// The feeds: a contract for each, what broke it this quarter, how late the
// evidence arrives, and the one change waiting for a decision.

import { useState } from "react";
import { Bar, BarChart } from "recharts";
import Proposal from "../../components/Proposal.jsx";
import { useTheme } from "../../context/ThemeContext.jsx";
import { fmtDate, fmtInt, pct, useApi } from "../../lib/api.js";
import {
  Badge, Callout, Card, ChartFrame, ChartOrTable, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle,
  Select, Stat, Table, useChartParts,
} from "../../lib/ui.jsx";

const CLASS_TONE = { personal: "critical", sensitive: "critical", free_text: "warning", internal: "neutral", public: "good" };

function Contract({ c }) {
  const { t } = useTheme();
  return (
    <Card title={c.id} right={<span style={{ fontSize: 12, color: t.textMuted }}>{c.versions.map((v) => `v${v.version} ${v.status}`).join(", ")}</span>}
      hint={`${c.source}. Owner: ${c.owner}; steward: ${c.steward}.`}>
      <KeyValues items={[
        ["Schedule", c.schedule],
        ["Freshness", c.freshness_hours == null ? "on change" : `${c.freshness_hours} h`],
        ["Key", c.key.join(", ")],
        ["Consumers", c.consumers.map((x) => x.team).join("; ") || "-"],
        ["Classification", c.classification],
        ...(c.vendor ? [["Vendor", c.vendor]] : []),
      ]} />
      <div style={{ marginTop: 10 }}>
        <Table maxHeight={260} columns={[
          { key: "name", label: "Field", render: (r) => <Mono>{r.name}</Mono> },
          { key: "type", label: "Type" },
          { key: "required", label: "Required", render: (r) => (r.required ? "yes" : "no") },
          { key: "class", label: "Class", render: (r) => <Badge tone={CLASS_TONE[r.class] || "neutral"}>{r.class}</Badge> },
        ]} rows={c.fields} />
      </div>
      {c.rules.length > 0 && <p style={{ fontSize: 12, color: t.textMuted, margin: "10px 0 0" }}>Rules: {c.rules.map((r) => r.what).join(" ")}</p>}
      {c.versions.filter((v) => v.mappings).map((v) => (
        <Callout key={v.version} tone={v.status.startsWith("approved") ? "good" : "ai"} title={`Version ${v.version}: ${v.status}`}>
          {v.reason} Mappings: {Object.entries(v.mappings).map(([k, m]) => `${k} to ${m.to}${m.transform ? ` (${m.transform})` : ""}`).join("; ")}.
        </Callout>
      ))}
    </Card>
  );
}

