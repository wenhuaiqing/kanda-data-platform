"""Proposals: a change to a data contract, with its evidence computed from the
data and its consequences previewed before anyone decides.

This quarter there is one. From 08/09 the mobile app vendor's release 5.0
sends check-ins with the worker under a new field name and the time in UTC.
Contract v1 quarantines every one of those events - correctly: a contract
that silently accepted a renamed field would let the next, worse change
through too. The services they evidence are held for want of evidence.
Releasing them one at a time would be waste and guessing; the proposal is
contract v2, which maps the new shape onto the old, and a person other than
the proposer decides.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.app.pipeline import reference as ref
from src.app.pipeline.stages import EVENTS_V2, PipelineResult, run_pipeline

PROPOSER = "contract-monitor"


def contract_v2_evidence(raw: Path, res: PipelineResult) -> dict:
    q = [x for x in res.quarantine if x["feed"] == "mobile.visit_events" and x["rule"] == "unknown_field"]
    keys = {x["record_key"] for x in q}
    recs = []
    for p in sorted((raw / "mobile").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["event_id"] in keys:
                recs.append(r)
    shifts = {s["shift_id"]: s for s in res.shifts}
    within_utc = within_local = parsed = 0
    for r in recs:
        try:
            t = datetime.fromisoformat(r["ts_utc"].rstrip("Z"))
        except (KeyError, ValueError):
            continue
        parsed += 1
        s = shifts.get(r["shift_id"])
        if s is None:
            continue
        lo, hi = s["start_local"] - timedelta(minutes=30), s["end_local"] + timedelta(minutes=30)
        within_utc += lo <= t + timedelta(hours=ref.UTC_OFFSET_HOURS) <= hi
        within_local += lo <= t <= hi
    versions = Counter(r.get("app_version") for r in recs)
    shapes = Counter(tuple(sorted(k for k in r if k in ("worker_ref", "ts_utc", "worker_id", "ts_local"))) for r in recs)
    held = [s for s in res.shifts if s.get("check_id") == "evidence" and s.get("events_quarantined")]
    first_seen = min((r["received_at"] for r in recs), default=None)
    return {
        "contract": "mobile.visit_events", "from_version": 1, "to_version": 2,
        "events_quarantined": len(recs), "app_versions": dict(versions),
        "field_shapes": {", ".join(k): v for k, v in shapes.items()},
        "first_seen": first_seen, "devices": len({r["device_id"] for r in recs}),
        "workers_resolved": sum(1 for r in recs if r.get("worker_ref") in res.workers),
        "timestamps_parsed": parsed,
        "within_roster_window_as_utc_plus_10": within_utc, "within_roster_window_read_as_local": within_local,
        "services_held": len(held), "services_held_value": round(sum(s["amount_c"] for s in held) / 100, 2),
    }


def contract_v2_preview(raw: Path, governed: PipelineResult) -> dict:
    after = run_pipeline(raw, approved={EVENTS_V2}, hash_files=False)
    b, a = governed.tables["fact_shift"], after.tables["fact_shift"]
    released = set(b.loc[b["status"] == "held", "shift_id"]) - set(a.loc[a["status"] == "held", "shift_id"])
    new_holds = set(a.loc[a["status"] == "held", "shift_id"]) - set(b.loc[b["status"] == "held", "shift_id"])
    qb, qa = len(governed.tables["quarantine"]), len(after.tables["quarantine"])
    return {
        "services_released": len(released),
        "claim_value_released": round(float(b.loc[b["shift_id"].isin(released), "amount"].sum()), 2),
        "exceptions_before": int((b["status"] == "held").sum()), "exceptions_after": int((a["status"] == "held").sum()),
        "new_holds": len(new_holds),
        "new_holds_by_check": a.loc[a["shift_id"].isin(new_holds), "check_id"].value_counts().to_dict(),
        "quarantined_before": qb, "quarantined_after": qa,
    }


def proposals_table(raw: Path, governed: PipelineResult, now: datetime) -> pd.DataFrame:
    ev = contract_v2_evidence(raw, governed)
    rows = []
    if ev["events_quarantined"]:
        rows.append({
            "proposal_id": "PRP-0001", "kind": "contract_version", "contract_version": EVENTS_V2,
            "title": f"Accept mobile app {ref.VENDOR_RELEASE_VERSION} events: visit events contract v2 "
                     "(worker_ref to worker_id, UTC to AEST)",
            "proposed_by": PROPOSER, "proposed_at": now, "status": "pending", "decided_by": None, "decided_at": None,
            "decision_note": None, "evidence": json.dumps(ev), "preview": json.dumps(contract_v2_preview(raw, governed)),
        })
    df = pd.DataFrame(rows)
    # All-null columns need a type, or the first approval cannot write to them.
    return df.astype({"decided_by": "string", "decision_note": "string", "decided_at": "datetime64[us]"})
