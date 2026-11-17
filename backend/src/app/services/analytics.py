"""Read models, one per page. SQL lives here; routers stay thin."""

from __future__ import annotations

import csv
import json
from functools import lru_cache

from src.app.pipeline import access, delivery
from src.app.pipeline import reference as ref
from src.app.pipeline.cases import TOOL_NAMES
from src.app.pipeline.stages import contract
from src.app.services import db, llm, policy
from src.settings import REPO_ROOT, settings

EVAL_STATUS = REPO_ROOT / "evals" / "status.json"
FEEDS = ["crm.clients", "crm.plans", "hr.workers", "catalogue.price_guide", "rostering.shifts", "mobile.visit_events"]

CHECKS = [
    {"id": "identity", "label": "Client identity", "what": "The roster's client id is on the client master.", "held": "A proposed match to the one regular client who fits, or a coordinator."},
    {"id": "evidence", "label": "Evidence of delivery", "what": "One check-in and one check-out from the worker's phone.", "held": "Cancelled if never delivered; confirmed with the worker if not closed; never claimed on the roster alone."},
    {"id": "screening", "label": "Worker screening", "what": "The worker's screening was current on the date of service.", "held": "Escalated to compliance. Cannot be claimed from the queue by anyone."},
    {"id": "overlap", "label": "One place at a time", "what": "The worker is not checked in at two clients for more than 15 minutes.", "held": "To the coordinator to establish what happened."},
    {"id": "plan_dates", "label": "Funding in force", "what": "The service is inside the client's plan or agreement.", "held": "Until the new plan is loaded."},
    {"id": "item", "label": "Right item", "what": "The item's funding and time band match the client and the shift's start.", "held": "Repriced to the right item."},
    {"id": "price", "label": "Price limit", "what": "The rate is no more than the item's price limit.", "held": "Repriced to the limit; roster rate corrected."},
    {"id": "duration", "label": "Time evidenced", "what": "Rostered time exceeds evidenced time by no more than 15 minutes or 10%.", "held": "Claimed for the evidenced time unless the coordinator records why not."},
    {"id": "budget", "label": "Budget left", "what": "The claim is within what is left of the client's budget.", "held": "To the plan review."},
]

TABLES = [
    {"name": "raw_files", "layer": "Bronze", "what": "Every file as landed, by feed: rows, bytes and SHA-256. Personal data stays here."},
    {"name": "quarantine", "layer": "Bronze", "what": "Every row that broke its feed's contract, with the rule. Never dropped, never fixed."},
    {"name": "event_duplicates", "layer": "Silver", "what": "Every phone event removed as a copy, and the event it copied."},
    {"name": "fact_visit_event", "layer": "Silver", "what": "Phone events, de-duplicated, local time, notes masked, lateness measured."},
    {"name": "dim_client", "layer": "Gold", "what": "Clients by id: region, funding, age band. No name, birth date, phone, address or NDIS number."},
    {"name": "dim_worker", "layer": "Gold", "what": "Workers by id: region, employment, screening expiry."},
    {"name": "dim_plan", "layer": "Gold", "what": "Plans and agreements: dates, budget at the period's start, claimed in the period."},
    {"name": "dim_support_item", "layer": "Gold", "what": "The support catalogue and price limits (synthetic)."},
    {"name": "fact_shift", "layer": "Gold", "what": "One row per roster entry: evidence, checks, status, claim."},
    {"name": "exceptions", "layer": "Gold", "what": "Held services with the reason and the value at risk."},
    {"name": "partition_hashes", "layer": "Control", "what": "SHA-256 of every governed partition, by run."},
    {"name": "runs", "layer": "Control", "what": "Every build and reprocess: trigger, time, cost, output digest."},
    {"name": "run_stages", "layer": "Control", "what": "Rows in, out and held for each stage of each run."},
    {"name": "ablation", "layer": "Control", "what": "Each control switched off and the quarter re-run."},
    {"name": "uat_results", "layer": "Control", "what": "Acceptance scenarios and what each query returned."},
]

