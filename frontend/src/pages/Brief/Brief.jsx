// The advertisement's own list, mapped to where each point is shown working,
// then the first ninety days - as a plan that starts by listening.

import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { Callout, Card, Grid, PageHeader, SectionTitle, Table } from "../../lib/ui.jsx";

const ASKED = [
  ["Leading the development and management of Kanda's Enterprise Data Platform and Microsoft Fabric Lakehouse.",
   "A platform taken from five source systems to the claim run: bronze, silver and gold, every row traced to its file and line, every partition digested and reproducible. Each piece mapped to its Fabric equivalent.",
   [["Platform overview", "/overview"], ["Lakehouse & lineage", "/lakehouse"]]],
  ["Overseeing data pipelines, integrations, scheduled loads and platform performance.",
   "A contract per feed with its owner, schedule and freshness; quarantine with the rule broken; lateness of the evidence measured against the claim run's cut-off; every run timed and costed.",
   [["Sources & contracts", "/sources"], ["Operations", "/operations"]]],
  ["Developing AI capabilities, including LLM integrations, RAG agents and governed data access.",
   "A tool-calling agent that reads held services and searches the policy library, graded against the runbook on hard and adversarial cases; a RAG assistant that answers only from what it retrieved and cites it; both reading through the narrowest role.",
   [["AI triage", "/triage"], ["Policy assistant (RAG)", "/policy"]]],
  ["Managing Power BI, Azure infrastructure, container deployments and DevOps pipelines.",
   "Measures defined once in SQL and DAX, row-level security written as views and as DAX; Azure Container Apps from Terraform, images built and published by CI only when the build matches its pinned digests.",
   [["Governed access & BI", "/access"], ["Operations", "/operations"]]],
  ["Maintaining data quality, governance, privacy and security standards.",
   "Nine checks before a claim, hold never guess, every control priced by switching it off; personal information kept in the landing zone, free text masked, every write token-gated and audit-logged.",
   [["Claim exceptions", "/exceptions"], ["What controls are worth", "/value"], ["Privacy & AI risk", "/risk"]]],
  ["Managing technology vendors, resolving technical issues and driving continuous improvement.",
   "A vendor release that changed an interface without notice: caught at the door, proposed as a contract version with evidence, approved by a second person, raised with the vendor.",
   [["Roadmap, vendors & RAID", "/delivery"], ["Sources & contracts", "/sources"]]],
  ["Leading and developing the data platform team while reporting on technical performance, risks and priorities.",
   "A roadmap with stages and risk tiers, a RAID log kept as the work went, requirements traced to tests, and the value of each control as a count, not an estimate.",
   [["Platform overview", "/overview"], ["Roadmap, vendors & RAID", "/delivery"]]],
  ["Experience in aged care, health, disability (NDIS) or another regulated industry would be highly regarded.",
   "Built around what a regulated care provider has to get right: evidence of delivery, worker screening, funding periods, price limits and personal information - in synthetic form, and without claiming to know Kanda's systems.",
   [["Privacy & AI risk", "/risk"]]],
];

const PLAN = [
  {
    when: "Days 1-30: listen, and learn what is there",
    items: [
      "Meet the team one to one: what they own, what they are proud of, what keeps breaking, and what they would change first.",
      "With the CIO and the business leads: which decisions the data platform supports today, and which ones people still make from spreadsheets.",
      "Walk the Fabric Lakehouse end to end - sources, loads, models, reports, costs and who can see what - before proposing anything.",
      "Read the incident and support history: which loads fail, how often, and how long the fix takes.",
    ],
  },
  {
    when: "Days 31-60: make the platform dependable",
    items: [
      "Contracts and freshness alerts on the feeds that matter most to claiming and to reporting; quarantine instead of silent failure.",
      "One published definition for the numbers executives see most, in the semantic model, with row-level security agreed with the privacy officer.",
      "A vendor review with the suppliers the platform depends on: change notice, interface versions, named contacts.",
      "Agree with the team how work is planned, reviewed and released, and write it down.",
    ],
  },
  {
    when: "Days 61-90: AI where it earns its place",
    items: [
      "Pick one AI use with the business - a first read on held items, or a policy assistant - and grade it against the current procedure before anyone relies on it.",
      "Governed access for AI from day one: a role, a masked snapshot, no write, and an evaluation that is rerun when the model changes.",
      "A roadmap for the next two quarters with costs, risks and what would make each item not worth doing.",
      "Report on platform performance, risks and priorities in a form the executive can use every month.",
    ],
  },
];

export default function Brief() {
  const { t } = useTheme();
  return (
    <>
      <PageHeader
        title="First 90 days"
        subtitle="The advertisement's own list, mapped to where each point is shown working here. Then a plan for the first ninety days - which starts by listening, because the right first move is the one the team and the business need, and that is not something a demo can know."
      />
      <Callout tone="neutral" title="What this is and is not">
        Built for a job application, on invented data, and named for the organisation it was built for. It is not
        affiliated with or endorsed by Kanda. The provider, its clients, workers, plans, policies, support catalogue and
        prices are synthetic, and the vendor is invented. Service delivery and claiming were chosen because every care
        provider has them, not because of anything known about how Kanda works; the logo and colours are Kanda's own,
        taken from its public website, to show what the work would look like in its hands.
      </Callout>
      <SectionTitle>What the role asks for, and where it is shown</SectionTitle>
      <Card>
        <Table maxHeight={1000} columns={[
          { key: 0, label: "From the advertisement", wrap: true, render: (r) => <i style={{ color: t.textMuted }}>"{r[0]}"</i> },
          { key: 1, label: "Here", wrap: true, render: (r) => r[1] },
          { key: 2, label: "Open", render: (r) => (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {r[2].map(([label, to]) => <Link key={to} to={to} style={{ color: t.accent, fontWeight: 650, fontSize: 12.5 }}>{label}</Link>)}
            </div>
          ) },
        ]} rows={ASKED} />
      </Card>

      <SectionTitle>The first ninety days</SectionTitle>
      <Grid cols={3} min={300}>
        {PLAN.map((p) => (
          <Card key={p.when} title={p.when}>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
              {p.items.map((i) => <li key={i} style={{ marginBottom: 6 }}>{i}</li>)}
            </ul>
          </Card>
        ))}
      </Grid>

      <SectionTitle>Questions I would ask first</SectionTitle>
      <Card>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
          <li>Which decisions does the business most need the platform to get right this year, and which does it trust least today?</li>
          <li>Which sources land in the Lakehouse now, which are still extracts by hand, and which vendor interfaces have changed without notice?</li>
          <li>Where has AI been tried already, what happened, and what is the rule today on which data may reach which model?</li>
          <li>How is access to client information governed in reporting today, and who signs off a new role?</li>
          <li>What does the team want to stop doing, and what would they like to learn?</li>
        </ul>
      </Card>
    </>
  );
}
