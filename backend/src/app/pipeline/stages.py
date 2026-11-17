"""The pipeline: landing zone to governed tables, and the checks before a claim.

  land       read and hash every raw file (bronze)
  contracts  every row against its feed's data contract; a row that breaks it
             goes to quarantine with the rule it broke - never dropped, never fixed
  conform    de-duplicate phone events (each removed copy recorded), convert the vendor's new shape when its
             contract is approved, mask free text (silver)
  evidence   pair each shift's check-in and check-out
  checks     nine checks in a fixed order; the first to fail holds the service
  publish    governed tables and a digest of every partition (gold)

Hold, never guess: a check that cannot decide holds the service and records
why. Nothing is dropped - every roster row is in fact_shift or in quarantine,
every phone event in fact_visit_event or in quarantine.

Each control can be switched off, which is how the ablation prices it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from src.app.pipeline import privacy
from src.app.pipeline import reference as ref

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTRACTS_DIR = REPO_ROOT / "contracts"

CHECK_ORDER = ["identity", "evidence", "screening", "overlap", "plan_dates", "item", "price", "duration", "budget"]
CONTROLS = ["dedupe_events", "mask_notes"] + CHECK_ORDER
ALL_ON = {c: True for c in CONTROLS}
FEED_OF = {"crm/clients.csv": "crm.clients", "crm/plans.csv": "crm.plans", "hr/workers.csv": "hr.workers",
           "catalogue/price_guide.csv": "catalogue.price_guide"}
EVENTS_V2 = "mobile.visit_events@2"


@dataclass
class Stage:
    name: str
    rows_in: int
    rows_out: int
    held: int
    wall_ms: float
    note: str = ""


@dataclass
class PipelineResult:
    files: pd.DataFrame
    tables: dict[str, pd.DataFrame]
    partition_hashes: pd.DataFrame
    stages: list[Stage]
    # Plain structures the case builder, the ablation and the proposals read.
    shifts: list[dict] = field(default_factory=list)
    clients: dict[str, dict] = field(default_factory=dict)
    workers: dict[str, dict] = field(default_factory=dict)
    plans: dict[str, dict] = field(default_factory=dict)
    items: dict[str, dict] = field(default_factory=dict)
    quarantine: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


@lru_cache(maxsize=None)
def contract(feed: str) -> dict:
    return yaml.safe_load((CONTRACTS_DIR / f"{feed}.yaml").read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame_digest(df: pd.DataFrame) -> str:
    body = df.to_csv(index=False, float_format="%.4f", lineterminator="\n")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def band_of(start: datetime) -> str:
    if start.weekday() == 5:
        return "SAT"
    if start.weekday() == 6:
        return "SUN"
    return "EVE" if start.hour >= 20 else "WD"


def cents(value: str) -> int:
    whole, _, frac = value.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2]) * (1 if not whole.startswith("-") else -1)


def amount_c(rate_c: int, minutes: int) -> int:
    return (rate_c * minutes + 30) // 60


# ---- contract validation --------------------------------------------------------

def _parse(kind: str, value: str):
    if kind == "string":
        return value
    if kind == "date":
        return date.fromisoformat(value)
    if kind == "timestamp":
        return datetime.fromisoformat(value)
    if kind == "money":
        if not re.fullmatch(r"-?\d+\.\d{2}", value):
            raise ValueError("not money")
        return cents(value)
    if kind == "integer":
        return int(value)
    raise ValueError(kind)


def validate_row(row: dict, fields: dict, strict_unknown: bool) -> tuple[dict | None, list[tuple[str, str]]]:
    """Return (typed row, []) or (None, [(rule, detail), ...])."""
    errors: list[tuple[str, str]] = []
    if strict_unknown:
        unknown = sorted(k for k in row if k not in fields)
        if unknown:
            errors.append(("unknown_field", ", ".join(unknown)))
    typed: dict = {}
    for name, spec in fields.items():
        value = row.get(name)
        value = "" if value is None else str(value)
        if value == "":
            if spec.get("required"):
                errors.append(("required", name))
            typed[name] = None
            continue
        try:
            v = _parse(spec["type"], value)
        except ValueError:
            errors.append(("type", f"{name} is not a {spec['type']}"))
            continue
        if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
            errors.append(("pattern", f"{name} {value!r}"))
        if "values" in spec and v not in spec["values"]:
            errors.append(("allowed_values", f"{name} {value!r}"))
        if "min" in spec and v < spec["min"]:
            errors.append(("range", f"{name} below {spec['min']}"))
        if "min_exclusive" in spec and v <= spec["min_exclusive"]:
            errors.append(("range", f"{name} not above {spec['min_exclusive']}"))
        typed[name] = v
    return (None, errors) if errors else (typed, [])


def _approved_fields(feed: str) -> dict:
    return next(v for v in contract(feed)["versions"] if v["status"] == "approved")["fields"]


def run_pipeline(raw: Path, controls: dict[str, bool] | None = None,
                 approved: frozenset[str] | set[str] = frozenset(), hash_files: bool = True) -> PipelineResult:
    on = {**ALL_ON, **(controls or {})}
    pol = ref.POLICY
    stages: list[Stage] = []
    clock = time.perf_counter()

    def stage(name: str, rows_in: int, rows_out: int, held: int = 0, note: str = "") -> None:
        nonlocal clock
        now = time.perf_counter()
        stages.append(Stage(name, rows_in, rows_out, held, round((now - clock) * 1000, 1), note))
        clock = now

    # ---- land -----------------------------------------------------------------------
    file_rows: list[dict] = []
    tabular: dict[str, list[dict]] = {}
    for rel, feed in FEED_OF.items():
        p = raw / rel
        tabular[rel] = _read_csv(p)
        file_rows.append({"file": rel, "feed": feed, "layer": "bronze", "rows": len(tabular[rel]),
                          "bytes": p.stat().st_size, "sha256": _sha(p) if hash_files else ""})
    roster_raw: list[dict] = []
    for p in sorted((raw / "rostering").glob("*.csv")):
        rows = _read_csv(p)
        for i, r in enumerate(rows):
            r["_file"], r["_row"] = f"rostering/{p.name}", i + 1
        roster_raw += rows
        file_rows.append({"file": f"rostering/{p.name}", "feed": "rostering.shifts", "layer": "bronze", "rows": len(rows),
                          "bytes": p.stat().st_size, "sha256": _sha(p) if hash_files else ""})
    events_raw: list[dict] = []
    for p in sorted((raw / "mobile").glob("*.jsonl")):
        recs = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line]
        for i, r in enumerate(recs):
            r["_file"], r["_row"] = f"mobile/{p.name}", i + 1
        events_raw += recs
        file_rows.append({"file": f"mobile/{p.name}", "feed": "mobile.visit_events", "layer": "bronze", "rows": len(recs),
                          "bytes": p.stat().st_size, "sha256": _sha(p) if hash_files else ""})
    files = pd.DataFrame(file_rows)
    landed = int(files["rows"].sum())
    stage("land", landed, landed, note=f"{len(files)} files from five source systems, hashed on landing")

    # ---- contracts ------------------------------------------------------------------
    quarantine: list[dict] = []

    def quarantine_row(feed: str, file: str, row: int, key: str, errors: list[tuple[str, str]], version: str = "") -> None:
        quarantine.append({"feed": feed, "file": file, "raw_row": row, "record_key": key,
                           "rule": errors[0][0], "detail": "; ".join(f"{r}: {d}" for r, d in errors)[:300],
                           "app_version": version})

    def load_master(rel: str, key: str) -> dict[str, dict]:
        feed = FEED_OF[rel]
        out = {}
        for i, r in enumerate(tabular[rel]):
            typed, errors = validate_row(r, _approved_fields(feed), strict_unknown=True)
            if errors:
                quarantine_row(feed, rel, i + 1, r.get(key, ""), errors)
            else:
                out[typed[key]] = typed
        return out

    clients = load_master("crm/clients.csv", "client_id")
    plans_by_id = load_master("crm/plans.csv", "plan_id")
    workers = load_master("hr/workers.csv", "worker_id")
    items = load_master("catalogue/price_guide.csv", "item_code")
    plans = {p["client_id"]: p for p in plans_by_id.values()}

    shift_fields = _approved_fields("rostering.shifts")
    shifts: list[dict] = []
    for r in roster_raw:
        raw_row = {k: v for k, v in r.items() if not k.startswith("_")}
        typed, errors = validate_row(raw_row, shift_fields, strict_unknown=True)
        if typed is not None:
            if typed["end_local"] <= typed["start_local"]:
                errors.append(("end_after_start", f"ends {typed['end_local']:%d/%m %H:%M}, starts {typed['start_local']:%d/%m %H:%M}"))
            if typed["item_code"] not in items:
                errors.append(("item_in_catalogue", f"{typed['item_code']} is not in the catalogue"))
        if errors:
            quarantine_row("rostering.shifts", r["_file"], r["_row"], r.get("shift_id", ""), errors)
            continue
        shifts.append({**typed, "file": r["_file"], "raw_row": r["_row"]})
    by_shift = {s["shift_id"]: s for s in shifts}

    ev_fields = _approved_fields("mobile.visit_events")
    v2 = EVENTS_V2 in approved
    events: list[dict] = []
    for r in events_raw:
        rec = {k: v for k, v in r.items() if not k.startswith("_")}
        mapped = False
        if v2 and "worker_ref" in rec and "ts_utc" in rec and "worker_id" not in rec and "ts_local" not in rec:
            try:
                local = datetime.fromisoformat(rec["ts_utc"].rstrip("Z")) + timedelta(hours=ref.UTC_OFFSET_HOURS)
                rec = {**{k: v for k, v in rec.items() if k not in ("worker_ref", "ts_utc")},
                       "worker_id": rec["worker_ref"], "ts_local": local.strftime("%Y-%m-%dT%H:%M:%S")}
                mapped = True
            except ValueError:
                pass
        typed, errors = validate_row(rec, ev_fields, strict_unknown=True)
        if typed is not None and typed["shift_id"] not in by_shift:
            errors.append(("shift_in_roster", f"{typed['shift_id']} is not in the roster that loaded"))
        if errors:
            quarantine_row("mobile.visit_events", r["_file"], r["_row"], r.get("event_id", ""), errors, r.get("app_version", ""))
            continue
        events.append({**typed, "file": r["_file"], "raw_row": r["_row"], "mapped_v2": mapped})
    q_counts = {}
    for q in quarantine:
        q_counts[q["feed"]] = q_counts.get(q["feed"], 0) + 1
    stage("contracts", landed, landed - len(quarantine), len(quarantine),
          f"{len(quarantine)} rows quarantined with the rule they broke"
          + (f" ({', '.join(f'{k}: {v}' for k, v in sorted(q_counts.items()))})" if q_counts else ""))

    # ---- conform ---------------------------------------------------------------------
    names = privacy.name_pattern({c["given_name"] for c in clients.values()} | {c["family_name"] for c in clients.values()})
    seen_id: dict[str, str] = {}
    seen_nat: dict[tuple, str] = {}
    kept: list[dict] = []
    duplicates: list[dict] = []
    dup_id = dup_nat = masked = 0
    for e in sorted(events, key=lambda e: (e["received_at"], e["event_id"])):
        nat = (e["shift_id"], e["event_type"], e["ts_local"])
        first = seen_id.get(e["event_id"]) if on["dedupe_events"] else None
        reason = "same event id resent"
        if first is None and on["dedupe_events"]:
            first, reason = seen_nat.get(nat), "same shift, event and time under a new id"
        if first is not None:
            dup_id += reason == "same event id resent"
            dup_nat += reason != "same event id resent"
            duplicates.append({"event_id": e["event_id"], "kept_event_id": first, "reason": reason,
                               "received_at": e["received_at"], "file": e["file"], "raw_row": e["raw_row"]})
            continue
        seen_id.setdefault(e["event_id"], e["event_id"])
        seen_nat.setdefault(nat, e["event_id"])
        if on["mask_notes"]:
            e["note_masked"], found = privacy.mask(e["note"] or "", names)
            e["pii_found"] = ",".join(found)
            masked += bool(found)
        else:
            e["note_masked"], e["pii_found"] = e["note"] or "", ""
        sh = by_shift[e["shift_id"]]
        cutoff = datetime.combine(sh["start_local"].date() + timedelta(days=1), datetime.min.time()) \
            + timedelta(hours=pol["evidence_cutoff_hour"])
        e["after_cutoff"] = e["received_at"] > cutoff
        e["lag_minutes"] = int((e["received_at"] - e["ts_local"]).total_seconds() // 60)
        kept.append(e)
    events = kept
    stage("conform", len(events) + dup_id + dup_nat, len(events), 0,
          f"{dup_id} resent events and {dup_nat} re-keyed copies removed; {masked} notes masked"
          + ("; app 5.0 events mapped under contract v2" if v2 else ""))

    # ---- evidence --------------------------------------------------------------------
    ev_by_shift: dict[str, list[dict]] = {}
    for e in events:
        ev_by_shift.setdefault(e["shift_id"], []).append(e)
    # Quarantined events still tell a reader something: how many there were for a shift.
    q_by_shift: dict[str, int] = {}
    q_events = {q["record_key"] for q in quarantine if q["feed"] == "mobile.visit_events"}
    for r in events_raw:
        if r.get("event_id") in q_events and r.get("shift_id"):
            q_by_shift[r["shift_id"]] = q_by_shift.get(r["shift_id"], 0) + 1
    evidenced = 0
    for s in shifts:
        evs = ev_by_shift.get(s["shift_id"], [])
        ins = sorted(e["ts_local"] for e in evs if e["event_type"] == "check_in")
        outs = sorted(e["ts_local"] for e in evs if e["event_type"] == "check_out")
        s["check_in"] = ins[0] if ins else None
        s["check_out"] = outs[-1] if outs else None
        s["events_in"], s["events_out"] = len(ins), len(outs)
        s["events_quarantined"] = q_by_shift.get(s["shift_id"], 0)
        s["rostered_min"] = int((s["end_local"] - s["start_local"]).total_seconds() // 60)
        if len(ins) == 1 and len(outs) == 1 and outs[0] > ins[0]:
            s["evidence"] = "complete"
            s["evidenced_min"] = int((outs[0] - ins[0]).total_seconds() // 60)
            evidenced += 1
        else:
            s["evidence"] = ("none" if not ins and not outs else "check_in_only" if ins and not outs
                             else "check_out_only" if outs and not ins else "ambiguous")
            s["evidenced_min"] = None
    stage("evidence", len(shifts), evidenced, 0, "each shift's check-in and check-out paired; minutes evidenced")

    # ---- checks ----------------------------------------------------------------------
    by_worker: dict[str, list[dict]] = {}
    for s in shifts:
        if s["evidence"] == "complete":
            by_worker.setdefault(s["worker_id"], []).append(s)
    overlaps: dict[str, list[str]] = {}
    for wid, ss in by_worker.items():
        ss.sort(key=lambda s: s["check_in"])
        for i, a in enumerate(ss):
            for b in ss[i + 1:]:
                if b["check_in"] >= a["check_out"]:
                    break
                mins = (min(a["check_out"], b["check_out"]) - b["check_in"]).total_seconds() / 60
                if mins > pol["overlap_tolerance_minutes"]:
                    overlaps.setdefault(a["shift_id"], []).append(b["shift_id"])
                    overlaps.setdefault(b["shift_id"], []).append(a["shift_id"])

    regular: dict[tuple, set[str]] = {}
    for s in shifts:
        if s["client_id"] in clients:
            regular.setdefault((s["worker_id"], s["start_local"].weekday(), s["start_local"].time()), set()).add(s["client_id"])

    used: dict[str, int] = {}
    for s in sorted(shifts, key=lambda s: (s["start_local"], s["shift_id"])):
        fails: dict[str, tuple[str, int]] = {}
        s["fails"] = fails
        s["candidates"] = []
        item = items[s["item_code"]]
        s["band"] = band_of(s["start_local"])
        s["funding"] = item["funding"]
        s["limit_c"] = item["price_limit_per_hour"]
        s["amount_c"] = amount_c(s["rate_per_hour"], s["rostered_min"])
        s["region"] = workers[s["worker_id"]]["region"] if s["worker_id"] in workers else None
        client = clients.get(s["client_id"])
        if s["status"] == "client_cancelled":
            notice = s["start_local"] - (s["cancelled_at"] or s["start_local"])
            s["kind"] = "short_notice_cancellation" if notice < timedelta(days=pol["short_notice_cancellation_days"]) \
                else "cancelled_with_notice"
        else:
            s["kind"] = "service"
        if s["kind"] == "cancelled_with_notice":
            s["status_out"] = "not_claimable"
            continue
        service = s["kind"] == "service"

        if client is None:
            s["candidates"] = sorted(regular.get((s["worker_id"], s["start_local"].weekday(), s["start_local"].time()), set()))
            if on["identity"]:
                why = f"Client {s['client_id']} is not in the client master."
                if s["candidates"]:
                    why += (f" {len(s['candidates'])} client(s) this worker regularly sees at this time: "
                            f"{', '.join(s['candidates'][:3])}.")
                fails["identity"] = (why, s["amount_c"])
        else:
            s["region"] = client["region"]

        if service and on["evidence"] and s["evidence"] != "complete":
            if s["evidence"] == "none":
                why = "No check-in or check-out was received."
            elif s["evidence"] == "check_in_only":
                why = f"Checked in at {s['check_in']:%H:%M}; no check-out was received."
            elif s["evidence"] == "check_out_only":
                why = "A check-out with no check-in."
            else:
                why = f"{s['events_in']} check-ins and {s['events_out']} check-outs: the visit cannot be read."
            if s["events_quarantined"]:
                why += f" {s['events_quarantined']} event(s) for this shift are in quarantine under the visit events contract."
            fails["evidence"] = (why, s["amount_c"])

        w = workers.get(s["worker_id"])
        if service and on["screening"] and w is not None and s["start_local"].date() > w["screening_expiry"]:
            fails["screening"] = (f"Worker {s['worker_id']}'s screening expired {w['screening_expiry']:%d/%m/%Y}.", s["amount_c"])

        if service and on["overlap"] and s["shift_id"] in overlaps:
            fails["overlap"] = (f"Worker {s['worker_id']} was checked in at {', '.join(overlaps[s['shift_id']])} "
                                "at the same time for more than 15 minutes.", s["amount_c"])

        plan = plans.get(s["client_id"])
        if client is not None and on["plan_dates"] and (plan is None or not (plan["start_date"] <= s["start_local"].date() <= plan["end_date"])):
            why = (f"No funding on file for {s['client_id']}." if plan is None else
                   f"Service on {s['start_local']:%d/%m/%Y} is outside plan {plan['plan_id']} "
                   f"({plan['start_date']:%d/%m/%Y} to {plan['end_date']:%d/%m/%Y}).")
            fails["plan_dates"] = (why, s["amount_c"])

        right_item = ref.item_code(item["funding"], item["support"], s["band"])
        if on["item"] and (item["time_band"] != s["band"] or (client is not None and item["funding"] != client["funding"])):
            right_limit = items[right_item]["price_limit_per_hour"] if right_item in items else s["limit_c"]
            gap = amount_c(right_limit, s["rostered_min"]) - s["amount_c"]
            fails["item"] = (f"{s['item_code']} is the {ref.BAND_LABEL[item['time_band']].lower()} item; the shift starts "
                             f"{s['start_local']:%a %H:%M} ({ref.BAND_LABEL[s['band']].lower()}): {right_item}.", abs(gap))

        if on["price"] and s["rate_per_hour"] > s["limit_c"]:
            fails["price"] = (f"Rate {s['rate_per_hour'] / 100:,.2f} an hour is above the {s['item_code']} limit of "
                              f"{s['limit_c'] / 100:,.2f}.", amount_c(s["rate_per_hour"] - s["limit_c"], s["rostered_min"]))

        if service and on["duration"] and s["evidenced_min"] is not None:
            gap = s["rostered_min"] - s["evidenced_min"]
            allowed = max(pol["duration_tolerance_minutes"], s["rostered_min"] * pol["duration_tolerance_pct"])
            if gap > allowed:
                fails["duration"] = (f"Rostered {s['rostered_min']} minutes; evidenced {s['evidenced_min']} "
                                     f"({s['check_in']:%H:%M} to {s['check_out']:%H:%M}).",
                                     amount_c(s["rate_per_hour"], gap))

        if not fails and plan is not None:
            left = plan["budget_remaining_at_2026_07_01"] - used.get(s["client_id"], 0)
            if on["budget"] and s["amount_c"] > left:
                fails["budget"] = (f"Claim of {s['amount_c'] / 100:,.2f} is more than the {left / 100:,.2f} left on "
                                   f"{plan['plan_id']}.", s["amount_c"])
            else:
                used[s["client_id"]] = used.get(s["client_id"], 0) + s["amount_c"]
        s["budget_used_before"] = used.get(s["client_id"], 0)
        checks = [c for c in CHECK_ORDER if c in fails]
        s["check_id"] = checks[0] if checks else None
        s["status_out"] = "held" if checks else ("claimable_cancellation" if s["kind"] == "short_notice_cancellation" else "claimable")
    for s in shifts:
        s.setdefault("fails", {})
        s.setdefault("check_id", None)
        s.setdefault("candidates", [])
        s.setdefault("budget_used_before", 0)
    held = sum(1 for s in shifts if s["status_out"] == "held")
    stage("checks", len(shifts), len(shifts) - held, held, "nine checks in a fixed order; the first to fail is the reason on the exception")

    # ---- publish ---------------------------------------------------------------------
    shift_rows, exc_rows = [], []
    for s in sorted(shifts, key=lambda s: s["shift_id"]):
        checks = [c for c in CHECK_ORDER if c in s["fails"]]
        month = s["start_local"].strftime("%Y-%m")
        claim = s["amount_c"] if s["status_out"] in ("claimable", "claimable_cancellation") else 0
        shift_rows.append({
            "shift_id": s["shift_id"], "month": month, "service_date": s["start_local"].date(),
            "start_local": s["start_local"], "end_local": s["end_local"], "client_id": s["client_id"],
            "worker_id": s["worker_id"], "region": s["region"], "funding": s["funding"], "item_code": s["item_code"],
            "time_band": s["band"], "kind": s["kind"], "rostered_min": s["rostered_min"],
            "evidence": s.get("evidence"), "evidenced_min": s.get("evidenced_min"),
            "check_in": s.get("check_in"), "check_out": s.get("check_out"),
            "rate": s["rate_per_hour"] / 100, "price_limit": s["limit_c"] / 100, "amount": s["amount_c"] / 100,
            "status": s["status_out"], "check_id": s["check_id"], "checks": ",".join(checks),
            "claim_amount": claim / 100,
            "at_risk": (s["fails"][checks[0]][1] / 100) if checks else 0.0,
            "file": s["file"], "raw_row": s["raw_row"],
        })
        if checks:
            exc_rows.append({
                "exception_id": "EX-" + s["shift_id"][3:], "shift_id": s["shift_id"], "month": month,
                "service_date": s["start_local"].date(), "region": s["region"], "client_id": s["client_id"],
                "worker_id": s["worker_id"], "item_code": s["item_code"], "check_id": checks[0], "checks": ",".join(checks),
                "reason": s["fails"][checks[0]][0], "amount": s["amount_c"] / 100, "at_risk": s["fails"][checks[0]][1] / 100,
            })
    event_rows = [{
        "event_id": e["event_id"], "month": e["ts_local"].strftime("%Y-%m"), "shift_id": e["shift_id"],
        "worker_id": e["worker_id"], "client_id": e["client_id"], "event_type": e["event_type"], "ts_local": e["ts_local"],
        "received_at": e["received_at"], "lag_minutes": e["lag_minutes"], "after_cutoff": e["after_cutoff"],
        "app_version": e["app_version"], "mapped_v2": e["mapped_v2"], "note_masked": e["note_masked"] or None,
        "pii_found": e["pii_found"] or None, "file": e["file"], "raw_row": e["raw_row"],
    } for e in sorted(events, key=lambda e: e["event_id"])]

    today = ref.PERIOD_END
    dim_client = pd.DataFrame([{
        "client_id": c["client_id"], "region": c["region"], "funding": c["funding"],
        "age_band": _age_band(c["date_of_birth"], today), "has_ndis_number": bool(c["ndis_number"])}
        for c in clients.values()])
    dim_worker = pd.DataFrame([{
        "worker_id": w["worker_id"], "region": w["region"], "employment": w["employment"],
        "screening_expiry": w["screening_expiry"]} for w in workers.values()])
    dim_item = pd.DataFrame([{
        "item_code": i["item_code"], "funding": i["funding"], "support": i["support"], "description": i["description"],
        "time_band": i["time_band"], "price_limit": i["price_limit_per_hour"] / 100, "effective_from": i["effective_from"]}
        for i in items.values()])
    dim_plan = pd.DataFrame([{
        "plan_id": p["plan_id"], "client_id": p["client_id"], "funding": p["funding"], "start_date": p["start_date"],
        "end_date": p["end_date"], "budget_at_period_start": p["budget_remaining_at_2026_07_01"] / 100,
        "claimed_in_period": used.get(p["client_id"], 0) / 100, "management": p["management"]} for p in plans_by_id.values()])
    exc_cols = ["exception_id", "shift_id", "month", "service_date", "region", "client_id", "worker_id", "item_code",
                "check_id", "checks", "reason", "amount", "at_risk"]
    q_cols = ["feed", "file", "raw_row", "record_key", "rule", "detail", "app_version"]
    tables = {
        "dim_client": dim_client, "dim_worker": dim_worker, "dim_support_item": dim_item, "dim_plan": dim_plan,
        "fact_shift": pd.DataFrame(shift_rows), "fact_visit_event": pd.DataFrame(event_rows),
        "exceptions": pd.DataFrame(exc_rows, columns=exc_cols),
        "quarantine": pd.DataFrame(sorted(quarantine, key=lambda q: (q["feed"], q["file"], q["raw_row"])), columns=q_cols),
        "event_duplicates": pd.DataFrame(sorted(duplicates, key=lambda d: (d["file"], d["raw_row"])),
                                         columns=["event_id", "kept_event_id", "reason", "received_at", "file", "raw_row"]),
    }
    hashes = []
    for name in ("dim_client", "dim_worker", "dim_support_item", "dim_plan", "quarantine", "event_duplicates"):
        hashes.append({"partition": name, "rows": len(tables[name]), "sha256": frame_digest(tables[name])})
    for name in ("fact_shift", "fact_visit_event", "exceptions"):
        for month in ref.MONTHS:
            part = tables[name][tables[name]["month"] == month]
            hashes.append({"partition": f"{name}/{month}", "rows": len(part), "sha256": frame_digest(part)})
    stage("publish", len(shifts), sum(len(t) for t in tables.values()), 0,
          f"{len(tables)} governed tables, {len(hashes)} partitions digested")
    return PipelineResult(files=files, tables=tables, partition_hashes=pd.DataFrame(hashes), stages=stages,
                          shifts=shifts, clients=clients, workers=workers, plans=plans, items=items,
                          quarantine=quarantine, events=events)


def _age_band(dob: date, on: date) -> str:
    age = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    for hi, label in ((24, "18-24"), (44, "25-44"), (64, "45-64"), (79, "65-79")):
        if age <= hi:
            return label
    return "80+"
