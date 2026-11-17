// What each control is worth, found by switching it off and running the
// quarter again - and what the triage first read is worth in hours, on
// stated assumptions.

import { Bar, BarChart, Cell } from "recharts";
import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CONTROL_LABEL, fmtAud, fmtInt, fmtNum, timeModel, useApi } from "../../lib/api.js";
import {
  Badge, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, Loading, PageHeader, SectionTitle, Stat, Table,
  useChartParts,
} from "../../lib/ui.jsx";

const KIND_TONE = {
  "claimed in error": "critical", "compliance exposure": "warning", "revenue missed": "serious",
  "privacy exposure": "critical", work: "neutral",
};

export default function Value() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/value");
  const parts = useChartParts();
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const a = data.assumptions;
  const rows = data.ablation.filter((r) => r.control !== "all_controls_off");
  const all = data.ablation.find((r) => r.control === "all_controls_off");
  const sum = (kind) => rows.filter((r) => r.kind === kind).reduce((n, r) => n + r.amount, 0);
  const money = rows.filter((r) => ["claimed in error", "compliance exposure", "revenue missed"].includes(r.kind))
    .sort((x, y) => y.amount - x.amount).map((r) => ({ ...r, label: CONTROL_LABEL[r.control] }));
  const dedupe = rows.find((r) => r.control === "dedupe_events");
  const mask = rows.find((r) => r.control === "mask_notes");
  const m = timeModel(h.held, a);
  const pending = data.proposals.find((p) => p.status === "pending");
  const colour = (r) => (r.kind === "compliance exposure" ? t.series[1] : r.kind === "revenue missed" ? t.series[2] : t.series[0]);

  return (
    <>
      <PageHeader
        title="What controls are worth"
        brief="Leading and developing the data platform team while reporting on technical performance, risks and priorities."
        subtitle="Each control was switched off in turn and the whole quarter run again from the landing zone. What follows is what would have happened - not an estimate, a count. The kinds of answer are kept apart because they are not the same thing: money claimed that would be repaid at audit, services claimed that compliance must review, revenue missed, personal information that would have spread, and work created for nothing."
      />
      <Grid cols={4} min={200}>
        <Stat label="Would have been claimed in error" value={fmtAud(sum("claimed in error"), { short: true })} sub="no evidence, outside funding, above limit, over time or budget" tone="critical" />
        <Stat label="Claimed without clearance" value={fmtAud(sum("compliance exposure"), { short: true })} sub="lapsed screening, or one worker in two places" tone="warning" />
        <Stat label="Notes that would carry personal data" value={fmtInt(mask?.notes_with_pii)} sub="into gold tables, reports and the model" tone="critical" />
        <Stat label="Coordinator hours a quarter" value={fmtNum(m.saved, 0)} sub={`${fmtAud(m.savedAud)} with a first read on each hold; assumed minutes`} emphasis />
      </Grid>

      <Callout tone="neutral" title="How to read this">
        The evidence check carries the biggest number partly because one vendor release put {fmtInt(pending?.evidence?.services_held || 0)} services
        behind it - which is the point: without it, those visits would have been claimed on the roster alone, and the ones that genuinely did not
        happen with them. Every control off at once: {fmtInt(all?.released)} held services claimed, {fmtAud(all?.amount)} at risk. The time
        saving rests on assumed minutes ({a.investigate_exception_today_min} to investigate a hold today, {a.investigate_with_first_read_min} with a
        first read); the dollar figures do not.
      </Callout>

      <SectionTitle>Controls that stop the wrong claim</SectionTitle>
      <Card hint="Switched off one at a time. The amount is what would be claimed that should not be (or, for the wrong item, what would be under-claimed).">
        <ChartOrTable
          chart={(
            <ChartFrame height={320}>
              <BarChart data={money} layout="vertical" margin={{ left: 30, right: 20 }}>
                {parts.grid}
                {parts.xAxis({ type: "number", tickFormatter: (v) => `$${Math.round(v / 1000)}k` })}
                {parts.yAxis({ type: "category", dataKey: "label", width: 140 })}
                {parts.tooltip({ formatter: (v) => fmtAud(v) })}
                <Bar dataKey="amount" name="At risk">
                  {money.map((r) => <Cell key={r.control} fill={colour(r)} />)}
                </Bar>
              </BarChart>
            </ChartFrame>
          )}
          table={<Table columns={[
            { key: "label", label: "Control switched off", render: (r) => <b>{r.label}</b> },
            { key: "kind", label: "Kind", render: (r) => <Badge tone={KIND_TONE[r.kind]}>{r.kind}</Badge> },
            { key: "released", label: "Services released", align: "right", render: (r) => fmtInt(r.released) },
            { key: "amount", label: "At risk", align: "right", render: (r) => fmtAud(r.amount) },
            { key: "claim_value_released", label: "Claim value", align: "right", render: (r) => fmtAud(r.claim_value_released) },
          ]} rows={money} />}
          defaultView="table"
        />
        <p style={{ fontSize: 12, color: t.textMuted, margin: "10px 0 0", lineHeight: 1.5 }}>
          In the chart: rust is claimed in error, orange is compliance exposure, grey is revenue missed. Each bar also carries its label in the table view.
        </p>
      </Card>

      <SectionTitle>Controls that protect people and time</SectionTitle>
      <Card>
        <Table columns={[
          { key: "control", label: "Control switched off", render: (r) => <b>{CONTROL_LABEL[r.control]}</b> },
          { key: "kind", label: "Kind", render: (r) => <Badge tone={KIND_TONE[r.kind]}>{r.kind}</Badge> },
          { key: "effect", label: "What happens", wrap: true, render: (r) => r.control === "mask_notes"
            ? `${fmtInt(r.notes_with_pii)} visit notes reach the governed tables, every report and the model with a client's name, phone number or NDIS number in them.`
            : `${fmtInt(r.extra_holds)} services held for unreadable evidence - a phone resending events makes two check-ins - about ${fmtNum((r.extra_holds * a.investigate_exception_today_min) / 60, 0)} hours to clear. With those held, ${fmtInt(r.released)} budget holds slip through.` },
        ]} rows={[mask, dedupe].filter(Boolean)} />
      </Card>

      {pending && (
        <>
          <SectionTitle>The thing the data found that nobody asked about</SectionTitle>
          <Callout tone="ai" title={pending.title}>
            {fmtInt(pending.evidence.services_held)} held services share one cause: the mobile app vendor's release changed the event shape on
            08/09/2026 without notice. Approving contract v2 releases {fmtAud(pending.preview.claim_value_released)} of claims and takes the queue
            from {fmtInt(pending.preview.exceptions_before)} to {fmtInt(pending.preview.exceptions_after)}. It is a decision for a person on{" "}
            <Link to="/sources" style={{ color: t.accent2, fontWeight: 650 }}>Sources & contracts</Link>, and a conversation with the vendor (V-01).
          </Callout>
        </>
      )}

      <SectionTitle>What was deliberately not built</SectionTitle>
      <Card>
        <Table columns={[
          { key: 0, label: "Not built", render: (r) => <b>{r[0]}</b> },
          { key: 1, label: "Why not", wrap: true, render: (r) => r[1] },
          { key: 2, label: "What would change that", wrap: true, render: (r) => r[2] },
        ]} rows={[
          ["A model scoring every service", "Most services are evidenced and in policy. Rules clear those for nothing, the same way every time, and explain themselves.", "Patterns rules cannot express - and a labelled history to prove a model finds them."],
          ["Automatic claiming of held services", "The agent's hard-case pass rate does not justify it, and a wrong claim is repaid at audit.", "Months of shadow-run evidence, and a category where a mistake is cheap."],
          ["Submission to the funder", "Out of scope: this stops at claim-ready. The bulk claim file and the payment reconciliation are the next step.", "Phase two of P-01, once the shadow run agrees."],
          ["Streaming", "Claims run nightly, so a batch is simpler to prove and to re-run. Lateness is measured against the 06:00 cut-off instead.", "Same-day claiming, or an alert that must fire during the visit."],
        ]} />
      </Card>
    </>
  );
}
