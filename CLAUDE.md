# kanda-data-platform

Portfolio demo: a care provider's data platform - rosters, phone check-ins,
client funding, worker screening and the support catalogue landed under data
contracts, nine checks before anything is claimed, personal information kept in
the landing zone, role-based access enforced in the data, a triage agent that
searches the policy library (RAG), graded against the runbook. Built for an
application to Kanda (Data Platform Lead) and named for it. **Not affiliated
with or endorsed by Kanda. All data is synthetic.**

## Layout

```
kanda-data-platform/
├── backend/           FastAPI + Python 3.12 (uv)
│   └── src/app/
│       ├── pipeline/  reference (every assumption and seeded defect), generate, stages,
│       │              privacy, access (role views), cases, ablation, registry, delivery, persist
│       ├── services/  analytics (reads), workflow (governed writes), replay, triage,
│       │              triage_cases, policy (BM25), policy_assistant, llm, db, auth,
│       │              rate_limit, sql_validator, timings
│       └── routers/   pages (reads), workflow (token-gated), actions (replay, triage, policy, query)
├── contracts/         one YAML data contract per feed
├── policies/          the synthetic policy library the agent and the assistant search
├── delivery/          roadmap, requirements, RAID log with vendors, UAT scenarios
├── semantic/          published measures (SQL + DAX) and the enquiry log
├── scripts/           build_platform.py - everything from nothing
├── evals/             run_triage_eval.py -> status.json
├── frontend/          React 18 + Vite; pages/<Section>/<Page>.jsx auto-discovered
└── infra-azure/       Terraform; build.sha256 is the pinned manifest
```

## How to run

```bash
cd backend && uv sync && uv run python ../scripts/build_platform.py && uv run uvicorn src.main:app --port 8071
cd frontend && npm install && npm run dev     # :5271
```

Tests: `cd backend && uv run pytest`. Pages: `cd frontend && node evals/check-pages.mjs`.
Operator path: `TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs`.

## Conventions

- **No emojis in code or output.** Australian English; dates DD/MM/YYYY on screen;
  straight quotes and hyphens only (the page check fails on typographic ones).
- Times are AEST (Queensland, no daylight saving), stored naive, labelled on screen.
- **Personal identity only.** Commits, CI, registry, README and infrastructure use
  the author's personal accounts. No employer name, work e-mail, work machine path
  or internal system appears anywhere in this repository.
- Every defect the generator seeds is declared once in `pipeline/reference.py`;
  tests assert each is found from the data. The pipeline never reads the truth file.
- Hold, never guess. Every row that lands is a governed row, a quarantine row with
  the rule it broke, or a recorded duplicate.
- Personal and sensitive fields (by contract class) never leave the landing zone;
  free text is masked before it does. Tests scan every table and every snapshot.
- Every write is token-gated, audit-logged, and refused - not warned - when the
  rule says no. The proposer of a change cannot approve it. The agent proposes;
  it cannot write.
- Numbers on screen come from the data. Handling times are assumptions, labelled.
- A requirement names the test that proves it; `tests/test_delivery.py` fails if
  that test does not exist. A UAT scenario is a query, run on every build.
- Changing the generator, contracts or pipeline changes the output: rebuild with
  `--write-manifest` and commit `infra-azure/build.sha256`, or CI and the image
  build fail.
- Azure: one resource group, scale to zero, no registry, no vault, no database.
  Do not add a resource that costs money at rest.
- Named for the organisation it was built for, and says so: the not-affiliated line
  stays in the sidebar, the First 90 days page and the README. It uses Kanda's
  public logo, favicon and palette (taken from kandacare.com.au), so that line must
  never be removed or made less visible. Nothing claims to know how Kanda operates.
