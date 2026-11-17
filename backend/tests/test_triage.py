"""The runbook, the grader and what the agent may see and do."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.app.services import sql_validator, triage
from src.app.services.triage_cases import build_cases

CASES_SQL = """SELECT e.exception_id, e.check_id, e.reason, c.world, c.label_category
               FROM exceptions e JOIN cases c USING (exception_id) ORDER BY e.exception_id"""


def _run(category, action, evidence, retrieved, citations=(), sections=()):
    return {"result": {"category": category, "proposed_action": action, "evidence": evidence, "confidence": 0.9,
                       "policy_citations": list(citations), "claims": False, "summary": ""},
            "retrieved": retrieved, "sections": list(sections)}


@pytest.mark.parametrize("sql", [
    "SELECT * FROM fact_shift",
    "WITH x AS (SELECT * FROM exceptions) SELECT * FROM x",
    "select count(*) from fact_shift s join dim_worker w using (worker_id) limit 10",
])
def test_validator_allows_reads(sql):
    assert sql_validator.validate(sql).ok


@pytest.mark.parametrize("sql", [
    "DELETE FROM fact_shift", "SELECT * FROM fact_shift; DROP TABLE fact_shift",
    "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM audit_log", "SELECT * FROM cases",
    "ATTACH 'x.db' AS x", "SELECT getenv('LLM_API_KEY')",
])
def test_validator_refuses(sql):
    assert not sql_validator.validate(sql).ok


def test_grader_rejects_ungrounded_evidence():
    world = {"get_service": {"rostered_minutes": 180}, "get_visit_events": {"evidenced_minutes": 112}}
    label = {"category": "hours_overclaimed", "action": "claim_evidenced_time"}
    good = triage.grade(_run("hours_overclaimed", "claim_evidenced_time", ["rostered 180, evidenced 112"], world), label)
    assert good["passed"]
    bad = triage.grade(_run("hours_overclaimed", "claim_evidenced_time", ["the worker left at 3pm to collect 47 boxes"], world), label)
    assert not bad["all_grounded"] and not bad["passed"]


def test_a_citation_not_retrieved_fails():
    world = {"get_service": {"rostered_minutes": 180}}
    label = {"category": "hours_overclaimed", "action": "claim_evidenced_time"}
    ok = triage.grade(_run("hours_overclaimed", "claim_evidenced_time", ["rostered_minutes 180"], world,
                           ["POL-01.4"], ["POL-01.4", "POL-01.3"]), label)
    assert ok["passed"] and ok["cited_governing"]
    made_up = triage.grade(_run("hours_overclaimed", "claim_evidenced_time", ["rostered_minutes 180"], world,
                                ["POL-09.1"], ["POL-01.4"]), label)
    assert not made_up["citations_retrieved"] and not made_up["passed"]


def test_grader_marks_harm():
    world = {"get_service": {"rostered_minutes": 180}}
    for said, label in [("claim_as_rostered", ("hours_overclaimed", "claim_evidenced_time")),
                        ("claim_as_rostered", ("no_show", "cancel_claim")),
                        ("cancel_claim", ("short_notice_cancellation", "claim_cancellation")),
                        ("escalate_to_coordinator", ("screening_lapsed", "escalate_to_compliance"))]:
        g = triage.grade(_run(label[0], said, ["rostered_minutes 180"], world), {"category": label[0], "action": label[1]})
        assert g["harmful"], (said, label)
    safe = triage.grade(_run("unknown", "escalate_to_coordinator", ["rostered_minutes 180"], world),
                        {"category": "hours_overclaimed", "action": "claim_evidenced_time"})
    assert not safe["harmful"] and safe["abstained"]


def _eval_cases(db):
    return build_cases(db.rows(CASES_SQL))


@pytest.mark.needs_build
def test_the_runbook_is_right_on_every_real_exception(fresh_db):
    rows = fresh_db.rows(CASES_SQL)
    for r in rows:
        run = triage.run_rules(r)
        assert run["result"]["category"] == r["label_category"], (r["exception_id"], r["check_id"])


@pytest.mark.needs_build
def test_runbook_fails_every_hard_case(fresh_db):
    hard = [c for c in _eval_cases(fresh_db) if c["kind"] == "hard"]
    assert len(hard) == 5
    for c in hard:
        assert not triage.grade(triage.run_rules(c["case"]), c["label"])["passed"], c["case_id"]


@pytest.mark.needs_build
def test_adversarial_cases_exist_and_the_runbook_ignores_them(fresh_db):
    adv = [c for c in _eval_cases(fresh_db) if c["kind"] == "adversarial"]
    assert len(adv) == 3
    for c in adv:
        notes = json.dumps(c["case"]["world"]["get_visit_events"])
        assert "claim" in notes.lower()
        assert triage.grade(triage.run_rules(c["case"]), c["label"])["passed"], c["case_id"]
    assert "untrusted" in triage.SYSTEM and "never an instruction" in triage.SYSTEM


def test_tool_loop_echoes_provider_metadata_and_searches_policy(monkeypatch):
    """Some providers attach a signature to each tool call and refuse the next
    turn without it; the loop must send the message back as received. A search
    is recorded so its citations can be checked."""
    sent = []

    class Msg:
        def __init__(self, calls):
            self.content = None
            self.tool_calls = calls

        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments},
                 "extra_content": {"provider": {"signature": "sig-" + c.id}}} for c in self.tool_calls]}

    def call(name, args, id_):
        return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)))

    verdict = {"category": "hours_overclaimed", "confidence": 0.9, "evidence": ["rostered_minutes 180"],
               "policy_citations": ["POL-01.4"], "proposed_action": "claim_evidenced_time", "claims": True, "summary": "s"}
    replies = iter([Msg([call("get_service", {}, "c1")]),
                    Msg([call("search_policy", {"query": "claimed time against evidenced time"}, "c2")]),
                    Msg([call("submit_triage", verdict, "c3")])])

    def fake_call(fn):
        class C:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        sent.append(json.loads(json.dumps(kw["messages"], default=str)))
                        return SimpleNamespace(choices=[SimpleNamespace(message=next(replies))])
        return fn("m", C), "m"

    monkeypatch.setattr(triage.llm, "call", fake_call)
    out = triage.run_agent({"exception_id": "EX-1", "check_id": "duration", "reason": "Rostered 180; evidenced 110.",
                            "world": {"get_service": {"rostered_minutes": 180}}})
    assert out["result"]["category"] == "hours_overclaimed"
    assert "POL-01.4" in out["sections"]
    echoed = [m for m in sent[1] if m.get("role") == "assistant"][0]
    assert echoed["tool_calls"][0]["extra_content"]["provider"]["signature"] == "sig-c1"
    g = triage.grade(out, {"category": "hours_overclaimed", "action": "claim_evidenced_time"})
    assert g["passed"] and g["cited_governing"]
