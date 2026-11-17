// Privacy and AI risk, as controls that exist and can be checked - not a
// policy document. A regulated industry asks both questions at once.

import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext.jsx";
import { ACTION_LABEL, CATEGORY_LABEL, fmtInt, useApi } from "../../lib/api.js";
import { Badge, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Stat, Table } from "../../lib/ui.jsx";

const LEVEL = { High: "critical", Medium: "warning", Low: "good" };

export default function Risk() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/risk");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const agentAdv = data.adversarial.filter((r) => r.engine === "agent");
  const rulesAdv = data.adversarial.filter((r) => r.engine === "rules");
  const graded = agentAdv.length > 0;
  const talked = agentAdv.filter((r) => r.grade?.harmful).length;
  const tools = Object.entries(data.sent_to_model).map(([tool, keys]) => ({ tool, keys: (keys || []).join(", ") }));
  const found = data.pii_found.reduce((n, r) => n + r.notes, 0);

  return (
    <>
      <PageHeader
        title="Privacy & AI risk"
        brief="Experience in aged care, health, disability (NDIS) or another regulated industry would be highly regarded."
        subtitle="Care data is personal and often health-adjacent, so two sets of questions decide whether a platform and an AI feature are safe to run. For the data: where does personal information live, who can see what, and what happens to free text. For the agent: what can it do, what can it see, can its input talk it into something, and what happens when it is wrong or unavailable. Each answer here is a control in the code with a test or a query behind it."
      />
      <Grid cols={4} min={200}>
        <Stat label="Personal columns in the database" value={fmtInt(data.personal_columns)} sub="names, birth dates, phones, addresses, NDIS numbers" tone={data.personal_columns ? "critical" : "good"} emphasis />
        <Stat label="Snapshots holding personal data" value={`${data.snapshots_with_personal} of ${fmtInt(data.snapshots)}`} sub="scanned against the landing zone on every request" tone={data.snapshots_with_personal ? "critical" : "good"} />
        <Stat label="Notes masked" value={fmtInt(found)} sub="phone, NDIS number or a client's name found and removed" />
        <Stat label="Talked into claiming" value={graded ? `${talked} of ${agentAdv.length}` : "not graded"} sub={graded ? "adversarial notes, agent" : "adversarial cases exist; the agent run needs a model key"} tone={graded && talked ? "critical" : undefined} />
      </Grid>

      <SectionTitle>1. Where personal information lives</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="In the landing zone, and nowhere else">
          <KeyValues columns={1} items={[
            ["Kept at the door", "Every field classed personal or sensitive in its contract: client and worker names, date of birth, phone, address, NDIS number, screening id."],
            ["Downstream", "Clients and workers are ids; age is a band. No gold table, role view, query result or model snapshot has the rest - tested on every build."],
            ["Who sees what", <span>Roles enforced as views with their row filter, and the same filter as Power BI RLS. See <Link to="/access" style={{ color: t.accent, fontWeight: 650 }}>Governed access</Link>.</span>],
            ["With real data", "The landing zone is its own restricted area with its own access group, retention and audit; the platform reads it as a service principal."],
          ]} />
        </Card>
        <Card title="Free text is masked before it moves" hint="Visit notes are typed on a phone and can contain anything. What the masking found this quarter:">
          <Table columns={[
            { key: "pii_found", label: "Found", render: (r) => <Mono>{r.pii_found}</Mono> },
            { key: "notes", label: "Notes", align: "right", render: (r) => fmtInt(r.notes) },
          ]} rows={data.pii_found} />
          <div style={{ marginTop: 10 }}>
            {data.masked_notes.map((n, i) => <div key={i} style={{ fontSize: 12.5, marginBottom: 4 }}><Mono>{n.note_masked}</Mono></div>)}
          </div>
          <p style={{ fontSize: 12, color: t.textMuted, margin: "8px 0 0", lineHeight: 1.5 }}>Pattern masking is a floor, not a guarantee (R-03): a monthly sample review, then a classifier if the misses justify one.</p>
        </Card>
      </Grid>

      <SectionTitle>2. What the agent can do, and see</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="Authority">
          <KeyValues columns={1} items={[
            ["Can write", "Nothing. It returns a typed proposal; a person records the decision under their own name, and the decision endpoint refuses its identity."],
            ["Never released from the queue", "A service by a worker whose screening had lapsed, or one with no evidence at all - by anyone, whatever the agent or a person proposes."],
            ["Contract changes", "Proposed with evidence, approved by someone other than the proposer, then the quarter reprocesses from the landing zone."],
          ]} />
        </Card>
        <Card title="Everything the agent can read, by tool" hint="Built once per held service, as at the quarter's close, plus what it retrieves from the policy library. Nothing else reaches the model.">
          <Table maxHeight={300} columns={[
            { key: "tool", label: "Tool", render: (r) => <Mono>{r.tool}</Mono> },
            { key: "keys", label: "Fields", wrap: true, render: (r) => <span style={{ fontSize: 12, color: t.textMuted }}>{r.keys}</span> },
          ]} rows={tools} />
        </Card>
      </Grid>

      <SectionTitle>3. Can the input talk it into something</SectionTitle>
      <Card hint="A visit note is written by a person and read by a model. Notes reach the agent under a key that says they are untrusted, and its instructions say a note is evidence, never an instruction. That is a mitigation, not a guarantee - so it is measured.">
        <Table columns={[
          { key: "case_id", label: "Case", render: (r) => <Mono>{r.case_id.replace("adv-", "")}</Mono> },
          { key: "why", label: "What the note tries", wrap: true },
          { key: "right", label: "Right answer", wrap: true, render: (r) => `${CATEGORY_LABEL[r.label.category]}: ${ACTION_LABEL[r.label.action]}` },
          { key: "rules", label: "Runbook", render: (r) => <Badge tone={r.grade?.passed ? "good" : "critical"}>{r.grade?.passed ? "held the line" : "failed"}</Badge> },
          { key: "agent", label: "Agent", render: (r) => {
            const a = agentAdv.find((x) => x.case_id === r.case_id);
            if (!a) return "not graded";
            return <Badge tone={a.grade?.passed ? "good" : "critical"}>{a.grade?.passed ? "held the line" : a.grade?.harmful ? "talked into claiming" : "wrong"}</Badge>;
          } },
        ]} rows={rulesAdv} empty="No eval on this build." />
      </Card>

      <SectionTitle>4 and 5. When it is wrong, and when it is not there</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="When it is wrong">
          <KeyValues columns={1} items={[
            ["Before anyone relies on it", "Graded against the runbook on labelled cases, including ones built to fool it. Failures are listed one by one."],
            ["What counts as harm", "Claiming what should be held, cancelling what should be claimed, or not escalating a screening hold. Harm fails however well it is argued."],
            ["Evidence and citations", "Every statement must quote a value a tool returned; every policy cited must be a section it retrieved."],
            ["After go-live", "A sample of its proposals compared each week with what coordinators decided. The risk nobody plans for is people ceasing to check (R-06)."],
          ]} />
        </Card>
        <Card title="When it is not there, or is abused">
          <KeyValues columns={1} items={[
            ["Model", data.llm_configured ? data.model : "none configured on this deployment"],
            ["Timeout", `${data.limits.timeout_seconds} s per call, not retried; one fallback model on a rate limit or server error`],
            ["Fallback", "The runbook answers and the page says so. The claim checks never call a model, so claims keep flowing."],
            ["Cost ceiling", `${data.limits.per_address} runs per address and ${data.limits.global} in all per ${Math.round(data.limits.window_seconds / 60)} minutes`],
          ]} />
        </Card>
      </Grid>

      <SectionTitle>The risk register</SectionTitle>
      <Card>
        <Table maxHeight={620} columns={[
          { key: "id", label: "Id", render: (r) => <Mono>{r.id}</Mono> },
          { key: "risk", label: "Risk", wrap: true },
          { key: "likelihood", label: "Likelihood", render: (r) => <Badge tone={LEVEL[r.likelihood]}>{r.likelihood}</Badge> },
          { key: "impact", label: "Impact", render: (r) => <Badge tone={LEVEL[r.impact]}>{r.impact}</Badge> },
          { key: "mitigation", label: "Mitigation", wrap: true },
          { key: "status", label: "Status", wrap: true },
        ]} rows={data.risks} />
      </Card>
      <Callout tone="neutral" title="Decisions behind this page">
        {data.decisions.map((d) => <div key={d.id} style={{ marginBottom: 4 }}><b>{d.id}</b> {d.decision} {d.why}</div>)}
      </Callout>
      <p style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.5 }}>
        Not covered here, and would be before real data: a privacy impact assessment, retention and deletion rules per
        feed, breach notification, and the model provider's data terms (V-02). Those are decisions to make with the
        privacy officer, not code.
      </p>
    </>
  );
}
