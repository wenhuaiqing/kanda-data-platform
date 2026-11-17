// The data layer: what landed, what each stage did to it, what was published,
// how it maps onto Fabric, and proof that the same landing zone gives the
// same tables.

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { useTheme } from "../../context/ThemeContext.jsx";
import { CHECK_LABEL, STATUS_LABEL, api, fmtAud, fmtDateTime, fmtInt, fmtMs, fmtTime, useApi } from "../../lib/api.js";
import {
  Badge, CTAButton, Callout, Card, ErrorNote, Grid, KeyValues, Loading, Mono, PageHeader, SectionTitle, Select, Stat, Table,
} from "../../lib/ui.jsx";

const LAYER_TONE = { Bronze: "serious", Silver: "neutral", Gold: "warning", Control: "neutral" };

function Lineage({ samples }) {
  const { t } = useTheme();
  const [id, setId] = useState(samples[0]?.shift_id);
  const { data, error } = useApi(id ? `/api/lineage?shift_id=${id}` : null);
  const s = data?.shift;
  return (
    <Card title="From a claim line back to the rows it came from" right={
      <Select label="Service" value={id} onChange={setId}
        options={samples.map((d) => ({ value: d.shift_id, label: `${d.shift_id}: ${d.check_id ? `held, ${CHECK_LABEL[d.check_id]}` : STATUS_LABEL[d.status]}` }))} />
    } hint="Every service carries the roster file and row it was read from, and every phone event the file and line it arrived on. Notes are shown masked, as they are stored.">
      <ErrorNote error={error} />
      {s && (
        <Grid cols={2} min={380}>
          <div>
            <KeyValues items={[
              ["Roster file", <Mono>{s.file} row {s.raw_row}</Mono>],
              ["File SHA-256", <Mono dim>{data.file.sha256.slice(0, 20)}...</Mono>],
              ["Client / worker", <Mono>{s.client_id} / {s.worker_id}</Mono>],
              ["Rostered", `${fmtDateTime(s.start_local, { seconds: false })} to ${fmtTime(s.end_local, { seconds: false })} (${s.rostered_min} min)`],
              ["Evidence", s.evidence === "complete" ? `${fmtTime(s.check_in, { seconds: false })} to ${fmtTime(s.check_out, { seconds: false })} (${s.evidenced_min} min)` : (s.evidence || "-")],
              ["Item and rate", `${s.item_code} at ${fmtAud(s.rate, { decimals: 2 })} an hour (limit ${fmtAud(s.price_limit, { decimals: 2 })})`],
              ["Status", s.status === "held" ? `Held: ${CHECK_LABEL[s.check_id]}` : `${STATUS_LABEL[s.status]}, ${fmtAud(s.claim_amount, { decimals: 2 })}`],
            ]} />
            {data.exception && <p style={{ fontSize: 12.5, color: t.textMuted, lineHeight: 1.5, margin: "12px 0 0" }}>{data.exception.reason}</p>}
          </div>
          <div>
            <Table maxHeight={260} columns={[
              { key: "event_id", label: "Event", render: (r) => <Mono>{r.event_id}</Mono> },
              { key: "event_type", label: "Type" },
              { key: "ts_local", label: "At", render: (r) => fmtTime(r.ts_local, { seconds: false }) },
              { key: "lag_minutes", label: "Landed after", align: "right", render: (r) => `${fmtInt(r.lag_minutes)} min` },
              { key: "note_masked", label: "Note (masked)", wrap: true, render: (r) => r.note_masked || "-" },
            ]} rows={data.events} empty="No events in the governed table for this service." />
            {data.events_quarantined.length > 0 && (
              <p style={{ fontSize: 12, color: t.status.warning, margin: "8px 0 0" }}>
                {data.events_quarantined.length} event(s) for this service are in quarantine: {data.events_quarantined[0].detail}
              </p>
            )}
            {data.duplicates.length > 0 && (
              <p style={{ fontSize: 12, color: t.textMuted, margin: "8px 0 0" }}>
                {data.duplicates.length} copy(ies) removed: {data.duplicates.map((d) => `${d.event_id} (${d.reason})`).join("; ")}.
              </p>
            )}
          </div>
        </Grid>
      )}
    </Card>
  );
}

function Rerun() {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const go = async () => {
    setBusy(true);
    setErr(null);
    try { setRes(await api("/api/replay", { method: "POST" })); } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  return (
    <Card title="Re-run the quarter from the landing zone" hint="Reads the landed files from disk, re-hashes them against the manifest pinned in the repository, re-runs the pipeline under the contract versions in force and compares every partition's digest with the one behind the tables on screen.">
      <div><CTAButton icon={RotateCcw} onClick={go} disabled={busy}>{busy ? "Running..." : "Re-run and compare"}</CTAButton></div>
      {err && <div style={{ marginTop: 12 }}><Callout tone="critical" title="Refused">{err.message}</Callout></div>}
      {res && (
        <div style={{ marginTop: 12 }}>
          <Callout tone={res.all_match ? "good" : "critical"} title={res.all_match ? "Identical" : "Different"}>
            {res.files.length} landed files and {res.partitions.length} governed partitions re-derived in {fmtMs(res.wall_ms)}.{" "}
            {res.all_match ? "Every digest matches." : "At least one digest differs."}
          </Callout>
          <Table maxHeight={240} columns={[
            { key: "partition", label: "Partition", render: (r) => <Mono>{r.partition}</Mono> },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "sha256", label: "SHA-256", render: (r) => <Mono dim>{r.sha256.slice(0, 16)}</Mono> },
            { key: "match", label: "Recorded", render: (r) => <Badge tone={r.match ? "good" : "critical"}>{r.match ? "matches" : "differs"}</Badge> },
          ]} rows={res.partitions} />
        </div>
      )}
    </Card>
  );
}

