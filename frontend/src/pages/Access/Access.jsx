// Who sees what, enforced in the data: roles as views with their row filter,
// the same filter as Power BI row-level security, a query box that runs as a
// role, and the measures defined once in SQL and DAX.

import { useState } from "react";
import { Play } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { api, fmtAud, fmtInt, fmtMs, fmtNum, pct, useApi } from "../../lib/api.js";
import {
  Badge, Button, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle,
  SegmentedControl, Select, Stat, Table,
} from "../../lib/ui.jsx";

const ROUTE = {
  measure: { tone: "good", label: "published measure" },
  query: { tone: "warning", label: "ad hoc query" },
  build: { tone: "neutral", label: "needs building" },
};
const CLASS_TONE = { personal: "critical", sensitive: "critical", free_text: "warning", internal: "neutral", public: "good" };
const STARTER = {
  coordinator_bn: "SELECT check_id, count(*) AS held, round(sum(amount)) AS value\nFROM coordinator_bn.exceptions\nGROUP BY 1\nORDER BY 2 DESC",
  finance: "SELECT month, funding, round(sum(claim_amount)) AS claimable, round(sum(at_risk)) AS at_risk\nFROM finance.claims\nGROUP BY 1, 2\nORDER BY 1, 2",
  executive: "SELECT region, sum(services) AS services, sum(held) AS held, round(sum(claimed)) AS claimed\nFROM executive.summary\nGROUP BY 1\nORDER BY 1",
  data_team: "SELECT feed, rule, count(*) AS rows\nFROM quarantine\nGROUP BY 1, 2\nORDER BY 3 DESC",
};

function fmtValue(m) {
  if (m.value == null) return "-";
  if (m.format === "aud") return fmtAud(m.value);
  if (m.format === "pct") return pct(m.value);
  if (m.format === "int") return fmtInt(m.value);
  return fmtNum(m.value, 0);
}