# How each piece here maps onto Microsoft Fabric. The advertisement describes a
# Fabric Lakehouse; nothing here claims to know how it is set up.
FABRIC = [
    {"here": "data/raw/ (landing zone, by source system)", "fabric": "Lakehouse Files, one folder per source; OneLake shortcuts where a source already lands in ADLS"},
    {"here": "contracts/*.yaml, quarantine table", "fabric": "Contracts in the repository, enforced in a notebook step; quarantine as a Delta table in the Lakehouse"},
    {"here": "stages.py (land, contracts, conform, evidence, checks, publish)", "fabric": "Notebooks (PySpark) orchestrated by a Data pipeline on a schedule per feed"},
    {"here": "gold tables in DuckDB", "fabric": "Delta tables in the Lakehouse; the SQL analytics endpoint for ad hoc SQL"},
    {"here": "role views (coordinator_bn, finance, executive)", "fabric": "OneLake security / SQL endpoint object and row security, and RLS roles in the semantic model"},
    {"here": "semantic/measures.yaml (SQL and DAX)", "fabric": "A Direct Lake semantic model with the same measures; Power BI reports on it"},
    {"here": "partition digests, replay, build manifest", "fabric": "The same digests written by the notebook; Git integration and deployment pipelines for promotion"},
    {"here": "Container Apps for the API and agent", "fabric": "Unchanged: the agent and its API sit beside Fabric and read the SQL endpoint as a service principal"},
]


def eval_status() -> dict | None:
    return json.loads(EVAL_STATUS.read_text(encoding="utf-8")) if EVAL_STATUS.exists() else None


def headline() -> dict:
    r = db.rows("""SELECT count(*) AS services,
                          count(*) FILTER (WHERE status = 'claimable') AS claimable,
                          count(*) FILTER (WHERE status = 'claimable_cancellation') AS cancellations_claimable,
                          count(*) FILTER (WHERE status = 'not_claimable') AS cancelled_with_notice,
                          count(*) FILTER (WHERE status = 'held') AS held,
                          sum(claim_amount) AS claim_value, sum(amount) FILTER (WHERE status = 'held') AS held_value,
                          sum(at_risk) FILTER (WHERE status = 'held') AS at_risk,
                          count(DISTINCT client_id) FILTER (WHERE client_id IN (SELECT client_id FROM dim_client)) AS clients,
                          count(DISTINCT worker_id) AS workers
                   FROM fact_shift""")[0]
    considered = r["services"] - r["cancelled_with_notice"]
    r["straight_through"] = (r["claimable"] + r["cancellations_claimable"]) / considered if considered else 0
    r["quarantined"] = db.scalar("SELECT count(*) FROM quarantine")
    r["duplicates"] = db.scalar("SELECT count(*) FROM event_duplicates")
    r["events"] = db.scalar("SELECT count(*) FROM fact_visit_event")
    r["notes_masked"] = db.scalar("SELECT count(*) FROM fact_visit_event WHERE pii_found IS NOT NULL")
    r["decided"] = db.scalar("SELECT count(*) FROM exception_decisions d JOIN exceptions e USING (exception_id)")
    return r


def by_check() -> list[dict]:
    return db.rows("""SELECT check_id, count(*) AS held, round(sum(at_risk), 2) AS at_risk,
                             round(sum(amount), 2) AS value FROM exceptions GROUP BY 1 ORDER BY 2 DESC""")


def proposals() -> list[dict]:
    out = db.rows("SELECT * FROM proposals ORDER BY proposal_id")
    for p in out:
        p["evidence"], p["preview"] = json.loads(p["evidence"]), json.loads(p["preview"])
    return out


