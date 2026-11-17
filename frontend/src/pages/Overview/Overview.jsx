// The platform at a glance: what one quarter of service delivery looked like
// by the time it reached the claim run, what held what, and the roadmap the
// data points to.

import { Link } from "react-router-dom";
import { Bar, BarChart } from "recharts";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CHECK_LABEL, fmtAud, fmtInt, pct, useApi } from "../../lib/api.js";
import {
  Badge, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, KeyValues, Loading, PageHeader, SectionTitle, Stat,
  Table, useChartParts,
} from "../../lib/ui.jsx";

const STAGE_TONE = { "Pilot ready": "good", "In progress": "good", Design: "ai", Discovery: "ai", Backlog: "neutral" };
const LINK_LABEL = {
  lakehouse: "Lakehouse & lineage", exceptions: "Claim exceptions", value: "What controls are worth", sources: "Sources & contracts",
  triage: "AI triage", policy: "Policy assistant", risk: "Privacy & AI risk", access: "Governed access & BI",
};

export default function Overview() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/overview");
  const parts = useChartParts();
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const h = data.headline;
  const months = data.by_month.map((m) => ({ ...m, label: `${m.month.slice(5)}/${m.month.slice(0, 4)}` }));
  const pending = data.proposals.filter((p) => p.status === "pending");

  return (
    <>
      <PageHeader
        title="Platform overview"
        brief="Leading the development and management of Kanda's Enterprise Data Platform and Microsoft Fabric Lakehouse."
        subtitle="One quarter of a care provider's service delivery, taken from five source systems to the claim run: rosters, check-ins from support workers' phones, client funding, worker screening and the support catalogue. Every source has a contract, every row is accounted for, nothing is claimed that the data cannot support, and no personal information leaves the landing zone. The provider, its clients, workers and every number are invented."
      />
      <Grid cols={4} min={200}>
        <Stat label={`Services rostered, ${data.period}`} value={fmtInt(h.services)} sub={`${fmtInt(h.clients)} clients, ${fmtInt(h.workers)} support workers, five regions`} emphasis />
        <Stat label="Claimable, nobody touching" value={pct(h.straight_through)} sub={`${fmtAud(h.claim_value, { short: true })} cleared to claim`} />
        <Stat label="Held for a person" value={fmtInt(h.held)} sub={`${fmtAud(h.held_value, { short: true })} not claimed until someone decides`} tone={h.held ? "warning" : undefined} />
        <Stat label="Rows in quarantine" value={fmtInt(h.quarantined)} sub="broke their feed's contract; none dropped" />
      </Grid>

      {pending.length > 0 && (
        <Callout tone="ai" title="One decision is waiting">
          {pending[0].title}. The evidence and what approving would change are on <Link to="/sources" style={{ color: t.accent2, fontWeight: 650 }}>Sources & contracts</Link>;
          the automation that proposed it cannot approve it.
        </Callout>
      )}

      <Grid cols={2} min={420}>
        <Card title="Services by month" hint="Claimable (including short notice cancellations) and held, by month of service.">
          <ChartOrTable
            chart={(
              <ChartFrame height={250}>
                <BarChart data={months}>
                  {parts.grid}
                  {parts.xAxis({ dataKey: "label" })}
                  {parts.yAxis({})}
                  {parts.tooltip({})}
                  {parts.legend({})}
                  <Bar dataKey="claimable" name="Claimable" stackId="a" fill={t.series[0]} />
                  <Bar dataKey="held" name="Held" stackId="a" fill={t.series[1]} />
                </BarChart>
              </ChartFrame>
            )}
            table={<Table columns={[
              { key: "label", label: "Month" },
              { key: "services", label: "Services", align: "right", render: (r) => fmtInt(r.services) },
              { key: "claimable", label: "Claimable", align: "right", render: (r) => fmtInt(r.claimable) },
              { key: "held", label: "Held", align: "right", render: (r) => fmtInt(r.held) },
              { key: "claimed", label: "Claimable value", align: "right", render: (r) => fmtAud(r.claimed) },
            ]} rows={months} />}
          />
        </Card>
        <Card title="Why services were held" hint="The first check to fail is the reason on the exception. September's spike is one vendor release (see Sources).">
          <Table maxHeight={300} columns={[
            { key: "check_id", label: "Check", render: (r) => CHECK_LABEL[r.check_id] },
            { key: "held", label: "Held", align: "right", render: (r) => fmtInt(r.held) },
            { key: "value", label: "Claim value", align: "right", render: (r) => fmtAud(r.value) },
          ]} rows={data.by_check} />
        </Card>
      </Grid>

      <SectionTitle>By region</SectionTitle>
      <Card hint="The same numbers a regional coordinator sees for their own region on the Governed access page, and nothing more.">
        <Table columns={[
          { key: "region", label: "Region" },
          { key: "services", label: "Services", align: "right", render: (r) => fmtInt(r.services) },
          { key: "held", label: "Held", align: "right", render: (r) => fmtInt(r.held) },
          { key: "rate", label: "Held share", align: "right", render: (r) => pct(r.held / r.services) },
          { key: "claimed", label: "Claimable value", align: "right", render: (r) => fmtAud(r.claimed) },
        ]} rows={data.by_region} />
      </Card>

      <SectionTitle>Roadmap</SectionTitle>
      <Grid cols={2} min={420}>
        {data.roadmap.map((i) => (
          <Card key={i.id} title={`${i.id}  ${i.name}`} right={<Badge tone={STAGE_TONE[i.stage] || "neutral"}>{i.stage}</Badge>} hint={i.teams.join(", ")}>
            <KeyValues columns={1} items={[
              ["Problem", i.problem],
              ["Approach", i.approach],
              ["What AI does", i.ai_role],
              ["How we would know", i.measure],
              ["Risk", i.risk_tier],
              ["Next", i.next],
            ]} />
            {i.links.length > 0 && (
              <div style={{ display: "flex", gap: 14, marginTop: 12, flexWrap: "wrap" }}>
                {i.links.map((l) => <Link key={l} to={`/${l}`} style={{ color: t.accent, fontWeight: 650, fontSize: 12.5 }}>{LINK_LABEL[l]}</Link>)}
              </div>
            )}
          </Card>
        ))}
      </Grid>
      <p style={{ fontSize: 12, color: t.textMuted, margin: "4px 0 0", lineHeight: 1.5 }}>
        Acceptance scenarios passing: {data.uat.passed} of {data.uat.n}. Policy retrieval: the governing section in the top {data.retrieval.k} for{" "}
        {data.retrieval.hits} of {data.retrieval.questions} questions. Triage eval: {data.eval?.agent
          ? `agent ${data.eval.agent.passed} of ${data.eval.agent.cases}, runbook ${data.eval.rules.passed} of ${data.eval.rules.cases}`
          : data.eval ? `runbook ${data.eval.rules.passed} of ${data.eval.rules.cases}; the agent has not been graded on this build` : "not run"}.
      </p>
    </>
  );
}