export default function Access() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/access");
  const [lang, setLang] = useState("sql");
  const [role, setRole] = useState("coordinator_bn");
  const [sql, setSql] = useState(STARTER.coordinator_bn);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [cls, setCls] = useState("all");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  const run = async (text = sql, as = role) => {
    setBusy(true);
    setErr(null);
    try { setRes(await api("/api/query", { method: "POST", body: { sql: text, role: as } })); } catch (e) { setRes(null); setErr(e); } finally { setBusy(false); }
  };
  const pickRole = (r) => { setRole(r); setSql(STARTER[r]); setRes(null); setErr(null); };
  const n = data.enquiries.length;
  const count = (route) => data.enquiries.filter((e) => e.route === route).length;
  const personal = data.classification.filter((c) => !c.reaches_gold).length;
  const roleViews = data.roles.find((r) => r.id === role)?.views || [];
  const classes = data.classification.filter((c) => cls === "all" || (cls === "kept" ? !c.reaches_gold : c.reaches_gold));

  return (
    <>
      <PageHeader
        title="Governed access & BI"
        brief="You have hands-on experience with Microsoft Fabric, Power BI, DAX and Azure."
        subtitle="Access decided once and enforced in the data, not report by report. Each role is a set of views carrying its own row filter - a coordinator sees their region, Finance sees claims without visit notes, executives see aggregates - and the same filter is written as the DAX row-level security a Power BI semantic model would carry. Every measure is defined once, with the SQL that runs here and the DAX for the model. Run a query as a role below: it can name that role's views and nothing else."
      />
      <Grid cols={4} min={200}>
        <Stat label="Roles" value={data.roles.length} sub="including the triage agent, the narrowest" emphasis />
        <Stat label="Fields kept in the landing zone" value={personal} sub="personal or sensitive; no governed table has them" tone="warning" />
        <Stat label="Published measures" value={data.measures.length} sub="each with SQL and DAX" />
        <Stat label="Enquiries a measure answers" value={pct(count("measure") / n, 0)} sub={`${count("measure")} of ${n} last quarter`} />
      </Grid>

      <SectionTitle>Roles</SectionTitle>
      <Grid cols={2} min={420}>
        {data.roles.map((r) => (
          <Card key={r.id} title={r.label} right={<Badge tone={r.id === "triage_agent" ? "ai" : "neutral"}>{r.rows}</Badge>} hint={r.who}>
            <Table maxHeight={220} columns={[
              { key: "name", label: "View", render: (v) => <Mono>{v.name}</Mono> },
              { key: "rows", label: "Rows", align: "right", render: (v) => fmtInt(v.rows) },
              { key: "columns", label: "Columns", wrap: true, render: (v) => <span style={{ fontSize: 12, color: t.textMuted }}>{v.columns.join(", ")}</span> },
            ]} rows={r.views} />
            <p style={{ fontSize: 12, margin: "8px 0 0", color: t.textMuted }}>Power BI RLS: <Mono>{r.dax}</Mono></p>
          </Card>
        ))}
      </Grid>

      <SectionTitle right={<Select label="Run as" value={role} onChange={pickRole} options={[
        ...data.roles.filter((r) => r.queryable).map((r) => ({ value: r.id, label: r.label })),
        { value: "data_team", label: "Data team (gold and control tables)" },
      ]} />}>
        Query as a role
      </SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="SQL" hint="SELECT only, against the role's own views, with a row limit and a five-second ceiling. The connection itself cannot read files or URLs.">
          <textarea value={sql} onChange={(e) => setSql(e.target.value)} spellCheck={false} aria-label="SQL" style={{
            width: "100%", minHeight: 150, fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 12.5,
            background: t.code, color: t.text, border: `1px solid ${t.border}`, borderRadius: 10, padding: 12, resize: "vertical", lineHeight: 1.5,
          }} />
          <div style={{ marginTop: 10, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <CTAButton icon={Play} onClick={() => run()} disabled={busy}>{busy ? "Running..." : "Run"}</CTAButton>
            <Button onClick={() => { const q = "SELECT region, count(*) FROM fact_shift GROUP BY 1"; setSql(q); run(q); }}>Try reading another region</Button>
            {res && <span style={{ fontSize: 12, color: t.textMuted }}>{res.rows.length} rows in {fmtMs(res.ms)}</span>}
          </div>
        </Card>
        <Card title="What this role can read">
          {role === "data_team" ? (
            <p style={{ fontSize: 12.5, color: t.textMuted, margin: 0 }}>{data.data_team_tables.join(", ")}. No table, for any role, has a name, date of birth, phone, address or NDIS number in it.</p>
          ) : (
            <Table maxHeight={260} columns={[
              { key: "name", label: "View", render: (v) => <Mono>{v.name}</Mono> },
              { key: "sql", label: "Defined as", wrap: true, render: (v) => <Mono dim>{v.sql}</Mono> },
            ]} rows={roleViews} />
          )}
        </Card>
      </Grid>
      {err && <Callout tone="critical" title="Refused">{err.message}</Callout>}
      {res && (
        <Card title={`Result, as ${res.role}`} hint={`Ran as: ${res.sql.replace(/\s+/g, " ").slice(0, 220)}`}>
          <Table maxHeight={380} columns={res.columns.map((c) => ({ key: c, label: c, render: (r) => r[c] === null ? "null" : typeof r[c] === "object" ? JSON.stringify(r[c]) : String(r[c]) }))} rows={res.rows} empty="No rows." />
        </Card>
      )}

      <SectionTitle right={<SegmentedControl label="Definition language" value={lang} onChange={setLang} options={[{ value: "sql", label: "SQL" }, { value: "dax", label: "DAX" }]} />}>
        Published measures
      </SectionTitle>
      <Card hint="The value is the SQL run against the governed tables just now. The DAX is the same definition for a Direct Lake semantic model; it is not executed here.">
        <Table maxHeight={520} columns={[
          { key: "name", label: "Measure", render: (m) => <b>{m.name}</b> },
          { key: "value", label: "Value", align: "right", render: fmtValue },
          { key: "description", label: "Means", wrap: true },
          { key: "def", label: lang === "sql" ? "SQL" : "DAX", wrap: true, render: (m) => <Mono dim>{m[lang]}</Mono> },
        ]} rows={data.measures} />
      </Card>

      <SectionTitle>The data team's enquiry log, scored</SectionTitle>
      <Card hint="An invented quarter of enquiries. Select an ad hoc one to run its query as the data team.">
        <Table maxHeight={420} onRowClick={(e) => { if (e.route === "query") { setRole("data_team"); setSql(e.answer); run(e.answer, "data_team"); } }} columns={[
          { key: "id", label: "Ticket", render: (e) => <Mono>{e.id}</Mono> },
          { key: "team", label: "Team" },
          { key: "asked", label: "Asked", wrap: true },
          { key: "route", label: "Answered by", render: (e) => <Badge tone={ROUTE[e.route].tone}>{ROUTE[e.route].label}</Badge> },
          { key: "answer", label: "How", wrap: true, render: (e) => e.route === "measure" ? e.measure_name : e.route === "query" ? "select to run" : e.answer },
        ]} rows={data.enquiries} />
      </Card>

      <SectionTitle right={<Select label="Fields" value={cls} onChange={setCls} options={[
        { value: "all", label: "All fields" }, { value: "kept", label: "Kept in the landing zone" }, { value: "gold", label: "Reach gold" }]} />}>
        Classification, from the contracts
      </SectionTitle>
      <Card hint="Every field's class is declared in its feed's contract. Personal and sensitive fields stop at the landing zone; free text is masked before it moves.">
        <Table maxHeight={380} columns={[
          { key: "feed", label: "Feed", render: (c) => <Mono>{c.feed}</Mono> },
          { key: "field", label: "Field", render: (c) => <Mono>{c.field}</Mono> },
          { key: "class", label: "Class", render: (c) => <Badge tone={CLASS_TONE[c.class] || "neutral"}>{c.class}</Badge> },
          { key: "reaches_gold", label: "Reaches gold", render: (c) => (c.reaches_gold ? (c.class === "free_text" ? "masked" : "yes") : "no") },
        ]} rows={classes} />
      </Card>

      <Card title="Not built here">
        <KeyValues columns={1} items={[
          ["A Power BI report", "The measures and RLS filters are written for the model; the report itself would be built in Power BI Desktop on the Fabric semantic model, not mocked up in a web page."],
          ["Identity", "Roles are chosen from a list here. In production they come from Entra ID groups, mapped once to the views and to the model's roles."],
        ]} />
      </Card>
    </>
  );
}