export default function Lakehouse() {
  const { data, error } = useApi("/api/lakehouse");
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const rawRows = data.files.reduce((n, f) => n + f.rows, 0);
  const held = Object.fromEntries(data.by_check.map((c) => [c.check_id, c]));

  return (
    <>
      <PageHeader
        title="Lakehouse & lineage"
        brief="Experience delivering cloud data warehouses or Lakehouse platforms into production."
        subtitle="The five sources land as files and are hashed (bronze). Six timed stages check them against their contracts, de-duplicate and mask (silver), pair each shift with its evidence and run nine checks before a claim leaves (gold). Nothing is dropped on the way, every row traces to the file and line it came from, and a re-run from the landing zone reproduces every partition byte for byte. Here it runs in DuckDB because a quarter fits in memory; the table below maps each piece onto a Fabric Lakehouse."
      />
      <Grid cols={4} min={200}>
        <Stat label="Landed files" value={data.files.length} sub={`${fmtInt(rawRows)} rows, hashed on landing`} />
        <Stat label="Governed tables" value={data.tables.filter((x) => x.layer === "Gold").length} sub={`${data.partitions.length} partitions digested`} />
        <Stat label="Last run" value={fmtMs(data.run.wall_ms)} sub={`${data.run.run_id}, ${data.run.kind}; ${fmtAud(data.run.cost_aud, { decimals: 6 })} at list price`} emphasis />
        <Stat label="Triggered by" value={data.run.trigger} sub={fmtDateTime(data.run.started_at, { seconds: false })} />
      </Grid>

      <SectionTitle>Stages of the last run</SectionTitle>
      <Card>
        <Table columns={[
          { key: "stage", label: "Stage", render: (r) => <b>{r.stage}</b> },
          { key: "note", label: "What it did", wrap: true },
          { key: "rows_in", label: "In", align: "right", render: (r) => fmtInt(r.rows_in) },
          { key: "rows_out", label: "Out", align: "right", render: (r) => fmtInt(r.rows_out) },
          { key: "held", label: "Held", align: "right", render: (r) => r.held ? fmtInt(r.held) : "-" },
          { key: "wall_ms", label: "Time", align: "right", render: (r) => fmtMs(r.wall_ms) },
        ]} rows={data.stages} />
      </Card>

      <SectionTitle>The nine checks before a claim, in the order they run</SectionTitle>
      <Card hint="Hold, never guess: a check that cannot decide holds the service and records why.">
        <Table columns={[
          { key: "label", label: "Check", render: (r) => <b>{r.label}</b> },
          { key: "what", label: "Passes when", wrap: true },
          { key: "held", label: "If it fails", wrap: true },
          { key: "n", label: "Held", align: "right", render: (r) => fmtInt(held[r.id]?.held || 0) },
        ]} rows={data.checks} maxHeight={520} />
      </Card>

      <div style={{ marginTop: 14 }}><Lineage samples={data.samples} /></div>
      <div style={{ marginTop: 14 }}><Rerun /></div>

      <SectionTitle>The same design on Microsoft Fabric</SectionTitle>
      <Card hint="The advertisement describes a Fabric Lakehouse. This is how each piece here would map onto one; nothing here claims to know how Kanda's is set up.">
        <Table columns={[
          { key: "here", label: "Here", wrap: true },
          { key: "fabric", label: "In Fabric", wrap: true },
        ]} rows={data.fabric} />
      </Card>

      <SectionTitle>What is stored</SectionTitle>
      <Grid cols={2} min={420}>
        <Card title="Landed files (bronze)">
          <Table maxHeight={360} columns={[
            { key: "file", label: "File", render: (r) => <Mono>{r.file}</Mono> },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "sha256", label: "SHA-256", render: (r) => <Mono dim>{r.sha256.slice(0, 12)}</Mono> },
          ]} rows={data.files} />
        </Card>
        <Card title="Tables">
          <Table maxHeight={360} columns={[
            { key: "name", label: "Table", render: (r) => <Mono>{r.name}</Mono> },
            { key: "layer", label: "Layer", render: (r) => <Badge tone={LAYER_TONE[r.layer]}>{r.layer}</Badge> },
            { key: "rows", label: "Rows", align: "right", render: (r) => fmtInt(r.rows) },
            { key: "what", label: "Holds", wrap: true },
          ]} rows={data.tables} />
        </Card>
      </Grid>
    </>
  );
}