def overview() -> dict:
    ev = eval_status()
    uat = db.rows("SELECT count(*) AS n, count(*) FILTER (WHERE passed) AS passed FROM uat_results")[0]
    rev = policy.retrieval_eval()
    return {
        "headline": headline(), "by_check": by_check(),
        "by_month": db.rows("""SELECT month, count(*) AS services, count(*) FILTER (WHERE status LIKE 'claimable%') AS claimable,
                                      count(*) FILTER (WHERE status = 'held') AS held, round(sum(claim_amount)) AS claimed
                               FROM fact_shift GROUP BY 1 ORDER BY 1"""),
        "by_region": db.rows("""SELECT region, count(*) AS services, count(*) FILTER (WHERE status = 'held') AS held,
                                       round(sum(claim_amount)) AS claimed FROM fact_shift WHERE region IS NOT NULL
                                GROUP BY 1 ORDER BY 1"""),
        "roadmap": delivery.load("delivery/roadmap.yaml")["initiatives"],
        "proposals": [{k: p[k] for k in ("proposal_id", "title", "status")} for p in proposals()],
        "uat": uat, "eval": ev["summary"] if ev else None, "period": ref.PERIOD_LABEL,
        "retrieval": {k: rev[k] for k in ("k", "questions", "hits", "hit_rate", "mrr")},
    }


def _contract_view(feed: str, approved: set[str]) -> dict:
    c = contract(feed)
    versions = []
    for v in c["versions"]:
        status = v["status"]
        if status == "proposed" and f"{feed}@{v['version']}" in approved:
            status = "approved (by proposal)"
        versions.append({"version": v["version"], "status": status, "effective_from": str(v.get("effective_from")),
                         "approved_by": v.get("approved_by"), "reason": v.get("reason"),
                         "mappings": v.get("mappings"), "fields": v.get("fields")})
    fields = next(v["fields"] for v in c["versions"] if v.get("fields"))
    return {"id": feed, "source": c["source"], "owner": c["owner"], "steward": c.get("steward"), "vendor": c.get("vendor"),
            "schedule": c["schedule"], "freshness_hours": c.get("freshness_hours"), "key": c["key"],
            "consumers": c.get("consumers", []), "classification": c.get("classification"),
            "rules": c.get("rules", []), "versions": versions,
            "fields": [{"name": k, **{x: v.get(x) for x in ("type", "required", "class")}} for k, v in fields.items()]}


def sources() -> dict:
    approved = {r["contract_version"] for r in db.rows("SELECT contract_version FROM proposals WHERE status = 'approved'")}
    files = db.rows("SELECT feed, count(*) AS files, sum(rows) AS rows, sum(bytes) AS bytes FROM raw_files GROUP BY 1")
    q = db.rows("""SELECT feed, rule, app_version, count(*) AS rows, min(detail) AS example
                   FROM quarantine GROUP BY 1, 2, 3 ORDER BY 4 DESC""")
    lag = db.rows("""SELECT app_version, count(*) AS events,
                            quantile_cont(lag_minutes, 0.5) AS p50_min, quantile_cont(lag_minutes, 0.95) AS p95_min,
                            max(lag_minutes) AS max_min, count(*) FILTER (WHERE after_cutoff) AS after_cutoff
                     FROM fact_visit_event GROUP BY 1 ORDER BY 1""")
    by_day = db.rows("""SELECT CAST(ts_local AS DATE) AS day, count(*) AS events,
                               count(*) FILTER (WHERE after_cutoff) AS late FROM fact_visit_event GROUP BY 1 ORDER BY 1""")
    return {
        "contracts": [_contract_view(f, approved) for f in FEEDS], "files": files, "quarantine": q,
        "quarantine_sample": db.rows("SELECT * FROM quarantine ORDER BY feed DESC, raw_row LIMIT 8"),
        "lag": lag, "by_day": by_day,
        "duplicates": db.rows("SELECT reason, count(*) AS events FROM event_duplicates GROUP BY 1 ORDER BY 2 DESC"),
        "proposals": proposals(), "vendor_release": {"date": ref.VENDOR_RELEASE_DATE.isoformat(),
                                                     "version": ref.VENDOR_RELEASE_VERSION},
        "cutoff_hour": ref.POLICY["evidence_cutoff_hour"],
    }


