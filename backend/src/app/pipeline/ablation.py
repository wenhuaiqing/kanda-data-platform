"""What each control is worth: switch it off, run the quarter again from the
raw files, and count what would have happened.

Five kinds of answer, kept apart because they are not the same thing:

  claimed in error     money claimed from a funder without the evidence or
                       entitlement to support it - repaid when audited
  compliance exposure  services by a worker who was not cleared, or who was
                       recorded in two places at once - claimed, and reportable
  revenue missed       a service claimed on the wrong item, below what it was owed
  privacy exposure     free-text notes carrying a phone number, an NDIS number
                       or a client's name into governed tables and the model
  work                 nothing is mis-claimed, but services that should pass are
                       held and somebody has to clear them
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.app.pipeline import privacy
from src.app.pipeline.stages import CONTROLS, PipelineResult, run_pipeline

KIND = {
    "identity": "claimed in error", "evidence": "claimed in error", "plan_dates": "claimed in error",
    "price": "claimed in error", "duration": "claimed in error", "budget": "claimed in error",
    "screening": "compliance exposure", "overlap": "compliance exposure",
    "item": "revenue missed", "mask_notes": "privacy exposure", "dedupe_events": "work",
}


def run_ablation(raw: Path, governed: PipelineResult, approved: frozenset[str] = frozenset()) -> pd.DataFrame:
    base = governed.tables["fact_shift"]
    base_held = {r.shift_id: float(r.at_risk) for r in base.itertuples() if r.status == "held"}
    names = privacy.name_pattern({c["given_name"] for c in governed.clients.values()}
                                 | {c["family_name"] for c in governed.clients.values()})
    rows = []
    for control in CONTROLS + ["all_controls_off"]:
        off = {c: False for c in CONTROLS} if control == "all_controls_off" else {control: False}
        res = run_pipeline(raw, controls=off, approved=approved, hash_files=False)
        inv = res.tables["fact_shift"]
        held_now = set(inv.loc[inv["status"] == "held", "shift_id"])
        released = [s for s in base_held if s not in held_now]
        extra = held_now - set(base_held)
        leaked = int(sum(privacy.contains_pii(n if isinstance(n, str) else "", names) for n in res.tables["fact_visit_event"]["note_masked"]))
        rows.append({
            "control": control, "kind": KIND.get(control, "everything"),
            "held": len(held_now), "released": len(released), "extra_holds": len(extra),
            "amount": round(sum(base_held[s] for s in released), 2),
            "claim_value_released": round(float(base.loc[base["shift_id"].isin(released), "amount"].sum()), 2),
            "notes_with_pii": leaked,
        })
    return pd.DataFrame(rows)
