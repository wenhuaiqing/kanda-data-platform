"""Governed access: who can see what, declared once, enforced by the database.

Each role is a schema of views over the gold tables. A query typed on the
Governed access page runs as one role and can name only that role's views -
the validator refuses anything else, and the views themselves carry the row
filter, so a clever query cannot widen it. The same filters are written as
the DAX row-level security a Power BI semantic model would carry.

Nobody's view has a personal column in it, because no gold table does: names,
dates of birth, phone numbers, addresses and NDIS numbers stay in the landing
zone. The triage agent is a role too, and the narrowest one.
"""

from __future__ import annotations

ROLES = {
    "coordinator_bn": {
        "label": "Coordinator, Brisbane North",
        "who": "Rosters and resolves held services for one region.",
        "rows": "Brisbane North only",
        "views": {
            "shifts": "SELECT shift_id, month, service_date, start_local, end_local, client_id, worker_id, funding, item_code, "
                      "time_band, kind, rostered_min, evidence, evidenced_min, status, check_id, amount FROM main.fact_shift "
                      "WHERE region = 'Brisbane North'",
            "exceptions": "SELECT exception_id, shift_id, service_date, client_id, worker_id, check_id, reason, amount "
                          "FROM main.exceptions WHERE region = 'Brisbane North'",
            "clients": "SELECT client_id, funding, age_band FROM main.dim_client WHERE region = 'Brisbane North'",
            "visit_notes": "SELECT e.shift_id, e.event_type, e.ts_local, e.note_masked FROM main.fact_visit_event e "
                           "JOIN main.fact_shift s USING (shift_id) WHERE s.region = 'Brisbane North' AND e.note_masked IS NOT NULL",
        },
        "dax": "[region] = \"Brisbane North\"",
    },
    "finance": {
        "label": "Finance (claiming)",
        "who": "Submits claims and reconciles what was paid.",
        "rows": "All regions; no visit notes",
        "views": {
            "claims": "SELECT shift_id, month, service_date, region, client_id, funding, item_code, time_band, rostered_min, "
                      "rate, price_limit, amount, status, check_id, claim_amount, at_risk FROM main.fact_shift",
            "exceptions": "SELECT exception_id, shift_id, month, region, check_id, amount, at_risk FROM main.exceptions",
            "plans": "SELECT plan_id, client_id, funding, start_date, end_date, budget_at_period_start, claimed_in_period, "
                     "management FROM main.dim_plan",
            "items": "SELECT * FROM main.dim_support_item",
        },
        "dax": "TRUE ()   -- all rows; the visit notes table is not in Finance's model",
    },
    "executive": {
        "label": "Executive",
        "who": "Reads the position by region and month.",
        "rows": "Aggregates only; no client or worker id",
        "views": {
            "summary": "SELECT month, region, funding, count(*) AS services, "
                       "count(*) FILTER (WHERE status = 'held') AS held, round(sum(claim_amount), 2) AS claimed, "
                       "round(sum(amount) FILTER (WHERE status = 'held'), 2) AS held_value "
                       "FROM main.fact_shift GROUP BY ALL",
        },
        "dax": "-- an aggregate table in the model; the shift-level table is hidden from this role",
    },
    "triage_agent": {
        "label": "Triage agent (service identity)",
        "who": "Reads one held service's snapshot at a time. Cannot write.",
        "rows": "Held services only, through six tools",
        "views": {
            "cases": "SELECT exception_id, shift_id, world FROM main.cases",
        },
        "dax": "-- not a Power BI user",
    },
}

QUERYABLE_ROLES = ["coordinator_bn", "finance", "executive"]


def create_views(con) -> None:
    for role, spec in ROLES.items():
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {role}")
        for name, sql in spec["views"].items():
            con.execute(f"CREATE OR REPLACE VIEW {role}.{name} AS {sql}")


def allowed_tables(role: str) -> set[str]:
    return {f"{role}.{name}" for name in ROLES[role]["views"]}
