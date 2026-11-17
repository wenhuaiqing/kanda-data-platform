// A contract-change proposal: the evidence computed from the data, what
// approving would change, and the decision - refused for the proposer.

import { useState } from "react";
import { Check, X } from "lucide-react";
import { actorName, setActorName, writeToken } from "../config.js";
import { useTheme } from "../context/ThemeContext.jsx";
import { apiWrite, fmtAud, fmtDateTime, fmtInt, fmtMs } from "../lib/api.js";
import { Badge, Button, CTAButton, Callout, Card, Grid, KeyValues, SectionTitle } from "../lib/ui.jsx";

export function Actor({ value, onChange }) {
  const { t } = useTheme();
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: t.textMuted }}>
      Acting as
      <input value={value} onChange={(e) => { onChange(e.target.value); setActorName(e.target.value); }} aria-label="Acting as"
        style={{ background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8, padding: "5px 8px", fontSize: 12.5, fontFamily: "inherit", width: 160 }} />
    </label>
  );
}

export default function Proposal({ p, onDone }) {
  const [actor, setActor] = useState(actorName());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [res, setRes] = useState(null);
  const e = p.evidence;
  const v = p.preview;
  const decide = async (verb) => {
    setBusy(true);
    setErr(null);
    try {
      setRes(await apiWrite(`/api/proposals/${p.proposal_id}/${verb}`, { note: verb === "approve" ? "evidence reviewed; vendor change confirmed" : "" }));
      onDone();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  const shapes = Object.entries(e.field_shapes || {}).map(([k, n]) => `${k} (${fmtInt(n)})`).join("; ");
  return (
    <Card title={`${p.proposal_id}: ${p.title}`} right={<Badge tone={p.status === "pending" ? "ai" : p.status === "approved" ? "good" : "neutral"}>{p.status}</Badge>}
      hint={`Proposed by ${p.proposed_by}, the platform's contract monitor. Quarantining these events was correct - a contract that bent on its own would have read UTC as local time and every duration from 08/09 would have been wrong by ten hours. Releasing ${fmtInt(e.services_held)} services one at a time would be waste and guessing.`}>
      <Grid cols={2} min={340}>
        <div>
          <SectionTitle>Evidence, computed from the quarantine</SectionTitle>
          <KeyValues items={[
            ["Events quarantined", `${fmtInt(e.events_quarantined)} from ${fmtInt(e.devices)} phones, first ${fmtDateTime(e.first_seen, { seconds: false })}`],
            ["App versions", Object.entries(e.app_versions).map(([k, n]) => `${k}: ${fmtInt(n)}`).join(", ")],
            ["Field shapes", shapes],
            ["worker_ref resolves to a worker", `${fmtInt(e.workers_resolved)} of ${fmtInt(e.events_quarantined)}`],
            ["ts_utc + 10 h inside the roster window", `${fmtInt(e.within_roster_window_as_utc_plus_10)} of ${fmtInt(e.timestamps_parsed)}`],
            ["ts_utc read as local, inside the window", `${fmtInt(e.within_roster_window_read_as_local)} of ${fmtInt(e.timestamps_parsed)}`],
            ["Services held for want of evidence", `${fmtInt(e.services_held)}, worth ${fmtAud(e.services_held_value)}`],
          ]} />
        </div>
        <div>
          <SectionTitle>If approved: reprocess from the landing zone</SectionTitle>
          <KeyValues items={[
            ["Services released", `${fmtInt(v.services_released)}, worth ${fmtAud(v.claim_value_released)}`],
            ["Held services", `${fmtInt(v.exceptions_before)} to ${fmtInt(v.exceptions_after)}`],
            ["New holds", v.new_holds ? `${v.new_holds}: ${Object.entries(v.new_holds_by_check).map(([k, n]) => `${k} ${n}`).join(", ")}` : "none"],
            ["Rows in quarantine", `${fmtInt(v.quarantined_before)} to ${fmtInt(v.quarantined_after)}`],
          ]} />
        </div>
      </Grid>
      {p.status === "pending" ? (
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
          <Actor value={actor} onChange={setActor} />
          <CTAButton icon={Check} onClick={() => decide("approve")} disabled={busy}>{busy ? "Reprocessing..." : "Approve and reprocess"}</CTAButton>
          <Button icon={X} onClick={() => decide("reject")} disabled={busy}>Reject</Button>
        </div>
      ) : (
        <p style={{ fontSize: 12.5, margin: "12px 0 0" }}>Decided by {p.decided_by} on {fmtDateTime(p.decided_at, { seconds: false })}.</p>
      )}
      {!writeToken() && p.status === "pending" && (
        <p style={{ fontSize: 12, margin: "10px 0 0", opacity: 0.75 }}>This is the read-only link: try it, and the server will say why it refuses. Try acting as "contract-monitor" with the operator link, and it refuses for a different reason.</p>
      )}
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
      {res?.after && (
        <div style={{ marginTop: 12 }}>
          <Callout tone="good" title={`Reprocessed from the landing zone in ${fmtMs(res.wall_ms)} (${res.run_id})`}>
            Held services {fmtInt(res.before.held)} to {fmtInt(res.after.held)}; held for want of evidence {fmtInt(res.before.held_for_evidence)} to{" "}
            {fmtInt(res.after.held_for_evidence)}; rows in quarantine {fmtInt(res.before.quarantined)} to {fmtInt(res.after.quarantined)}. Every page now reads the new tables.
          </Callout>
        </div>
      )}
    </Card>
  );
}
