// The work queue: every held service with its reason, the evidence behind it,
// the policy that governs it, and the decision - which the server refuses
// when the rule says no.

import { useState } from "react";
import { Check } from "lucide-react";
import { Link } from "react-router-dom";
import Proposal, { Actor } from "../../components/Proposal.jsx";
import { actorName } from "../../config.js";
import { useTheme } from "../../context/ThemeContext.jsx";
import { ACTION_LABEL, CHECK_LABEL, apiWrite, fmtAud, fmtDate, fmtDateTime, fmtInt, fmtTime, useApi } from "../../lib/api.js";
import {
  Badge, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Select, Stat, Table,
} from "../../lib/ui.jsx";

function Detail({ id, onDone }) {
  const { t } = useTheme();
  const { data, error, reload } = useApi(`/api/exceptions/${id}`);
  const [action, setAction] = useState("");
  const [note, setNote] = useState("");
  const [actor, setActor] = useState(actorName());
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const e = data.exception;
  const s = data.shift;
  const chosen = action || e.label_action;
  const decide = async () => {
    setBusy(true);
    setErr(null);
    try {
      await apiWrite(`/api/exceptions/${id}/decide`, { action: chosen, note });
      reload();
      onDone();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  };
  return (
    <Card title={`${e.exception_id}: ${s.region || "region unknown"}, ${fmtDate(s.service_date)}`} right={<Badge tone="warning">{CHECK_LABEL[e.check_id]}</Badge>}>
      <Callout tone="warning" title="Why it is held">{e.reason}</Callout>
      <Grid cols={2} min={380}>
        <div>
          <KeyValues items={[
            ["Client / worker", <Mono>{s.client_id} / {s.worker_id}</Mono>],
            ["Rostered", `${fmtDateTime(s.start_local, { seconds: false })} to ${fmtTime(s.end_local, { seconds: false })} (${s.rostered_min} min)`],
            ["Item", `${s.item_code} at ${fmtAud(s.rate, { decimals: 2 })} an hour`],
            ["Claim as rostered", fmtAud(s.amount, { decimals: 2 })],
            ["At risk", fmtAud(e.at_risk, { decimals: 2 })],
            ["Read from", <Mono>{s.file} row {s.raw_row}</Mono>],
          ]} />
        </div>
        <div>
          <Table maxHeight={200} columns={[
            { key: "event_type", label: "Event" },
            { key: "ts_local", label: "At", render: (r) => fmtTime(r.ts_local, { seconds: false }) },
            { key: "app_version", label: "App" },
            { key: "note_masked", label: "Note (masked)", wrap: true, render: (r) => r.note_masked || "-" },
          ]} rows={data.events} empty="No usable phone events for this service." />
          {data.events_quarantined.length > 0 && (
            <p style={{ fontSize: 12, color: t.status.warning, margin: "8px 0 0" }}>{data.events_quarantined.length} event(s) in quarantine: {data.events_quarantined[0].detail}</p>
          )}
          {data.policy && (
            <p style={{ fontSize: 12, color: t.textMuted, margin: "10px 0 0", lineHeight: 1.5 }}>
              <b>{data.policy.section_id} {data.policy.heading}.</b> {data.policy.text}
            </p>
          )}
        </div>
      </Grid>
      {data.decision ? (
        <Callout tone="good" title="Decided">{ACTION_LABEL[data.decision.action]}, by {data.decision.actor} on {fmtDateTime(data.decision.decided_at, { seconds: false })}{data.decision.note ? `: ${data.decision.note}` : "."}</Callout>
      ) : (
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
          <Select label="Decision" value={chosen} onChange={setAction} options={Object.entries(ACTION_LABEL).filter(([k]) => k !== "propose_contract_update").map(([value, label]) => ({ value, label }))} />
          <input value={note} onChange={(x) => setNote(x.target.value)} placeholder="Why (needed to release a claim)" aria-label="Note"
            style={{ background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8, padding: "6px 9px", fontSize: 12.5, fontFamily: "inherit", minWidth: 220 }} />
          <Actor value={actor} onChange={setActor} />
          <CTAButton icon={Check} onClick={decide} disabled={busy}>Record the decision</CTAButton>
          <Link to={`/triage?exception=${id}`} style={{ color: t.accent2, fontWeight: 650, fontSize: 12.5 }}>Ask the agent for a first read</Link>
        </div>
      )}
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
    </Card>
  );
}

export default function Exceptions() {
  const { data, error, reload } = useApi("/api/exceptions");
  const [check, setCheck] = useState("all");
  const [open, setOpen] = useState(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const rows = data.rows.filter((r) => check === "all" || r.check_id === check);

  return (
    <>
      <PageHeader
        title="Claim exceptions"
        brief="Maintaining data quality, governance, privacy and security standards."
        subtitle="Data quality, measured where it costs money: only the services the checks could not clear, each with the reason, the phone evidence, the policy section that governs it and the value at risk. A decision is recorded once, under a name, and the server refuses the ones policy forbids - try claiming a service by a worker whose screening had lapsed, claiming a no-show, or deciding as the agent's own identity."
      />
      <Grid cols={4} min={200}>
        <Stat label="Held" value={fmtInt(h.held)} sub={`of ${fmtInt(h.services)} services rostered`} emphasis />
        <Stat label="Claim value held" value={fmtAud(h.held_value, { short: true })} sub={`${fmtAud(h.at_risk, { short: true })} of it at risk if claimed as rostered`} tone="warning" />
        <Stat label="Decided" value={fmtInt(h.decided)} sub="on this deployment, each under a name" />
        <Stat label="Proposals waiting" value={data.proposals.filter((p) => p.status === "pending").length} sub="contract changes need a second person" />
      </Grid>

      {data.proposals.map((p) => <div key={p.proposal_id} style={{ marginBottom: 14 }}><Proposal p={p} onDone={reload} /></div>)}

      <SectionTitle right={<Select label="Check" value={check} onChange={(v) => { setCheck(v); setOpen(null); }}
        options={[{ value: "all", label: "All checks" }, ...data.by_check.map((c) => ({ value: c.check_id, label: `${CHECK_LABEL[c.check_id]} (${c.held})` }))]} />}>
        Held services, largest risk first
      </SectionTitle>
      {open && <div style={{ marginBottom: 14 }}><Detail key={open} id={open} onDone={reload} /></div>}
      <Card hint="Select a row to open the service.">
        <Table maxHeight={520} onRowClick={(r) => setOpen(r.exception_id)} columns={[
          { key: "exception_id", label: "Exception", render: (r) => <Mono>{r.exception_id}</Mono> },
          { key: "region", label: "Region", render: (r) => r.region || "-" },
          { key: "check_id", label: "Held by", render: (r) => <Badge tone="warning">{CHECK_LABEL[r.check_id]}</Badge> },
          { key: "service_date", label: "Service", render: (r) => fmtDate(r.service_date) },
          { key: "amount", label: "Claim", align: "right", render: (r) => fmtAud(r.amount) },
          { key: "at_risk", label: "At risk", align: "right", render: (r) => fmtAud(r.at_risk) },
          { key: "decided_action", label: "Decision", render: (r) => r.decided_action ? <Badge tone="good">{ACTION_LABEL[r.decided_action]}</Badge> : "open" },
        ]} rows={rows} />
      </Card>
    </>
  );
}