def lakehouse() -> dict:
    counts = {t["name"]: db.scalar(f"SELECT count(*) FROM {t['name']}") for t in TABLES}
    latest = db.scalar("SELECT max(run_id) FROM runs")
    return {
        "files": db.rows("SELECT * FROM raw_files ORDER BY file"),
        "tables": [{**t, "rows": counts[t["name"]]} for t in TABLES],
        "stages": db.rows("SELECT * FROM run_stages WHERE run_id = ? ORDER BY seq", [latest]),
        "run": db.rows("SELECT * FROM runs WHERE run_id = ?", [latest])[0],
        "partitions": db.rows("SELECT * FROM partition_hashes WHERE run_id = ? ORDER BY partition", [latest]),
        "checks": CHECKS, "by_check": by_check(), "fabric": FABRIC,
        "samples": db.rows("""SELECT shift_id, status, check_id, kind FROM fact_shift
                              WHERE shift_id IN (SELECT min(shift_id) FROM fact_shift GROUP BY coalesce(check_id, kind))
                              ORDER BY shift_id"""),
    }


@lru_cache(maxsize=64)
def _roster_row(file: str, raw_row: int) -> dict | None:
    path = settings.raw_dir / file
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as fh:
        for i, r in enumerate(csv.DictReader(fh), start=1):
            if i == raw_row:
                return r
    return None


def lineage(shift_id: str) -> dict:
    s = db.rows("SELECT * FROM fact_shift WHERE shift_id = ?", [shift_id])
    if not s:
        q = db.rows("SELECT * FROM quarantine WHERE record_key = ?", [shift_id])
        if q:
            return {"shift": None, "quarantined": q[0], "roster_row": _roster_row(q[0]["file"], int(q[0]["raw_row"])),
                    "events": [], "events_quarantined": [], "duplicates": [], "exception": None, "file": None}
        raise ValueError(f"No service {shift_id}.")
    s = s[0]
    file = db.rows("SELECT * FROM raw_files WHERE file = ?", [s["file"]])[0]
    events = db.rows("""SELECT event_id, event_type, ts_local, received_at, lag_minutes, after_cutoff, app_version, mapped_v2,
                               note_masked, pii_found, file, raw_row FROM fact_visit_event WHERE shift_id = ? ORDER BY ts_local""",
                     [shift_id])
    ids = [e["event_id"] for e in events]
    dups = db.rows("SELECT * FROM event_duplicates WHERE kept_event_id IN (SELECT unnest(?))", [ids]) if ids else []
    q_events: list = []
    world = db.rows("SELECT world FROM cases WHERE shift_id = ?", [shift_id])
    if world:
        q_events = json.loads(world[0]["world"])["get_visit_events"]["quarantined"]
    return {"shift": s, "file": file, "roster_row": _roster_row(s["file"], int(s["raw_row"])), "events": events,
            "events_quarantined": q_events, "duplicates": dups,
            "exception": (db.rows("SELECT * FROM exceptions WHERE shift_id = ?", [shift_id]) or [None])[0]}


def exceptions() -> dict:
    return {
        "headline": headline(), "by_check": by_check(), "checks": CHECKS, "proposals": proposals(),
        "rows": db.rows("""SELECT e.*, c.label_category, d.action AS decided_action, d.actor AS decided_by, d.decided_at
                           FROM exceptions e JOIN cases c USING (exception_id)
                           LEFT JOIN exception_decisions d USING (exception_id) ORDER BY e.at_risk DESC, e.exception_id"""),
    }


def exception_detail(exception_id: str) -> dict:
    rows = db.rows("""SELECT e.*, c.world, c.label_category, c.label_action, c.label_detail
                      FROM exceptions e JOIN cases c USING (exception_id) WHERE exception_id = ?""", [exception_id])
    if not rows:
        raise ValueError(f"No held service {exception_id}.")
    e = rows[0]
    e["world"] = json.loads(e["world"])
    gov = policy.GOVERNING.get(e["label_category"])
    sec = policy.section(gov) if gov else None
    return {**lineage(e["shift_id"]), "exception": e,
            "policy": {"section_id": sec.section_id, "policy": sec.doc_title, "heading": sec.heading, "text": sec.text}
            if sec else None,
            "decision": (db.rows("SELECT * FROM exception_decisions WHERE exception_id = ?", [exception_id]) or [None])[0]}


