"""Governed writes: deciding a held service, approving a contract change, reset.

Every write is token-gated by the router, audit-logged here, and refused - not
warned - when the rule says no:

  - the automation's service identities cannot decide anything
  - a held service is decided once
  - a screening hold can only be escalated to compliance, by anyone
  - a service with no evidence cannot be claimed as rostered from this queue
  - the proposer of a contract change cannot approve it

Approving a contract change reprocesses the quarter from the landing zone and
replaces the governed tables, so every page moves on the next request.
Nothing is patched in place.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from fastapi import HTTPException

from src.app.pipeline.ablation import run_ablation
from src.app.pipeline.cases import load_truth
from src.app.pipeline.persist import persist_governed, replace
from src.app.pipeline.reference import CLAIMING, LABEL_ACTION
from src.app.pipeline.stages import run_pipeline
from src.app.services import db
from src.settings import settings

SERVICE_IDENTITIES = {"contract-monitor", "triage-agent"}
ACTIONS = set(LABEL_ACTION.values())


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _audit(cur, actor: str, action: str, subject: str, outcome: str, detail: dict | str) -> None:
    cur.execute("INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?)", [
        _now(), actor, action, subject, outcome, detail if isinstance(detail, str) else json.dumps(detail, default=str)])


def _refuse(cur, actor: str, action: str, subject: str, status: int, reason: str) -> None:
    _audit(cur, actor, action, subject, "refused", reason)
    raise HTTPException(status_code=status, detail=reason)


def approved_contracts(cur=None) -> frozenset[str]:
    sql = "SELECT contract_version FROM proposals WHERE status = 'approved'"
    rows = cur.execute(sql).fetchall() if cur is not None else [(r["contract_version"],) for r in db.rows(sql)]
    return frozenset(r[0] for r in rows)


def decide_exception(exception_id: str, actor: str, action: str, note: str = "") -> dict:
    with db.writing() as cur:
        rows = cur.execute("SELECT check_id, reason FROM exceptions WHERE exception_id = ?", [exception_id]).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No held service {exception_id}.")
        check_id, reason = rows[0]
        verb = f"decide:{action}"
        if action not in ACTIONS:
            raise HTTPException(status_code=400, detail=f"{action} is not an action a person can take here.")
        if actor.strip().lower() in SERVICE_IDENTITIES:
            _refuse(cur, actor, verb, exception_id, 403,
                    f"{actor} is the automation's own identity. It proposes; a person decides.")
        prior = cur.execute("SELECT action, actor FROM exception_decisions WHERE exception_id = ?", [exception_id]).fetchall()
        if prior:
            _refuse(cur, actor, verb, exception_id, 409,
                    f"{exception_id} was already decided ({prior[0][0]}) by {prior[0][1]}. A held service is decided once.")
        if check_id == "screening" and action != "escalate_to_compliance":
            _refuse(cur, actor, verb, exception_id, 409,
                    "A service by a worker whose screening had expired can only be escalated to compliance. It is not "
                    "claimed from this queue by anyone, whatever is known about a renewal.")
        if check_id == "evidence" and action in CLAIMING and "No check-in" in reason:
            _refuse(cur, actor, verb, exception_id, 409,
                    "There is no evidence this service was delivered. It cannot be claimed from this queue; record the "
                    "worker's confirmation, or the cancellation, first.")
        if not note.strip() and action in CLAIMING:
            _refuse(cur, actor, verb, exception_id, 400,
                    "A claim released from the exception queue needs a note saying why.")
        cur.execute("INSERT INTO exception_decisions VALUES (?, ?, ?, ?, ?)", [exception_id, action, actor, _now(), note])
        _audit(cur, actor, verb, exception_id, "done", note or action)
        return {"exception_id": exception_id, "action": action, "decided_by": actor}


def _snapshot(cur) -> dict:
    held, claimable, risk, quarantined = cur.execute(
        "SELECT count(*) FILTER (WHERE status = 'held'), count(*) FILTER (WHERE status LIKE 'claimable%'), "
        "coalesce(sum(amount) FILTER (WHERE status = 'held'), 0), (SELECT count(*) FROM quarantine) FROM fact_shift").fetchall()[0]
    return {"held": int(held), "claimable": int(claimable), "held_value": round(float(risk), 2),
            "held_for_evidence": int(cur.execute("SELECT count(*) FROM fact_shift WHERE check_id = 'evidence'").fetchall()[0][0]),
            "quarantined": int(quarantined)}


def decide_proposal(proposal_id: str, actor: str, approve: bool, note: str = "") -> dict:
    with db.writing() as cur:
        rows = cur.execute("SELECT status, proposed_by, decided_by, contract_version FROM proposals WHERE proposal_id = ?",
                           [proposal_id]).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No proposal {proposal_id}.")
        status, proposed_by, decided_by, version = rows[0]
        action = "approve" if approve else "reject"
        if status != "pending":
            _refuse(cur, actor, action, proposal_id, 409,
                    f"{proposal_id} was already {status} by {decided_by}. A proposal is decided once.")
        if actor.strip().lower() == str(proposed_by).lower() or actor.strip().lower() in SERVICE_IDENTITIES:
            _refuse(cur, actor, action, proposal_id, 403,
                    f"{actor} proposed {proposal_id}, or is an automation, and cannot also decide it. Someone else has to.")
        now = _now()
        cur.execute("UPDATE proposals SET status = ?, decided_by = ?, decided_at = ?, decision_note = ? WHERE proposal_id = ?",
                    ["approved" if approve else "rejected", actor, now, note, proposal_id])
        if not approve:
            _audit(cur, actor, "reject", proposal_id, "done", note or "rejected")
            return {"proposal_id": proposal_id, "status": "rejected"}

        before = _snapshot(cur)
        approved = approved_contracts(cur)
        w0 = time.perf_counter()
        result = run_pipeline(settings.raw_dir, approved=approved)
        ablation = run_ablation(settings.raw_dir, result, approved)
        wall_ms = (time.perf_counter() - w0) * 1000
        n = int(cur.execute("SELECT count(*) FROM runs").fetchall()[0][0]) + 1
        run = {"run_id": f"RUN-{n:04d}", "kind": "reprocess", "trigger": f"{proposal_id} approved by {actor}",
               "started_at": now, "git_sha": settings.git_sha, "approved": sorted(approved), "wall_ms": round(wall_ms, 1)}
        persist_governed(cur, result, run, load_truth(settings.truth_path), settings.raw_dir)
        replace(cur, "ablation", ablation)
        after = _snapshot(cur)
        _audit(cur, actor, "approve", proposal_id, "done", {"run_id": run["run_id"], "contract": version,
                                                           "before": before, "after": after})
        return {"proposal_id": proposal_id, "status": "approved", "run_id": run["run_id"], "wall_ms": run["wall_ms"],
                "before": before, "after": after}


def reset(actor: str) -> dict:
    db.reset_to_build()
    with db.writing() as cur:
        _audit(cur, actor, "reset", "platform", "done", "restored the built state")
    return {"status": "reset"}