export default function Sources() {
  const { t } = useTheme();
  const { data, error, reload } = useApi("/api/sources");
  const parts = useChartParts();
  const [feed, setFeed] = useState("mobile.visit_events");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const qTotal = data.quarantine.reduce((a, r) => a + r.rows, 0);
  const lagAll = data.lag.reduce((a, r) => ({ events: a.events + r.events, late: a.late + r.after_cutoff }), { events: 0, late: 0 });
  const contract = data.contracts.find((c) => c.id === feed);
  const days = data.by_day.map((d) => ({ ...d, label: fmtDate(d.day).slice(0, 5), on_time: d.events - d.late }));

  return (
    <>
      <PageHeader
        title="Sources & contracts"
        brief="Overseeing data pipelines, integrations, scheduled loads and platform performance."
        subtitle="Five source systems feed the claim run, each under a data contract: who owns it, when it loads, how fresh it must be, every field with its type and classification, and the rules a row must keep. A row that breaks its contract goes to quarantine with the rule it broke - never dropped, never fixed in place. When a source changes shape, the contract does not bend on its own: the change is proposed as a new version, with evidence and a preview, and someone other than the proposer decides."
      />
      <Grid cols={4} min={200}>
        <Stat label="Feeds under contract" value={data.contracts.length} sub="from five source systems" emphasis />
        <Stat label="Rows landed" value={fmtInt(data.files.reduce((a, f) => a + f.rows, 0))} sub={`${fmtInt(data.files.reduce((a, f) => a + f.files, 0))} files, each hashed on landing`} />
        <Stat label="Rows in quarantine" value={fmtInt(qTotal)} sub="each with the rule it broke" tone={qTotal ? "warning" : undefined} />
        <Stat label="Evidence after the 06:00 cut-off" value={pct(lagAll.late / lagAll.events)} sub={`${fmtInt(lagAll.late)} of ${fmtInt(lagAll.events)} phone events synced late`} />
      </Grid>

      {data.proposals.map((p) => <div key={p.proposal_id} style={{ marginBottom: 14 }}><Proposal p={p} onDone={reload} /></div>)}

      <Grid cols={2} min={420}>
        <Card title="What broke a contract" hint="Grouped by feed, rule and app version. One vendor release accounts for almost all of it.">
          <Table maxHeight={300} columns={[
            { key: "feed", label: "Feed", render: (r) => <Mono>{r.feed}</Mono> },
            { key: "rule", label: "Rule", render: (r) => <Badge tone="warning">{r.rule}</Badge> },
            { key: "app_version", label: "App", render: (r) => r.app_version || "-" },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "example", label: "Example", wrap: true },
          ]} rows={data.quarantine} />
        </Card>
        <Card title="How late the evidence arrives" hint={`Minutes from the event on the phone to landing. The nightly claim run reads what has landed by 0${data.cutoff_hour}:00 the next day; anything later waits a night.`}>
          <Table columns={[
            { key: "app_version", label: "App version" },
            { key: "events", label: "Events", align: "right", render: (r) => fmtInt(r.events) },
            { key: "p50_min", label: "p50", align: "right", render: (r) => `${fmtInt(r.p50_min)} min` },
            { key: "p95_min", label: "p95", align: "right", render: (r) => `${fmtInt(r.p95_min)} min` },
            { key: "max_min", label: "Max", align: "right", render: (r) => `${fmtInt(r.max_min / 60)} h` },
            { key: "after_cutoff", label: "After cut-off", align: "right", render: (r) => fmtInt(r.after_cutoff) },
          ]} rows={data.lag} />
          <p style={{ fontSize: 12, color: t.textMuted, margin: "10px 0 0", lineHeight: 1.5 }}>
            Copies removed in conforming: {data.duplicates.map((d) => `${fmtInt(d.events)} (${d.reason})`).join("; ")}. Each is recorded with the event it copied.
          </p>
        </Card>
      </Grid>

      <Card title="Phone events by day of service" hint={`On time and after the cut-off. The drop from ${fmtDate(data.vendor_release.date)} is app ${data.vendor_release.version}'s events going to quarantine, not fewer visits.`}>
        <ChartOrTable
          chart={(
            <ChartFrame height={230}>
              <BarChart data={days}>
                {parts.grid}
                {parts.xAxis({ dataKey: "label", interval: 13 })}
                {parts.yAxis({})}
                {parts.tooltip({})}
                {parts.legend({})}
                <Bar dataKey="on_time" name="Before the cut-off" stackId="a" fill={t.series[0]} />
                <Bar dataKey="late" name="After the cut-off" stackId="a" fill={t.series[1]} />
              </BarChart>
            </ChartFrame>
          )}
          table={<Table maxHeight={300} columns={[
            { key: "day", label: "Day", render: (r) => fmtDate(r.day) },
            { key: "events", label: "Events", align: "right", render: (r) => fmtInt(r.events) },
            { key: "late", label: "After cut-off", align: "right", render: (r) => fmtInt(r.late) },
          ]} rows={days} />}
        />
      </Card>

      <SectionTitle right={<Select label="Contract" value={feed} onChange={setFeed} options={data.contracts.map((c) => ({ value: c.id, label: c.id }))} />}>
        The contracts
      </SectionTitle>
      {contract && <Contract c={contract} />}

      <SectionTitle>Files landed</SectionTitle>
      <Card hint="The landing zone (bronze). Personal information - names, dates of birth, phones, addresses, NDIS numbers - is in these files and nowhere downstream.">
        <Table columns={[
          { key: "feed", label: "Feed", render: (r) => <Mono>{r.feed}</Mono> },
          { key: "files", label: "Files", align: "right" },
          { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
          { key: "bytes", label: "Size", align: "right", render: (r) => `${fmtInt(r.bytes / 1024)} KB` },
        ]} rows={data.files} />
      </Card>
      <p style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.5 }}>
        Not built: a live scheduler. Each feed's schedule is declared in its contract and the freshness is measured from the data;
        in production the same contracts run in a scheduled Fabric Data pipeline, and a load that misses its freshness raises an alert to the steward.
      </p>
    </>
  );
}
