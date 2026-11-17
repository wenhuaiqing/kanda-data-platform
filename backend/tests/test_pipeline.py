"""The pipeline finds every seeded defect from the data, holds nothing clean,
accounts for every row, and reproduces itself byte for byte."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.app.pipeline import reference as ref
from src.app.pipeline.stages import EVENTS_V2, run_pipeline
from tests.conftest import RAW

pytestmark = pytest.mark.needs_build

# The check that should hold each seeded category.
CHECK_FOR = {
    "unknown_client": "identity", "contract_change": "evidence", "no_show": "evidence", "missing_checkout": "evidence",
    "screening_lapsed": "screening", "worker_overlap": "overlap", "plan_lapsed": "plan_dates",
    "wrong_time_band": "item", "price_above_limit": "price", "hours_overclaimed": "duration",
    "budget_exhausted": "budget",
}


def test_every_seeded_defect_is_found_from_the_data(governed, seeded_exceptions):
    fs = governed.tables["fact_shift"].set_index("shift_id")
    for sid, category in seeded_exceptions.items():
        assert fs.loc[sid, "status"] == "held", (sid, category)
        assert fs.loc[sid, "check_id"] == CHECK_FOR[category], (sid, category, fs.loc[sid, "check_id"])
    for name, n in ref.DEFECTS.items():
        if n is not None and name not in ref.NOT_EXCEPTIONS:
            found = sum(1 for c in seeded_exceptions.values() if c == name)
            assert found == (2 * n if name == "worker_overlap" else n), name


def test_nothing_clean_is_held(governed, seeded_exceptions):
    fs = governed.tables["fact_shift"]
    held = set(fs.loc[fs["status"] == "held", "shift_id"])
    assert held == set(seeded_exceptions), sorted(held ^ set(seeded_exceptions))[:5]


def test_every_row_is_accounted_for(governed):
    files = governed.files.groupby("feed")["rows"].sum()
    q = governed.tables["quarantine"].groupby("feed").size()
    assert files["rostering.shifts"] == len(governed.tables["fact_shift"]) + q.get("rostering.shifts", 0)
    assert files["mobile.visit_events"] == (len(governed.tables["fact_visit_event"]) + q.get("mobile.visit_events", 0)
                                            + len(governed.tables["event_duplicates"]))
    for feed in ("crm.clients", "crm.plans", "hr.workers", "catalogue.price_guide"):
        assert q.get(feed, 0) == 0, feed
    assert (governed.tables["quarantine"]["rule"] != "").all()


def test_duplicate_events_are_absorbed(governed):
    d = governed.tables["event_duplicates"]
    assert len(d) == ref.DEFECTS["duplicate_event"]
    assert (d["reason"] == "same event id resent").sum() == ref.DUPLICATE_SAME_ID
    fs = governed.tables["fact_shift"]
    assert not (fs["evidence"] == "ambiguous").any()
    # Switched off, the same copies make visits unreadable and hold them.
    off = run_pipeline(RAW, controls={"dedupe_events": False}, hash_files=False).tables["fact_shift"]
    assert (off["evidence"] == "ambiguous").sum() > 0


def test_short_notice_cancellations_are_claimable(governed, truth):
    fs = governed.tables["fact_shift"].set_index("shift_id")
    short = [sid for sid, (d, _) in truth.items() if "short_notice_cancellation" in d]
    assert len(short) == ref.DEFECTS["short_notice_cancellation"]
    assert all(fs.loc[s, "status"] == "claimable_cancellation" for s in short)
    with_notice = fs[fs["kind"] == "cancelled_with_notice"]
    assert len(with_notice) > 0 and (with_notice["status"] == "not_claimable").all()
    assert (with_notice["claim_amount"] == 0).all()


def test_vendor_release_is_quarantined_not_dropped(governed):
    q = governed.tables["quarantine"]
    v5 = q[q["app_version"] == ref.VENDOR_RELEASE_VERSION]
    assert len(v5) > 0 and (v5["rule"] == "unknown_field").all()
    assert v5["detail"].str.contains("worker_ref").all()
    # Nothing from the new release reached the governed events under contract v1.
    assert not (governed.tables["fact_visit_event"]["app_version"] == ref.VENDOR_RELEASE_VERSION).any()


def test_contract_v2_maps_the_new_shape_to_local_time(governed):
    after = run_pipeline(RAW, approved={EVENTS_V2}, hash_files=False)
    ev = after.tables["fact_visit_event"]
    mapped = ev[ev["mapped_v2"]]
    assert len(mapped) > 0
    fs = after.tables["fact_shift"].set_index("shift_id")
    # Mapped events land inside their rostered window - which they would not if UTC were read as local.
    for r in mapped.head(200).itertuples():
        s = fs.loc[r.shift_id]
        window = pd.Timedelta(minutes=30)
        assert s["start_local"] - window <= r.ts_local <= s["end_local"] + window
    assert (after.tables["fact_shift"]["check_id"] == "evidence").sum() < (governed.tables["fact_shift"]["check_id"] == "evidence").sum()


def test_build_is_deterministic(governed):
    again = run_pipeline(RAW)
    assert list(again.partition_hashes["sha256"]) == list(governed.partition_hashes["sha256"])
    assert list(again.files["sha256"]) == list(governed.files["sha256"])


def test_the_truth_file_is_never_read_by_the_pipeline():
    import inspect

    from src.app.pipeline import stages
    assert "truth" not in inspect.getsource(stages)
    assert json.dumps(ref.DEFECTS)