def triage_page() -> dict:
    return {
        "cases": db.rows("""SELECT e.exception_id, e.check_id, e.region, e.reason, e.amount, e.at_risk,
                                   c.label_category, c.label_action
                            FROM exceptions e JOIN cases c USING (exception_id) ORDER BY e.check_id, e.exception_id"""),
        "eval": eval_status(), "llm_configured": llm.configured(), "model": settings.llm_chat_model,
        "tools": TOOL_NAMES + ["search_policy"],
        "recent": db.rows("SELECT run_id, ts, exception_id, engine, model, ms, steps, grade FROM triage_runs ORDER BY ts DESC LIMIT 20"),
    }


def policy_page() -> dict:
    secs = policy.sections()
    docs: dict[str, dict] = {}
    for s in secs:
        d = docs.setdefault(s.doc_id, {"doc_id": s.doc_id, "title": s.doc_title, "sections": []})
        d["sections"].append({"section_id": s.section_id, "heading": s.heading, "text": s.text})
    ev = eval_status() or {}
    return {"documents": list(docs.values()), "retrieval": policy.retrieval_eval(), "llm_configured": llm.configured(),
            "model": settings.llm_chat_model if llm.configured() else None,
            "answer_eval": ev.get("policy_answers"),
            "recent": db.rows("SELECT ts, question, engine, model, sections, cited, grounded, ms FROM policy_answers ORDER BY ts DESC LIMIT 10")}


def access_page() -> dict:
    con = db.connection().cursor()
    try:
        measures = delivery.run_measures(con)
    finally:
        con.close()
    names = {m["id"]: m["name"] for m in measures}
    enquiries = delivery.load("semantic/enquiries.yaml")["enquiries"]
    roles = []
    for key, spec in access.ROLES.items():
        views = []
        for name, sql in spec["views"].items():
            cols = db.rows("""SELECT column_name FROM information_schema.columns
                              WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position""", [key, name])
            views.append({"name": f"{key}.{name}", "sql": sql, "columns": [c["column_name"] for c in cols],
                          "rows": db.scalar(f"SELECT count(*) FROM {key}.{name}")})
        roles.append({"id": key, **{k: spec[k] for k in ("label", "who", "rows", "dax")}, "views": views,
                      "queryable": key in access.QUERYABLE_ROLES})
    classes = []
    for feed in FEEDS:
        fields = next(v["fields"] for v in contract(feed)["versions"] if v.get("fields"))
        for name, spec in fields.items():
            classes.append({"feed": feed, "field": name, "class": spec.get("class"),
                            "reaches_gold": spec.get("class") not in ("personal", "sensitive")})
    return {"roles": roles, "measures": measures, "classification": classes,
            "enquiries": [{**e, "measure_name": names.get(e["answer"]) if e["route"] == "measure" else None} for e in enquiries],
            "data_team_tables": sorted(t["name"] for t in TABLES)}


def value() -> dict:
    return {"headline": headline(), "by_check": by_check(), "ablation": db.rows("SELECT * FROM ablation"),
            "assumptions": ref.TIME_ASSUMPTIONS, "proposals": proposals(), "eval": (eval_status() or {}).get("summary")}


@lru_cache(maxsize=1)
def _client_names() -> list[str]:
    path = settings.raw_dir / "crm" / "clients.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return sorted({r["family_name"] for r in rows} | {r["phone"] for r in rows} | {r["ndis_number"] for r in rows if r["ndis_number"]})


def snapshots_with_personal() -> int:
    """Scan every model snapshot for any client's surname, phone or NDIS number from the landing zone."""
    worlds = [r["world"] for r in db.rows("SELECT world FROM cases")]
    names = _client_names()
    return sum(1 for w in worlds if any(n in w for n in names))


