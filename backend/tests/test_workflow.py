"""Governed writes: token-gated, audit-logged, refused when the rule says no."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.needs_build

H = {"X-Write-Token": "test-token", "X-Actor": "Coordinator BN"}


def _held(db, check):
    return db.scalar("SELECT exception_id FROM exceptions WHERE check_id = ? ORDER BY exception_id LIMIT 1", [check])


def test_writes_need_the_token(client, fresh_db):
    ex = _held(fresh_db, "price")
    r = client.post(f"/api/exceptions/{ex}/decide", json={"action": "reprice_to_limit", "note": "x"})
    assert r.status_code == 401
    assert client.post("/api/proposals/PRP-0001/approve", json={}).status_code == 401


def test_the_agent_identity_cannot_decide(client, fresh_db):
    ex = _held(fresh_db, "price")
    r = client.post(f"/api/exceptions/{ex}/decide", json={"action": "reprice_to_limit", "note": "x"},
                    headers={**H, "X-Actor": "triage-agent"})
    assert r.status_code == 403
    assert fresh_db.scalar("SELECT count(*) FROM audit_log WHERE outcome = 'refused'") == 1


def test_screening_hold_only_escalates(client, fresh_db):
    ex = _held(fresh_db, "screening")
    r = client.post(f"/api/exceptions/{ex}/decide", json={"action": "claim_as_rostered", "note": "renewal in progress"},
                    headers=H)
    assert r.status_code == 409
    ok = client.post(f"/api/exceptions/{ex}/decide", json={"action": "escalate_to_compliance"}, headers=H)
    assert ok.status_code == 200


def test_no_evidence_cannot_be_claimed(client, fresh_db):
    ex = fresh_db.scalar("""SELECT exception_id FROM exceptions WHERE check_id = 'evidence'
                            AND reason LIKE 'No check-in%' ORDER BY exception_id LIMIT 1""")
    r = client.post(f"/api/exceptions/{ex}/decide", json={"action": "claim_as_rostered", "note": "worker said so"},
                    headers=H)
    assert r.status_code == 409


def test_decided_once_and_claims_need_a_note(client, fresh_db):
    ex = _held(fresh_db, "price")
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "reprice_to_limit"}, headers=H).status_code == 400
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "reprice_to_limit", "note": "roster rate fixed"},
                       headers=H).status_code == 200
    assert client.post(f"/api/exceptions/{ex}/decide", json={"action": "cancel_claim", "note": "x"},
                       headers=H).status_code == 409


def test_proposer_cannot_approve(client, fresh_db):
    r = client.post("/api/proposals/PRP-0001/approve", json={}, headers={**H, "X-Actor": "contract-monitor"})
    assert r.status_code == 403
    assert fresh_db.scalar("SELECT status FROM proposals WHERE proposal_id = 'PRP-0001'") == "pending"


def test_approval_reprocesses_from_the_landing_zone(client, fresh_db):
    before = fresh_db.scalar("SELECT count(*) FROM fact_shift WHERE status = 'held'")
    preview = fresh_db.rows("SELECT preview FROM proposals WHERE proposal_id = 'PRP-0001'")[0]["preview"]
    r = client.post("/api/proposals/PRP-0001/approve", json={"note": "vendor confirmed the change"},
                    headers={**H, "X-Actor": "Data platform lead"})
    assert r.status_code == 200, r.text
    body = r.json()
    after = fresh_db.scalar("SELECT count(*) FROM fact_shift WHERE status = 'held'")
    import json
    assert before - after == json.loads(preview)["services_released"] - json.loads(preview)["new_holds"]
    assert body["after"]["held"] == after
    assert fresh_db.scalar("SELECT count(*) FROM runs") == 2
    assert fresh_db.scalar("SELECT count(*) FROM uat_results WHERE NOT passed") == 0
    # The replay now reproduces the reprocessed state, not the original one.
    assert client.post("/api/replay").json()["all_match"]
    assert client.post("/api/proposals/PRP-0001/approve", json={}, headers={**H, "X-Actor": "Someone else"}).status_code == 409
