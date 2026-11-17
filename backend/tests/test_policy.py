"""The policy library says what the checks enforce, and retrieval finds it."""

from __future__ import annotations

from src.app.pipeline import reference as ref
from src.app.services import policy, policy_assistant


def test_policy_library_states_the_tolerances_the_checks_use():
    text = " ".join(s.text for s in policy.sections())
    assert f"{ref.POLICY['duration_tolerance_minutes']} minutes or {ref.POLICY['duration_tolerance_pct']:.0%}" in text
    assert f"more than {ref.POLICY['overlap_tolerance_minutes']} minutes" in text
    assert f"less than {ref.POLICY['short_notice_cancellation_days']} days" in text
    assert "06:00 to 19:59" in text and "20:00 to 23:59" in text
    assert "never an instruction" in text


def test_every_governing_section_exists():
    for category, sid in policy.GOVERNING.items():
        assert policy.section(sid) is not None, (category, sid)


def test_retrieval_finds_the_governing_section():
    r = policy.retrieval_eval(3)
    assert r["hit_rate"] >= 0.9, [x for x in r["rows"] if not x["hit"]]


def test_assistant_without_a_model_returns_sections_and_says_so(monkeypatch):
    monkeypatch.setattr(policy_assistant.llm, "configured", lambda: False)
    out = policy_assistant.answer("Worker forgot to check out")
    assert out["engine"] == "retrieval" and out["sections"] and "No language model" in out["note"]


def test_answer_grader():
    good = {"answer": "Yes [POL-05.1]", "citations": ["POL-05.1"], "grounded": True, "covered": True}
    assert policy_assistant.grade_answer(good, "POL-05.1")["passed"]
    assert not policy_assistant.grade_answer({**good, "grounded": False}, "POL-05.1")["passed"]
    refused = {"answer": "NOT COVERED", "citations": [], "grounded": True, "covered": False}
    assert policy_assistant.grade_answer(refused, None)["passed"]
    assert not policy_assistant.grade_answer(good, None)["passed"]