def risk() -> dict:
    sample = db.rows("""SELECT c.world FROM cases c JOIN exceptions e USING (exception_id)
                        WHERE e.check_id = 'duration' ORDER BY exception_id LIMIT 1""")
    world = json.loads(sample[0]["world"]) if sample else {}
    ev = eval_status()
    adversarial = [r for r in (ev or {}).get("results", []) if r["kind"] == "adversarial"]
    raid = delivery.load("delivery/raid.yaml")
    return {
        "risks": raid["risks"], "decisions": [d for d in raid["decisions"] if d["id"] in ("D-02", "D-03", "D-04", "D-05")],
        "sent_to_model": {k: sorted(v.keys()) if isinstance(v, dict) else None for k, v in world.items()},
        "masked_notes": db.rows("""SELECT note_masked, pii_found FROM fact_visit_event WHERE pii_found LIKE '%phone%'
                                   OR pii_found LIKE '%ndis%' ORDER BY event_id LIMIT 4"""),
        "pii_found": db.rows("""SELECT pii_found, count(*) AS notes FROM fact_visit_event WHERE pii_found IS NOT NULL
                                GROUP BY 1 ORDER BY 2 DESC"""),
        "snapshots": db.scalar("SELECT count(*) FROM cases"),
        "snapshots_with_personal": snapshots_with_personal(),
        "adversarial": adversarial, "eval_summary": ev["summary"] if ev else None,
        "limits": {"per_address": settings.triage_rate_limit_per_ip, "global": settings.triage_rate_limit_global,
                   "window_seconds": settings.rate_limit_window_seconds, "timeout_seconds": settings.llm_timeout_seconds},
        "llm_configured": llm.configured(), "model": settings.llm_chat_model if llm.configured() else None,
        "personal_columns": db.scalar("""SELECT count(*) FROM information_schema.columns WHERE column_name IN
                                         ('given_name', 'family_name', 'date_of_birth', 'phone', 'address', 'ndis_number')"""),
    }


def delivery_page() -> dict:
    raid = delivery.load("delivery/raid.yaml")
    return {"requirements": delivery.load("delivery/requirements.yaml")["requirements"],
            "roadmap": delivery.load("delivery/roadmap.yaml")["initiatives"],
            "uat": db.rows("SELECT * FROM uat_results ORDER BY id"), **raid}


def operations(timings: list[dict]) -> dict:
    lag = db.rows("""SELECT count(*) FILTER (WHERE after_cutoff) AS late, count(*) AS events,
                            quantile_cont(lag_minutes, 0.95) AS p95_min FROM fact_visit_event""")[0]
    return {
        "runs": db.rows("SELECT * FROM runs ORDER BY run_id DESC"),
        "audit": db.rows("SELECT * FROM audit_log ORDER BY ts DESC LIMIT 50"),
        "timings": timings,
        "feeds": [{"feed": f, "schedule": contract(f)["schedule"], "freshness_hours": contract(f).get("freshness_hours"),
                   "owner": contract(f)["owner"]} for f in FEEDS],
        "evidence_lag": lag,
        "usage": {"decisions": db.scalar("SELECT count(*) FROM exception_decisions"),
                  "triage_runs": db.scalar("SELECT count(*) FROM triage_runs"),
                  "policy_answers": db.scalar("SELECT count(*) FROM policy_answers"),
                  "refused_writes": db.scalar("SELECT count(*) FROM audit_log WHERE outcome = 'refused'"),
                  "audit_entries": db.scalar("SELECT count(*) FROM audit_log")},
        "build_seconds": db.kv("build_seconds"), "uat": db.rows("SELECT id, passed FROM uat_results ORDER BY id"),
        "eval": {k: (eval_status() or {}).get(k) for k in ("run_at", "model", "cases")},
    }


def meta_counts() -> dict:
    h = headline()
    return {"services": h["services"], "held": h["held"], "tables": len(TABLES)}
