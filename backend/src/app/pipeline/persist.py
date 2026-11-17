"""Write a governed run into the DuckDB the pages read.

Used by the build and again whenever an approval reprocesses the quarter, so
the tables always come from one code path. The role views are recreated and
the acceptance scenarios re-run every time: a reprocess that broke one would
show on the page.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd

from src.app.pipeline import access, delivery
from src.app.pipeline.cases import build_cases
from src.app.pipeline.stages import PipelineResult

GOVERNED_TABLES = ["dim_client", "dim_worker", "dim_support_item", "dim_plan", "fact_shift", "fact_visit_event",
                   "exceptions", "quarantine", "event_duplicates"]


def replace(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame) -> None:
    con.register("_frame", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _frame")
    con.unregister("_frame")


def output_hash(result: PipelineResult) -> str:
    return hashlib.sha256("".join(result.partition_hashes.sort_values("partition")["sha256"]).encode()).hexdigest()


def persist_governed(con: duckdb.DuckDBPyConnection, result: PipelineResult, run: dict, truth: dict, raw: Path) -> None:
    for name in GOVERNED_TABLES:
        replace(con, name, result.tables[name])
    replace(con, "raw_files", result.files)
    replace(con, "partition_hashes", result.partition_hashes.assign(run_id=run["run_id"]))
    replace(con, "cases", build_cases(result, truth, raw))
    access.create_views(con)
    replace(con, "uat_results", delivery.run_uat(con))

    con.execute("""CREATE TABLE IF NOT EXISTS runs (
        run_id VARCHAR, kind VARCHAR, started_at TIMESTAMP, git_sha VARCHAR, "trigger" VARCHAR,
        approved VARCHAR, wall_ms DOUBLE, cost_aud DOUBLE, output_sha256 VARCHAR)""")
    con.execute("""CREATE TABLE IF NOT EXISTS run_stages (
        run_id VARCHAR, seq INTEGER, stage VARCHAR, rows_in BIGINT, rows_out BIGINT, held BIGINT,
        wall_ms DOUBLE, note VARCHAR)""")
    con.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
        run["run_id"], run["kind"], run["started_at"], run.get("git_sha", ""), run.get("trigger", ""),
        json.dumps(sorted(run.get("approved", []))), run["wall_ms"], run_cost_aud(run["wall_ms"]),
        output_hash(result)])
    for seq, st in enumerate(result.stages):
        con.execute("INSERT INTO run_stages VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            run["run_id"], seq, st.name, st.rows_in, st.rows_out, st.held, st.wall_ms, st.note])


# Container Apps consumption, list price in australiaeast, converted at 1.52.
# The monthly free grant covers a demo's runs entirely; list price is what the
# number would mean at scale.
VCPU_SECOND_AUD = 0.000024 * 1.52
GIB_SECOND_AUD = 0.000003 * 1.52


def run_cost_aud(wall_ms: float, vcpu: float = 0.5, gib: float = 1.0) -> float:
    return round(wall_ms / 1000.0 * (vcpu * VCPU_SECOND_AUD + gib * GIB_SECOND_AUD), 8)
