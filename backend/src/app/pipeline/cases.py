"""One case per held service: what a coordinator - or the triage agent - would
look at to decide it, frozen as at the quarter's close, and the label it is
graded against.

The snapshot is six tool answers. Three things are deliberate:

  - no client's name, date of birth, phone, address or NDIS number reaches
    it. Clients are their id, region, funding and age band.
  - visit notes are carried masked, under a key that says they are
    untrusted. They are evidence about the visit, never an instruction.
  - the policy library is not in the snapshot: the agent searches it, and
    what it retrieved is graded like any other evidence.

Labels come from the generator's truth file, which the pipeline never reads.
"""

from __future__ import annotations

import csv
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from src.app.pipeline import reference as ref
from src.app.pipeline.stages import PipelineResult

TOOL_NAMES = ["get_service", "get_visit_events", "get_worker", "get_client", "get_price_guide", "get_related_services"]

# When a service carries more than one seeded defect, the one a person has to
# act on first - the one the earliest check holds it for.
PRECEDENCE = ["unknown_client", "contract_change", "no_show", "missing_checkout", "screening_lapsed", "worker_overlap",
              "plan_lapsed", "wrong_time_band", "price_above_limit", "hours_overclaimed", "budget_exhausted"]


def load_truth(path: Path) -> dict[str, tuple[list[str], str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["shift_id"]: ([d for d in r["defects"].split("|") if d], r["detail"]) for r in csv.DictReader(fh)}


def label_for(defects: list[str]) -> str:
    for d in PRECEDENCE:
        if d in defects:
            return d
    return "valid_service"


def _t(v) -> str | None:
    return v.strftime("%Y-%m-%dT%H:%M") if v is not None else None


def _brief(s: dict) -> dict:
    return {"shift_id": s["shift_id"], "client_id": s["client_id"], "worker_id": s["worker_id"],
            "start": _t(s["start_local"]), "end": _t(s["end_local"]), "check_in": _t(s.get("check_in")),
            "check_out": _t(s.get("check_out")), "status": s.get("status_out")}


def build_world(s: dict, res: PipelineResult, idx: dict) -> dict:
    item = res.items[s["item_code"]]
    right = ref.item_code(item["funding"], item["support"], s["band"])
    service = {
        "shift_id": s["shift_id"], "client_id": s["client_id"], "worker_id": s["worker_id"], "region": s["region"],
        "kind": s["kind"], "start": _t(s["start_local"]), "end": _t(s["end_local"]),
        "weekday": s["start_local"].strftime("%A"), "rostered_minutes": s["rostered_min"],
        "item_code": s["item_code"], "item_time_band": item["time_band"], "shift_time_band": s["band"],
        "rate_per_hour": s["rate_per_hour"] / 100, "claim_amount": s["amount_c"] / 100,
        "roster_status": s["status"], "cancelled_at": _t(s.get("cancelled_at")),
        "crm_contact_log": [],
    }
    evs = [e for e in idx["events"].get(s["shift_id"], [])]
    events = {
        "evidence": s.get("evidence"), "evidenced_minutes": s.get("evidenced_min"),
        "check_in": _t(s.get("check_in")), "check_out": _t(s.get("check_out")),
        "events": [{"event_id": e["event_id"], "event_type": e["event_type"], "ts_local": _t(e["ts_local"]),
                    "received_at": _t(e["received_at"]), "app_version": e["app_version"],
                    "note_untrusted": e["note_masked"] or None} for e in sorted(evs, key=lambda e: e["ts_local"])],
        "quarantined": [{"event_id": q["record_key"], "rule": q["rule"], "detail": q["detail"],
                         "app_version": q["app_version"]} for q in idx["quarantine"].get(s["shift_id"], [])],
    }
    w = res.workers.get(s["worker_id"])
    day = s["start_local"].date()
    worker = {"found": w is not None}
    if w is not None:
        worker.update({
            "worker_id": w["worker_id"], "region": w["region"], "employment": w["employment"],
            "screening_expiry": w["screening_expiry"].isoformat(),
            "screening_valid_on_service_date": day <= w["screening_expiry"],
            "other_services_that_day": [_brief(o) for o in idx["by_worker_day"].get((s["worker_id"], day), [])
                                        if o["shift_id"] != s["shift_id"]],
        })
    c = res.clients.get(s["client_id"])
    plan = res.plans.get(s["client_id"])
    if c is None:
        client = {"found": False, "client_id_on_roster": s["client_id"],
                  "regular_clients_of_this_worker_at_this_time": [
                      {"client_id": cid, "region": res.clients[cid]["region"], "funding": res.clients[cid]["funding"],
                       "services_that_day": [_brief(o) for o in idx["by_client_day"].get((cid, day), [])]}
                      for cid in s["candidates"][:3]]}
    else:
        client = {"found": True, "client_id": c["client_id"], "region": c["region"], "funding": c["funding"],
                  "age_band": idx["age_band"].get(c["client_id"])}
        if plan is not None:
            budget = plan["budget_remaining_at_2026_07_01"]
            client["plan"] = {"plan_id": plan["plan_id"], "start_date": plan["start_date"].isoformat(),
                              "end_date": plan["end_date"].isoformat(), "management": plan["management"],
                              "budget_at_period_start": budget / 100,
                              "claimed_before_this_service": s["budget_used_before"] / 100,
                              "remaining_before_this_service": (budget - s["budget_used_before"]) / 100,
                              "renewal": None}
    price = {"item": {"item_code": item["item_code"], "description": item["description"], "time_band": item["time_band"],
                      "price_limit_per_hour": item["price_limit_per_hour"] / 100},
             "item_for_this_shift_time_band": {"item_code": right,
                                               "price_limit_per_hour": res.items[right]["price_limit_per_hour"] / 100
                                               if right in res.items else None},
             "time_band_rule": "The band of the shift's start: weekday 06:00-19:59, weekday 20:00-23:59, Saturday, Sunday."}
    related = {"same_client_same_day": [_brief(o) for o in idx["by_client_day"].get((s["client_id"], day), [])
                                        if o["shift_id"] != s["shift_id"]],
               "overlapping_services_by_this_worker": [],
               "previous_week_same_slot": [_brief(o) for o in idx["by_client_day"].get((s["client_id"], day - timedelta(days=7)), [])]}
    if s.get("check_out") is not None:
        related["overlapping_services_by_this_worker"] = [
            _brief(o) for o in idx["by_worker_day"].get((s["worker_id"], day), [])
            if o["shift_id"] != s["shift_id"] and o.get("check_in") and o.get("check_out") and s.get("check_in")
            and o["check_in"] < s["check_out"] and s["check_in"] < o["check_out"]]
    return {"get_service": service, "get_visit_events": events, "get_worker": worker, "get_client": client,
            "get_price_guide": price, "get_related_services": related}


def index(res: PipelineResult) -> dict:
    idx: dict = {"events": {}, "quarantine": {}, "by_worker_day": {}, "by_client_day": {}, "shift": {}, "age_band": {}}
    for e in res.events:
        idx["events"].setdefault(e["shift_id"], []).append(e)
    for s in res.shifts:
        idx["shift"][s["shift_id"]] = s
        idx["by_worker_day"].setdefault((s["worker_id"], s["start_local"].date()), []).append(s)
        idx["by_client_day"].setdefault((s["client_id"], s["start_local"].date()), []).append(s)
    for k in idx["by_worker_day"].values():
        k.sort(key=lambda s: s["start_local"])
    dim = res.tables["dim_client"]
    idx["age_band"] = dict(zip(dim["client_id"], dim["age_band"]))
    return idx


def attach_quarantine(idx: dict, res: PipelineResult, raw: Path) -> None:
    keys = {q["record_key"]: q for q in res.quarantine if q["feed"] == "mobile.visit_events"}
    for p in sorted((raw / "mobile").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            q = keys.get(r["event_id"])
            if q is not None and r.get("shift_id"):
                lst = idx["quarantine"].setdefault(r["shift_id"], [])
                if all(x["record_key"] != q["record_key"] for x in lst):
                    lst.append(q)


def build_cases(res: PipelineResult, truth: dict[str, tuple[list[str], str]], raw: Path) -> pd.DataFrame:
    idx = index(res)
    attach_quarantine(idx, res, raw)
    rows = []
    for s in res.shifts:
        if s.get("status_out") != "held":
            continue
        defects, detail = truth.get(s["shift_id"], ([], ""))
        category = label_for(defects)
        rows.append({"exception_id": "EX-" + s["shift_id"][3:], "shift_id": s["shift_id"],
                     "world": json.dumps(build_world(s, res, idx), default=str),
                     "label_category": category, "label_action": ref.LABEL_ACTION[category], "label_detail": detail})
    return pd.DataFrame(rows, columns=["exception_id", "shift_id", "world", "label_category", "label_action", "label_detail"])
