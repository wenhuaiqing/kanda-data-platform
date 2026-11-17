"""Anonymous actions that cost something: the re-run from the landing zone,
triage, the policy assistant, ad hoc queries as a role. Rate-limited, never
state-changing beyond their own log."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.app.pipeline import access
from src.app.services import db, llm, policy, policy_assistant, replay, sql_validator, triage
from src.app.services.rate_limit import limit_replay, limit_triage

router = APIRouter(prefix="/api", tags=["actions"])


@router.post("/replay", dependencies=[Depends(limit_replay)])
async def run_replay() -> dict:
    return await asyncio.to_thread(replay.replay)


class TriageRequest(BaseModel):
    exception_id: str = Field(max_length=20)
    engine: str = Field(default="agent", pattern="^(agent|rules)$")


def _triage(exception_id: str, engine: str) -> dict:
    rows = db.rows("""SELECT e.exception_id, e.check_id, e.reason, c.world, c.label_category, c.label_action
                      FROM exceptions e JOIN cases c USING (exception_id) WHERE exception_id = ?""", [exception_id])
    if not rows:
        raise HTTPException(status_code=404, detail=f"No held service {exception_id}.")
    case = rows[0]
    fallback_reason = None
    if engine == "agent" and llm.configured():
        try:
            run = triage.run_agent(case)
        except Exception as exc:  # noqa: BLE001 - degrade visibly, never silently
            fallback_reason = f"The agent could not finish ({type(exc).__name__}); the runbook answered instead."
            run = triage.run_rules(case)
    elif engine == "agent":
        fallback_reason = "No language model is configured on this deployment; the runbook answered instead."
        run = triage.run_rules(case)
    else:
        run = triage.run_rules(case)
    label = {"category": case["label_category"], "action": case["label_action"]}
    grade = triage.grade(run, label)
    run_id = f"TR-{int(time.time() * 1000) % 10**10:010d}"
    with db.writing() as cur:
        cur.execute("INSERT INTO triage_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            run_id, datetime.now().replace(microsecond=0), exception_id, run["engine"], run["model"], run["ms"],
            run["steps"], json.dumps(run["result"]), json.dumps(grade), json.dumps(run["trace"], default=str)])
    return {"run_id": run_id, **{k: run[k] for k in ("engine", "model", "result", "trace", "steps", "ms")},
            "grade": grade, "label": label, "fallback_reason": fallback_reason}


@router.post("/triage/run", dependencies=[Depends(limit_triage)])
async def triage_run(body: TriageRequest) -> dict:
    return await asyncio.to_thread(_triage, body.exception_id, body.engine)


class QueryRequest(BaseModel):
    sql: str = Field(max_length=4000)
    role: str = Field(default="data_team", max_length=30)


QUERY_TIMEOUT_SECONDS = 5.0


def _run_query(sql: str, role: str) -> dict:
    if role == "data_team":
        allowed = None
    elif role in access.QUERYABLE_ROLES:
        allowed = access.allowed_tables(role)
    else:
        raise HTTPException(status_code=400, detail=f"{role} is not a role that can run queries here.")
    verdict = sql_validator.validate(sql, allowed)
    if not verdict.ok:
        raise HTTPException(status_code=400, detail=" ".join(verdict.errors))
    cur = db.connection().cursor()
    timer = threading.Timer(QUERY_TIMEOUT_SECONDS, cur.interrupt)
    t0 = time.perf_counter()
    timer.start()
    try:
        df = cur.execute(verdict.sql).df()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).split("\n")[0][:300]
        if "INTERRUPT" in msg.upper():
            msg = f"Stopped after {QUERY_TIMEOUT_SECONDS:.0f} s."
        raise HTTPException(status_code=400, detail=msg) from exc
    finally:
        timer.cancel()
        cur.close()
    return {"role": role, "sql": verdict.sql, "tables": verdict.tables, "columns": list(df.columns),
            "rows": db.records(df), "ms": round((time.perf_counter() - t0) * 1000, 1)}


@router.post("/query")
async def query(body: QueryRequest) -> dict:
    return await asyncio.to_thread(_run_query, body.sql, body.role)


class PolicyRequest(BaseModel):
    question: str = Field(min_length=3, max_length=400)


@router.post("/policy/search")
async def policy_search(body: PolicyRequest) -> dict:
    return {"question": body.question, "results": policy.search(body.question, 5)}


def _ask(question: str) -> dict:
    try:
        result = policy_assistant.answer(question)
    except Exception as exc:  # noqa: BLE001 - degrade visibly
        hits = policy.search(question, 3)
        result = {"engine": "retrieval", "model": None, "answer": None, "citations": [], "sections": hits,
                  "grounded": True, "covered": bool(hits), "ms": 0,
                  "note": f"The model could not answer ({type(exc).__name__}); these are the sections retrieval found."}
    with db.writing() as cur:
        cur.execute("INSERT INTO policy_answers VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            datetime.now().replace(microsecond=0), question, result["engine"], result["model"],
            ",".join(h["section_id"] for h in result["sections"]), ",".join(result["citations"]), result["grounded"],
            result["ms"]])
    return result


@router.post("/policy/ask", dependencies=[Depends(limit_triage)])
async def policy_ask(body: PolicyRequest) -> dict:
    return await asyncio.to_thread(_ask, body.question)
