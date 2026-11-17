// Retrieval-augmented answers over the policy library: what retrieval found
// and why, the answer generated only from it with its citations checked, and
// the retrieval measured on a fixed question set every build.

import { useState } from "react";
import { MessageSquareText, Search } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { api, fmtDateTime, fmtMs, pct, useApi } from "../../lib/api.js";
import {
  Badge, Button, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Select,
  Stat, Table,
} from "../../lib/ui.jsx";

const EXAMPLES = [
  "A worker forgot to check out. Can we claim the rostered end time?",
  "The client rang the office to cancel but the roster still says scheduled",
  "My screening renewal is in progress - can I keep working?",
  "Can a phone number from a visit note appear in a report?",
  "What is the pay rate for a casual worker on a Sunday?",
];

function Ask({ llm }) {
  const { t } = useTheme();
  const [q, setQ] = useState(EXAMPLES[0]);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [kind, setKind] = useState(null);
  const [err, setErr] = useState(null);
  const go = async (what) => {
    setBusy(true);
    setErr(null);
    setRes(null);
    setKind(what);
    try {
      setRes(await api(`/api/policy/${what}`, { method: "POST", body: { question: q } }));
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  const sections = kind === "search" ? res?.results : res?.sections;
  return (
    <Card title="Ask the policy library" hint={llm ? "Retrieve the three best sections, then answer from those alone and cite them. A citation to anything not retrieved is flagged." : "No model is configured on this deployment: asking returns the sections retrieval found, and says so."}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Question" maxLength={400}
          style={{ flex: "1 1 320px", minWidth: 0, background: t.surface, color: t.text, border: `1px solid ${t.border}`, borderRadius: 8, padding: "8px 10px", fontSize: 13, fontFamily: "inherit" }} />
        <CTAButton icon={MessageSquareText} onClick={() => go("ask")} disabled={busy || q.length < 3}>{busy && kind === "ask" ? "Answering..." : "Ask"}</CTAButton>
        <Button icon={Search} onClick={() => go("search")} disabled={busy || q.length < 3}>Retrieval only</Button>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
        {EXAMPLES.map((e) => (
          <button key={e} onClick={() => setQ(e)} style={{ background: t.code, color: t.textMuted, border: "none", borderRadius: 999, padding: "4px 10px", fontSize: 11.5, cursor: "pointer", fontFamily: "inherit" }}>{e}</button>
        ))}
      </div>
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
      {res && kind === "ask" && (
        <div style={{ marginTop: 12 }}>
          {res.note && <Callout tone="warning" title="Retrieval only">{res.note}</Callout>}
          {res.answer && (
            <Callout tone={res.covered ? "ai" : "neutral"} title={`${res.covered ? "Answer" : "Not covered"} (${res.model}, ${fmtMs(res.ms)})`}>
              {res.answer}
              <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
                {res.citations.map((c) => <Badge key={c} tone="ai">{c}</Badge>)}
                <Badge tone={res.grounded ? "good" : "critical"}>{res.grounded ? "every citation was retrieved" : "cites something not retrieved"}</Badge>
              </div>
            </Callout>
          )}
        </div>
      )}
      {sections && (
        <div style={{ marginTop: 10 }}>
          <Table maxHeight={360} columns={[
            { key: "section_id", label: "Section", render: (r) => <Mono>{r.section_id}</Mono> },
            { key: "heading", label: "Heading", render: (r) => <b>{r.heading}</b> },
            { key: "score", label: "BM25", align: "right" },
            { key: "matched", label: "Words matched", wrap: true, render: (r) => r.matched.join(", ") },
            { key: "text", label: "Text", wrap: true },
          ]} rows={sections} empty="Nothing in the library matched." />
        </div>
      )}
    </Card>
  );
}

export default function Policy() {
  const { t } = useTheme();
  const { data, error } = useApi("/api/policy");
  const [doc, setDoc] = useState("POL-01");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const r = data.retrieval;
  const a = data.answer_eval;
  const d = data.documents.find((x) => x.doc_id === doc) || data.documents[0];
  const total = data.documents.reduce((n, x) => n + x.sections.length, 0);

  return (
    <>
      <PageHeader
        title="Policy assistant (RAG)"
        brief="You understand AI technologies, including LLMs, RAG and tool integrations."
        subtitle="Coordinators and the triage agent both need the policy that governs a held service. Eight short policies are split into sections with stable ids; retrieval finds the best three for a question, and the model answers from those alone, citing them - or says the library does not cover it. Retrieval is BM25: lexical, so every result is explained by the words it matched, and deterministic, so the evaluation below gives the same number on every build. The policies are written for this demo and are nobody's real policy."
      />
      <Grid cols={4} min={200}>
        <Stat label="Library" value={`${data.documents.length} policies`} sub={`${total} sections, each with a stable id`} emphasis />
        <Stat label="Retrieval hit rate" value={pct(r.hit_rate, 0)} sub={`governing section in the top ${r.k} for ${r.hits} of ${r.questions} questions`} />
        <Stat label="Mean reciprocal rank" value={r.mrr.toFixed(2)} sub="1.00 would be first every time" />
        <Stat label="Answers graded" value={a ? `${a.passed} / ${a.questions}` : "not graded"} sub={a ? `${a.refused_correctly} of ${a.out_of_scope} out-of-scope questions refused` : "needs a model key; retrieval is graded on every build"} tone={a ? undefined : "warning"} />
      </Grid>

      <Ask llm={data.llm_configured} />

      <SectionTitle>Retrieval, measured</SectionTitle>
      <Card hint="Questions in the words a coordinator or a finance officer would use, each with the section that answers it. Not tuned to pass: where the right section comes second or third, that is shown.">
        <Table maxHeight={420} columns={[
          { key: "question", label: "Question", wrap: true },
          { key: "expected", label: "Should find", render: (x) => <Mono>{x.expected}</Mono> },
          { key: "retrieved", label: "Top three", render: (x) => <Mono>{x.retrieved.join(", ")}</Mono> },
          { key: "rank", label: "Rank", align: "right", render: (x) => x.rank ? <Badge tone={x.rank === 1 ? "good" : "warning"}>{x.rank}</Badge> : <Badge tone="critical">missed</Badge> },
        ]} rows={r.rows} />
      </Card>

      {a && (
        <>
          <SectionTitle>Answers, graded</SectionTitle>
          <Card hint="Each answer must cite the governing section, cite only what was retrieved, and - for questions the library does not cover - say so instead of guessing.">
            <Table maxHeight={420} columns={[
              { key: "question", label: "Question", wrap: true },
              { key: "answer", label: "Answer", wrap: true, render: (x) => x.answer || x.error },
              { key: "citations", label: "Cited", render: (x) => <Mono>{(x.citations || []).join(", ") || "-"}</Mono> },
              { key: "passed", label: "Result", render: (x) => <Badge tone={x.passed ? "good" : "critical"}>{x.passed ? "pass" : "fail"}</Badge> },
            ]} rows={a.rows} />
          </Card>
        </>
      )}

      <SectionTitle right={<Select label="Policy" value={doc} onChange={setDoc} options={data.documents.map((x) => ({ value: x.doc_id, label: x.title }))} />}>
        The library
      </SectionTitle>
      <Card title={d.title}>
        {d.sections.map((s) => (
          <div key={s.section_id} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 650 }}><Mono>{s.section_id}</Mono> {s.heading}</div>
            <p style={{ fontSize: 13, lineHeight: 1.55, margin: "3px 0 0", color: t.textMuted }}>{s.text}</p>
          </div>
        ))}
      </Card>

      <SectionTitle>Decisions behind it</SectionTitle>
      <Card>
        <KeyValues columns={1} items={[
          ["Why BM25, not embeddings", "Twenty-eight sections written in the words staff use. The evaluation finds the governing section in the top three every time; a vector index would add cost and opacity for no measured gain. With thousands of documents and paraphrased questions the answer changes to hybrid search in Azure AI Search - and this evaluation is what would show it."],
          ["Why answer only from retrieved text", "So every claim in an answer can be checked against a section a person can open. A citation to anything not retrieved is flagged on the answer itself."],
          ["What is not built", "Ingesting real policy documents (PDF and Word) with their version history, and access control on the library itself. Both come before real use."],
          ["Recent questions on this replica", data.recent.length ? data.recent.slice(0, 5).map((x) => `${fmtDateTime(x.ts, { seconds: false })}: ${x.engine}${x.cited ? `, cited ${x.cited}` : ""}`).join("; ") : "none yet"],
        ]} />
      </Card>
    </>
  );
}
