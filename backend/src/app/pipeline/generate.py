"""Generate one quarter of synthetic service delivery, deterministically.

Writes what a real landing zone would hold, one folder per source system:

  crm/        clients and their funding (plans and home care agreements)
  hr/         support workers and their screening
  catalogue/  the support catalogue and its price limits
  rostering/  the roster, one extract per month
  mobile/     check-in and check-out events from workers' phones, one file a month

Seeds the defects declared in reference.py and writes which shift carries
which to a truth file outside the landing zone - the pipeline never reads it.

Money is integer cents, rates integer cents per hour, time whole minutes, and
every draw an integer, so the output is byte-identical on any machine.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from src.app.pipeline import reference as ref


def band_of(start: datetime) -> str:
    if start.weekday() == 5:
        return "SAT"
    if start.weekday() == 6:
        return "SUN"
    return "EVE" if start.hour >= 20 else "WD"


def amount_c(rate_c: int, minutes: int) -> int:
    return (rate_c * minutes + 30) // 60


def _money(c: int) -> str:
    return f"{c / 100:.2f}"


def _ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S")


BENIGN_NOTES = [
    "Assisted with shower and breakfast.", "Community outing to the library, back by 2pm.",
    "Meal prep for the week, fridge stocked.", "In good spirits today.", "Medication prompt given as per plan.",
    "Linen changed, vacuumed living areas.", "Shopping at the local centre.", "Walk to the park and coffee.",
    "Helped with appointments for next week.", "Garden tidy and bins out.",
]
NAMED_NOTES = ["{first} enjoyed the walk to the park.", "{first} asked to swap Thursday's visit to Friday.",
               "Helped {first} with lunch and a puzzle."]


def generate(raw: Path, truth_path: Path) -> list[Path]:
    rng = np.random.default_rng(ref.SEED)

    def ri(a: int, b: int) -> int:
        return int(rng.integers(a, b + 1))

    def pick(seq):
        return seq[ri(0, len(seq) - 1)]

    # ---- workers --------------------------------------------------------------
    workers: list[dict] = []
    for i in range(ref.WORKERS):
        region = ref.REGIONS[i % len(ref.REGIONS)]
        workers.append({
            "worker_id": f"W{2001 + i}", "given_name": pick(ref.FIRST_NAMES), "family_name": pick(ref.SURNAMES),
            "region": region, "employment": pick(["permanent", "permanent", "casual"]),
            "screening_id": f"SCR-{ri(100000, 999999)}",
            "screening_expiry": date(2027, 1, 1) + timedelta(days=ri(0, 1400)),
            "device_id": f"DV-{4001 + i}", "slots": {d: [] for d in range(7)},
        })
    by_region_w = {r: [w for w in workers if w["region"] == r] for r in ref.REGIONS}

    # Workers on the vendor's staged rollout, and three whose screening lapses.
    order = [int(x) for x in rng.permutation(len(workers))]
    lapsed_w = [workers[j] for j in order[:ref.SCREENING_LAPSED_WORKERS]]
    for w in lapsed_w:
        w["screening_expiry"] = date(2026, 8, 3) + timedelta(days=ri(0, 35))
    v5 = {workers[j]["worker_id"] for j in order[ref.SCREENING_LAPSED_WORKERS:]
          if ri(1, 100) <= ref.VENDOR_ROLLOUT_PCT}
    lapsed_ids = {w["worker_id"] for w in lapsed_w}

    # ---- clients and their funding ----------------------------------------------
    clients: list[dict] = []
    for i in range(ref.CLIENTS):
        region = ref.REGIONS[i % len(ref.REGIONS)]
        funding = "NDIS" if ri(1, 100) <= ref.NDIS_SHARE_PCT else "SAH"
        age = ri(19, 64) if funding == "NDIS" else ri(66, 94)
        clients.append({
            "client_id": f"C{10001 + i}", "given_name": pick(ref.FIRST_NAMES), "family_name": pick(ref.SURNAMES),
            "date_of_birth": date(2026 - age, ri(1, 12), ri(1, 28)), "region": region, "funding": funding,
            "phone": f"{ref.PHONE_PREFIX} {ri(0, 9999):04d}",
            "address": f"{ri(1, 240)} {pick(ref.STREETS)} Street, {pick(ref.SUBURBS[region])} QLD",
            "ndis_number": f"70{ri(1000000, 9999999)}" if funding == "NDIS" else "",
            "plan_start": date(2026, ri(1, 6), ri(1, 28)) if funding == "NDIS" else date(2025, ri(7, 12), 1),
            "slots": [],
        })
    for c in clients:
        c["plan_end"] = (c["plan_start"] + timedelta(days=364)) if c["funding"] == "NDIS" else date(2027, 6, 30)
        c["plan_id"] = f"{'PLN' if c['funding'] == 'NDIS' else 'AGR'}-{c['client_id'][1:]}-{c['plan_start']:%y%m}"

    # ---- weekly patterns: each client's regular visits and who does them ----------
    def free(w: dict, dow: int, s: int, e: int) -> bool:
        return all(e + 45 <= a or s >= b + 45 for a, b in w["slots"][dow])

    for c in clients:
        for _ in range(pick([1, 2, 2, 2, 3, 3])):
            dow = pick([0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6])
            if dow < 5 and ri(1, 20) == 1:
                start_m, dur = 20 * 60, pick([60, 90, 120])
            else:
                start_m, dur = ri(14, 33) * 30, pick([60, 90, 120, 120, 150, 180, 240])
            if any(s["dow"] == dow and not (start_m + dur <= s["start"] or start_m >= s["start"] + s["dur"])
                   for s in c["slots"]):
                continue
            pool = by_region_w[c["region"]]
            w = None
            for _try in range(25):
                cand = pick(pool)
                if free(cand, dow, start_m, start_m + dur):
                    w = cand
                    break
            if w is None:
                continue
            w["slots"][dow].append((start_m, start_m + dur))
            support = (pick(["ADL", "ADL", "ADL", "CP"]) if c["funding"] == "NDIS" else pick(["PC", "PC", "PC", "DA", "DA"]))
            discount = 0 if ri(1, 10) > 1 else ri(3, 8)
            c["slots"].append({"dow": dow, "start": start_m, "dur": dur, "worker": w, "support": support,
                               "discount_pct": discount})

    # ---- the roster ----------------------------------------------------------------
    shifts: list[dict] = []
    day = ref.PERIOD_START
    while day <= ref.PERIOD_END:
        todays = []
        for c in clients:
            for s in c["slots"]:
                if s["dow"] == day.weekday():
                    todays.append((s["start"], c["client_id"], c, s))
        for start_m, _, c, s in sorted(todays, key=lambda x: (x[0], x[1])):
            start = datetime(day.year, day.month, day.day) + timedelta(minutes=start_m)
            band = band_of(start)
            limit = ref.PRICE_LIMIT_C[(c["funding"], s["support"])][band]
            shifts.append({
                "client": c, "client_ref": c["client_id"], "worker": s["worker"], "funding": c["funding"],
                "support": s["support"], "item": ref.item_code(c["funding"], s["support"], band),
                "start": start, "end": start + timedelta(minutes=s["dur"]),
                "rate_c": limit * (100 - s["discount_pct"]) // 100, "status": "scheduled", "cancelled_at": None,
                "defects": [], "detail": "", "events": True, "malformed": "",
            })
        day += timedelta(days=1)

    # Cancellations with proper notice: not claimed, not held, not defects.
    for k in [int(x) for x in rng.permutation(len(shifts))[:24]]:
        sh = shifts[k]
        sh["status"], sh["cancelled_at"] = "client_cancelled", sh["start"] - timedelta(days=ri(8, 20), hours=ri(0, 9))
        sh["events"] = False

    # ---- who is special (kept apart so each defect is cleanly attributable) -----
    def v5_shift(sh: dict) -> bool:
        return sh["worker"]["worker_id"] in v5 and sh["start"].date() >= ref.VENDOR_RELEASE_DATE

    def lapsed_shift(sh: dict) -> bool:
        return sh["start"].date() > sh["worker"]["screening_expiry"]

    served_by_special = {c["client_id"] for c in clients
                         if any(s["worker"]["worker_id"] in v5 | lapsed_ids for s in c["slots"])}
    candidates = [c for c in clients if c["slots"] and c["client_id"] not in served_by_special]
    perm = [int(x) for x in rng.permutation(len(candidates))]
    ndis_c = [candidates[j] for j in perm if candidates[j]["funding"] == "NDIS"]
    plan_lapsed = ndis_c[:ref.PLAN_LAPSED_CLIENTS]
    for c in plan_lapsed:
        c["plan_end"] = date(2026, 8, 1) + timedelta(days=ri(0, 40))
        c["plan_start"] = c["plan_end"] - timedelta(days=364)
        c["plan_id"] = f"PLN-{c['client_id'][1:]}-{c['plan_start']:%y%m}"
    budget_c = [candidates[j] for j in perm if candidates[j] not in plan_lapsed][:ref.BUDGET_EXHAUSTED_CLIENTS]
    special_clients = {c["client_id"] for c in plan_lapsed + budget_c}

    def ordinary(sh: dict) -> bool:
        return (sh["status"] == "scheduled" and not v5_shift(sh) and not lapsed_shift(sh)
                and sh["client"]["client_id"] not in special_clients and not sh["defects"]
                and sh["worker"]["worker_id"] not in lapsed_ids)

    pool = [int(x) for x in rng.permutation(len(shifts))]

    def take(n: int, pred=lambda sh: True) -> list[dict]:
        got, rest = [], []
        for idx in pool:
            sh = shifts[idx]
            if len(got) < n and ordinary(sh) and pred(sh):
                got.append(sh)
            else:
                rest.append(idx)
        pool[:] = rest
        if len(got) < n:
            raise RuntimeError(f"could not seed {n} shifts: only {len(got)} candidates")
        return got

    def mark(sh: dict, defect: str, detail: str = "") -> None:
        sh["defects"].append(defect)
        sh["detail"] = sh["detail"] or detail

    for sh in take(ref.DEFECTS["no_show"]):
        sh["events"] = False
        mark(sh, "no_show", "no check-in and no cancellation")
    for sh in take(ref.DEFECTS["missing_checkout"]):
        sh["events"] = "in_only"
        mark(sh, "missing_checkout", "check-in only")
    for sh in take(ref.DEFECTS["hours_overclaimed"], lambda s: (s["end"] - s["start"]).seconds >= 120 * 60):
        sh["early_min"] = ri(30, 90)
        mark(sh, "hours_overclaimed", f"checked out {sh['early_min']} minutes before the rostered end")
    for sh in take(ref.DEFECTS["price_above_limit"]):
        limit = ref.PRICE_LIMIT_C[(sh["funding"], sh["support"])][band_of(sh["start"])]
        up = ri(4, 15)
        sh["rate_c"] = limit * (100 + up) // 100
        mark(sh, "price_above_limit", f"rate {up}% above the price limit")
    for sh in take(ref.DEFECTS["wrong_time_band"], lambda s: band_of(s["start"]) in ("SAT", "SUN")):
        sh["item"] = ref.item_code(sh["funding"], sh["support"], "WD")
        sh["rate_c"] = ref.PRICE_LIMIT_C[(sh["funding"], sh["support"])]["WD"]
        mark(sh, "wrong_time_band", f"{band_of(sh['start'])} shift on the weekday item")
    for sh in take(ref.DEFECTS["short_notice_cancellation"]):
        sh["status"], sh["events"] = "client_cancelled", False
        sh["cancelled_at"] = sh["start"] - timedelta(days=ri(1, 5), hours=ri(0, 9))
        mark(sh, "short_notice_cancellation", "cancelled inside the notice period")
    for sh in take(ref.DEFECTS["unknown_client"]):
        sh["client_ref"] = "C1O" + sh["client"]["client_id"][2:]
        mark(sh, "unknown_client", f"{sh['client']['client_id']} keyed as {sh['client_ref']}")

    # Double bookings: a worker rostered at a second client before the first visit ends.
    extra: list[dict] = []
    ordinary_clients = [c for c in clients if c["client_id"] not in special_clients | served_by_special and c["slots"]]
    for sh in take(ref.DEFECTS["worker_overlap"], lambda s: band_of(s["start"]) == "WD"
                   and (s["end"] - s["start"]).seconds >= 120 * 60):
        other = pick([c for c in ordinary_clients if c["region"] == sh["worker"]["region"]
                      and c is not sh["client"]])
        start = sh["start"] + timedelta(minutes=ri(30, 60))
        support = other["slots"][0]["support"]
        twin = {"client": other, "client_ref": other["client_id"], "worker": sh["worker"], "funding": other["funding"],
                "support": support, "item": ref.item_code(other["funding"], support, band_of(start)), "start": start,
                "end": start + timedelta(minutes=pick([60, 90, 120])),
                "rate_c": ref.PRICE_LIMIT_C[(other["funding"], support)][band_of(start)], "status": "scheduled",
                "cancelled_at": None, "defects": [], "detail": "", "events": True, "malformed": ""}
        mark(sh, "worker_overlap", "double-booked: a second client before this visit ends")
        mark(twin, "worker_overlap", "double-booked: rostered while still at another client")
        extra.append(twin)
    shifts += extra

    for k, sh in enumerate(take(ref.DEFECTS["roster_malformed"])):
        sh["malformed"] = "no_item" if k % 2 == 0 else "end_before_start"
        mark(sh, "roster_malformed", "item code missing" if k % 2 == 0 else "end time before start time")

    for sh in shifts:
        if v5_shift(sh) and sh["status"] == "scheduled" and sh["events"] and not sh["defects"]:
            mark(sh, "contract_change", f"evidenced only by app {ref.VENDOR_RELEASE_VERSION} events")
        if lapsed_shift(sh) and sh["status"] == "scheduled":
            mark(sh, "screening_lapsed", f"worker screening expired {sh['worker']['screening_expiry']:%d/%m/%Y}")
        if sh["client"] in plan_lapsed and sh["start"].date() > sh["client"]["plan_end"] and sh["status"] == "scheduled":
            mark(sh, "plan_lapsed", f"plan ended {sh['client']['plan_end']:%d/%m/%Y}")

    # Budgets: what is left of each client's funding at the start of the quarter.
    # Ordinary clients have plenty; five do not, and their last services are held.
    spend: dict[str, int] = {}
    for sh in shifts:
        if sh["status"] == "scheduled":
            minutes = int((sh["end"] - sh["start"]).total_seconds() // 60)
            spend[sh["client"]["client_id"]] = spend.get(sh["client"]["client_id"], 0) + amount_c(sh["rate_c"], minutes)
    for c in clients:
        quarter = spend.get(c["client_id"], 0)
        c["budget_c"] = quarter * ri(140, 260) // 100 + ri(50_000, 400_000)
    for c in budget_c:
        c["budget_c"] = spend[c["client_id"]] * ri(62, 80) // 100
        used = 0
        for sh in sorted((s for s in shifts if s["client"] is c and s["status"] == "scheduled"), key=lambda s: s["start"]):
            minutes = int((sh["end"] - sh["start"]).total_seconds() // 60)
            amt = amount_c(sh["rate_c"], minutes)
            if used + amt > c["budget_c"]:
                mark(sh, "budget_exhausted", "client budget exhausted")
            else:
                used += amt

    # ---- ids, then the phone events each shift produced ------------------------------
    shifts.sort(key=lambda s: (s["start"], s["client"]["client_id"], s["worker"]["worker_id"]))
    for n, sh in enumerate(shifts, start=1):
        sh["shift_id"] = f"SH-{n:06d}"

    events: list[dict] = []
    eid = 0
    late = 0
    for sh in shifts:
        if not sh["events"]:
            continue
        w = sh["worker"]
        new_app = w["worker_id"] in v5 and sh["start"].date() >= ref.VENDOR_RELEASE_DATE
        times = [("check_in", sh["start"] + timedelta(minutes=ri(-5, 5)))]
        if sh["events"] != "in_only":
            end = sh["end"] - timedelta(minutes=sh["early_min"]) if sh.get("early_min") else sh["end"]
            times.append(("check_out", end + timedelta(minutes=ri(-5, 5))))
        for kind, t in times:
            eid += 1
            offline = ri(1, 100) <= ref.LATE_SYNC_PCT
            received = t + (timedelta(minutes=ri(60, 4320)) if offline else timedelta(minutes=ri(0, 3), seconds=ri(0, 59)))
            late += offline
            note = ""
            if kind == "check_out" and ri(1, 3) == 1:
                note = (pick(NAMED_NOTES).format(first=sh["client"]["given_name"]) if ri(1, 4) == 1 else pick(BENIGN_NOTES))
            ev = {"event_id": f"EV-{eid:07d}", "app_version": ref.VENDOR_RELEASE_VERSION if new_app else ref.APP_VERSION_V1,
                  "device_id": w["device_id"], "shift_id": sh["shift_id"], "client_id": sh["client_ref"],
                  "event_type": kind, "note": note, "received_at": _ts(received), "_sh": sh, "_t": t}
            if new_app:
                ev["worker_ref"], ev["ts_utc"] = w["worker_id"], (t - timedelta(hours=ref.UTC_OFFSET_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                ev["worker_id"], ev["ts_local"] = w["worker_id"], _ts(t)
            events.append(ev)

    ev_pool = [int(x) for x in rng.permutation(len(events))]
    pii_targets = [events[j] for j in ev_pool if events[j]["event_type"] == "check_out"
                   and events[j]["app_version"] == ref.APP_VERSION_V1][:ref.DEFECTS["pii_in_notes"]]
    for k, ev in enumerate(pii_targets):
        c = ev["_sh"]["client"]
        ev["note"] = [f"{c['given_name']} {c['family_name']} asked me to call her daughter on {ref.PHONE_PREFIX} {ri(0, 9999):04d}.",
                      f"Plan manager needs NDIS number {c['ndis_number'] or '70' + str(ri(1000000, 9999999))} on the form.",
                      f"Mrs {c['family_name']} was tired today, short walk only.",
                      f"Called {c['given_name']} back on {c['phone']} to confirm Thursday."][k % 4]
        ev["_sh"]["pii"] = True

    dups: list[dict] = []
    src = [events[j] for j in ev_pool if events[j]["app_version"] == ref.APP_VERSION_V1][-ref.DEFECTS["duplicate_event"]:]
    for k, ev in enumerate(src):
        d = {**ev, "received_at": _ts(datetime.fromisoformat(ev["received_at"]) + timedelta(minutes=ri(1, 600)))}
        if k >= ref.DUPLICATE_SAME_ID:
            eid += 1
            d["event_id"] = f"EV-{eid:07d}"
        dups.append(d)
    events += dups

    # ---- write the landing zone ---------------------------------------------------
    files: list[Path] = []

    def write_csv(rel: str, header: list[str], rows: list[list]) -> None:
        path = raw / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)
        files.append(path)

    write_csv("crm/clients.csv",
              ["client_id", "given_name", "family_name", "date_of_birth", "phone", "address", "region", "funding",
               "ndis_number"],
              [[c["client_id"], c["given_name"], c["family_name"], c["date_of_birth"].isoformat(), c["phone"],
                c["address"], c["region"], c["funding"], c["ndis_number"]] for c in clients])
    write_csv("crm/plans.csv",
              ["plan_id", "client_id", "funding", "start_date", "end_date", "budget_remaining_at_2026_07_01", "management"],
              [[c["plan_id"], c["client_id"], c["funding"], c["plan_start"].isoformat(), c["plan_end"].isoformat(),
                _money(c["budget_c"]), ("agency" if int(c["client_id"][1:]) % 3 else "plan") if c["funding"] == "NDIS"
                else "provider"] for c in clients])
    write_csv("hr/workers.csv",
              ["worker_id", "given_name", "family_name", "region", "employment", "screening_id", "screening_expiry",
               "device_id"],
              [[w["worker_id"], w["given_name"], w["family_name"], w["region"], w["employment"], w["screening_id"],
                w["screening_expiry"].isoformat(), w["device_id"]] for w in workers])
    write_csv("catalogue/price_guide.csv",
              ["item_code", "funding", "support", "description", "time_band", "price_limit_per_hour", "effective_from"],
              [[ref.item_code(f, s, b), f, s, desc, b, _money(ref.PRICE_LIMIT_C[(f, s)][b]), ref.PRICE_GUIDE_EFFECTIVE.isoformat()]
               for f, items in ref.SUPPORTS.items() for s, desc in items for b in ref.BANDS])
    for month in ref.MONTHS:
        rows = []
        for sh in shifts:
            if sh["start"].strftime("%Y-%m") != month:
                continue
            start, end, item = _ts(sh["start"]), _ts(sh["end"]), sh["item"]
            if sh["malformed"] == "no_item":
                item = ""
            elif sh["malformed"] == "end_before_start":
                end = _ts(sh["start"] - timedelta(minutes=30))
            rows.append([sh["shift_id"], sh["client_ref"], sh["worker"]["worker_id"], item, start, end,
                         _money(sh["rate_c"]), sh["status"], _ts(sh["cancelled_at"]) if sh["cancelled_at"] else ""])
        write_csv(f"rostering/shifts_{month}.csv",
                  ["shift_id", "client_id", "worker_id", "item_code", "start_local", "end_local", "rate_per_hour",
                   "status", "cancelled_at"], rows)
        path = raw / "mobile" / f"visit_events_{month}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        month_events = sorted((e for e in events if e["_t"].strftime("%Y-%m") == month),
                              key=lambda e: (e["received_at"], e["event_id"]))
        with path.open("w", encoding="utf-8", newline="") as fh:
            for e in month_events:
                fh.write(json.dumps({k: v for k, v in e.items() if not k.startswith("_")}, ensure_ascii=True) + "\n")
        files.append(path)

    truth_path.parent.mkdir(parents=True, exist_ok=True)
    with truth_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["shift_id", "defects", "detail", "pii_note"])
        for sh in shifts:
            if sh["defects"] or sh.get("pii"):
                w.writerow([sh["shift_id"], "|".join(sh["defects"]), sh["detail"], "Y" if sh.get("pii") else ""])
    with (truth_path.parent / "truth_events.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["kind", "count"])
        w.writerows([["duplicate_event", len(dups)], ["late_sync", late], ["v5_workers", len(v5)]])
    return files
