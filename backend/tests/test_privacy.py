"""Personal information stays in the landing zone; roles see their rows only."""

from __future__ import annotations

import csv
import json
import re

import pytest

from src.app.pipeline import access
from src.app.services import sql_validator
from src.app.services.triage_cases import build_cases
from tests.conftest import RAW

pytestmark = pytest.mark.needs_build


def _clients():
    with (RAW / "crm" / "clients.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _personal_strings():
    rows = _clients()
    return ({r["family_name"] for r in rows} | {r["phone"] for r in rows} | {r["ndis_number"] for r in rows if r["ndis_number"]}
            | {r["address"] for r in rows})


def test_no_personal_column_in_any_governed_table(fresh_db):
    cols = {r["column_name"] for r in fresh_db.rows("SELECT column_name FROM information_schema.columns")}
    assert not cols & {"given_name", "family_name", "date_of_birth", "phone", "address", "ndis_number", "screening_id"}


def test_no_note_in_gold_carries_pii(governed, truth):
    notes = [n for n in governed.tables["fact_visit_event"]["note_masked"] if isinstance(n, str)]
    personal = _personal_strings()
    assert notes
    for n in notes:
        assert not re.search(r"\(0\d\)\s?\d{4}\s?\d{4}|\b\d{9}\b", n), n
        assert not any(p in n for p in personal), n
    seeded_pii = sum(1 for sid in truth if truth[sid] is not None)
    assert seeded_pii
    assert governed.tables["fact_visit_event"]["pii_found"].notna().sum() >= 70


def test_snapshots_carry_no_personal_information(fresh_db):
    personal = _personal_strings() | {r["given_name"] + " " + r["family_name"] for r in _clients()}
    worlds = [r["world"] for r in fresh_db.rows("SELECT world FROM cases")]
    assert worlds
    for w in worlds:
        assert not any(p in w for p in personal)
    rows = fresh_db.rows("""SELECT e.exception_id, e.check_id, e.reason, c.world, c.label_category
                            FROM exceptions e JOIN cases c USING (exception_id) ORDER BY e.exception_id""")
    for c in build_cases(rows):
        assert not any(p in json.dumps(c["case"]["world"]) for p in personal), c["case_id"]


def test_role_views_filter_rows(fresh_db):
    assert fresh_db.scalar("SELECT count(*) FROM coordinator_bn.shifts") > 0
    assert fresh_db.scalar("""SELECT count(*) FROM coordinator_bn.shifts v JOIN fact_shift s USING (shift_id)
                              WHERE s.region <> 'Brisbane North'""") == 0
    assert fresh_db.scalar("SELECT count(*) FROM coordinator_bn.shifts") == \
        fresh_db.scalar("SELECT count(*) FROM fact_shift WHERE region = 'Brisbane North'")
    cols = {r["column_name"] for r in fresh_db.rows(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'finance'")}
    assert "note_masked" not in cols
    exec_cols = {r["column_name"] for r in fresh_db.rows(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'executive'")}
    assert not exec_cols & {"client_id", "worker_id", "shift_id"}


def test_a_role_cannot_query_another_roles_views():
    bn = access.allowed_tables("coordinator_bn")
    assert sql_validator.validate("SELECT * FROM coordinator_bn.shifts", bn).ok
    for sql in ("SELECT * FROM fact_shift", "SELECT * FROM finance.claims", "SELECT * FROM main.fact_shift",
                "SELECT * FROM coordinator_bn.shifts s JOIN dim_client c USING (client_id)",
                "SELECT * FROM information_schema.tables", "SELECT * FROM triage_agent.cases"):
        assert not sql_validator.validate(sql, bn).ok, sql
    assert not sql_validator.validate("SELECT * FROM cases").ok
