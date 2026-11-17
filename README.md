# Kanda - data platform workbench

**A care provider's service data, from five source systems to the claim run,
governed.** Rosters, check-ins from support workers' phones, client funding,
worker screening and the support catalogue: landed under data contracts,
checked before anything is claimed, with personal information kept in the
landing zone, access enforced by role in the data, and an AI agent that reads
what the checks hold - graded against the runbook, citing the policy it
retrieved.

> **Built for a job application to Kanda (Data Platform Lead). Not affiliated
> with or endorsed by Kanda.** **All data is synthetic.** The provider, its
> clients, workers, plans, policies, support catalogue, prices and the app
> vendor are invented and generated from a seed by
> `backend/src/app/pipeline/generate.py`. Service delivery and claiming were
> chosen because every care provider has them, not because of anything known
> about how Kanda works. The logo, favicon and colours are Kanda's own, taken
> from its public website, and are used only to show what the work would look
> like in its hands.

## What it shows

| | |
|---|---|
| **Sources & contracts** | Six feeds from five source systems, each under a YAML contract: owner, schedule, freshness, fields with types and classification, rules. 27,136 rows landed and hashed; 976 broke a contract and are in quarantine with the rule they broke. Evidence lateness measured against the nightly claim run's 06:00 cut-off. |
| **A vendor release, handled** | From 08/09/2026 the mobile app vendor's release 5.0 renamed a field and sent times in UTC. Contract v1 quarantined every such event; the platform proposed contract v2 with evidence (958 of 958 events land inside their rostered window as UTC + 10 h, 0 of 958 read as local) and a preview (479 services worth $85,974 released, no new holds). Someone other than the proposer approves; the quarter reprocesses from the landing zone. |
| **Lakehouse & lineage** | Bronze, silver, gold in six timed stages; every claim line traced to its roster row and phone events; every partition digested; a re-run from the landing zone reproduces the tables byte for byte. Each piece mapped onto its Microsoft Fabric equivalent. |
| **Checks before a claim** | Nine checks in a fixed order - identity, evidence, screening, one place at a time, funding, item, price limit, time evidenced, budget. Of 8,738 services, 90.6% are claimable with nobody touching them ($1.43M); 820 are held ($147k) with the reason. Hold, never guess; nothing is dropped. |
| **What controls are worth** | Each control switched off and the quarter re-run: $120,204 that would be claimed in error, $14,535 claimed without clearance, 783 notes that would carry a client's name, phone or NDIS number into every table and the model. |
| **AI triage** | A tool-calling agent (six record tools over a frozen, masked snapshot, plus policy search) that submits a typed verdict with evidence and policy citations. Graded against the runbook on 30 labelled cases: 22 standard, 5 where the check's name points at the wrong answer, 3 where a note in the app tries to talk its way to a claim. It proposes; it cannot write. |
| **Policy assistant (RAG)** | Eight synthetic policies in 28 sections; BM25 retrieval measured on 16 questions (governing section in the top three for 16 of 16, MRR 0.83); answers generated only from what was retrieved, citations checked, "not covered" when it is not. |
| **Governed access & BI** | Roles as views carrying their row filter (a regional coordinator, Finance, Executive, the agent), the same filters as Power BI DAX RLS, a query box that runs as a role, and nine measures defined once in SQL and DAX. |
| **Privacy** | No governed table, view, query result or model snapshot holds a name, date of birth, phone, address or NDIS number - tested on every build. Free-text notes masked before they leave the landing zone. |
| **Lead** | A platform roadmap with risk tiers, vendors and the ask of each, requirements traced to tests, acceptance scenarios that run as queries, a RAID log kept as the work went, and a First 90 days plan that starts by listening. |

## Pages

Platform overview · Sources & contracts · Lakehouse & lineage · Claim exceptions ·
What controls are worth · AI triage · Policy assistant (RAG) · Privacy & AI risk ·
Governed access & BI · Roadmap, vendors & RAID · Operations · First 90 days.

## Architecture

```
  data/raw/                                    scripts/build_platform.py (in the image build)
   crm/ hr/ catalogue/ rostering/ mobile/      generate -> pipeline -> ablation -> proposals
        │ hashed on landing (bronze)           -> acceptance scenarios -> verify against
        ▼                                         infra-azure/build.sha256
  ┌────────────────── pipeline ───────────────────┐
  │ land · contracts (quarantine) · conform        │──► quarantine, event_duplicates
  │ (dedupe, v2 mapping, mask notes) · evidence ·  │
  │ nine checks · publish                          │──► partition digests (the re-run contract)
  └──────────────────┬─────────────────────────────┘
                     ▼
  gold: dim_client, dim_worker, dim_plan, dim_support_item,
        fact_shift, fact_visit_event, exceptions
                     ▼
  role views: coordinator_bn.*, finance.*, executive.*, triage_agent.*
                     ▼
  DuckDB (one file) ◄── FastAPI ◄── nginx ◄── React SPA
                           │
                           ├─ triage agent ──► policy search (BM25) + any OpenAI-protocol model,
                           │                   a fallback model, then the runbook - said on screen
                           └─ policy assistant (retrieve, answer from it, cite)
```

The checks are deterministic rules; the model only reads what they hold.
`delivery/raid.yaml` records that decision and six others.

At this size the lakehouse is DuckDB in one file. The same layout is a Fabric
Lakehouse at production scale - Files and Delta tables, notebooks in a
scheduled Data pipeline, the SQL endpoint, a Direct Lake semantic model with
the same measures and RLS - and with real client data the model would be one
deployed in the organisation's own tenancy. The agent code depends on the
protocol, not the provider.

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node 20.

```bash
cd backend
uv sync
uv run python ../scripts/build_platform.py     # about 6 s; verifies against the pinned manifest
cp ../.env.example ../.env                      # model key optional; DEMO_WRITE_TOKEN for decisions
uv run uvicorn src.main:app --port 8071

cd ../frontend
npm install
npm run dev                                     # http://localhost:5271
```

Open `http://localhost:5271/?write_token=<DEMO_WRITE_TOKEN>` once to unlock
decisions and approvals in that browser session. The plain link is read-only,
and the server says why it refuses.

## Checks

```bash
cd backend
uv run pytest                                   # pipeline, privacy, workflow, triage, policy, delivery record
uv run python ../evals/run_triage_eval.py       # agent + runbook + policy answers, graded; writes evals/status.json
uv run python ../evals/run_triage_eval.py --rules     # runbook only, no model key needed

cd ../frontend
npx playwright install chromium                 # once
node evals/check-pages.mjs                      # every page, desktop and phone
TOKEN=<DEMO_WRITE_TOKEN> node evals/flow.mjs    # the operator's path, end to end
```

Until the eval has been run with a model key, the AI triage and Policy
assistant pages say the agent and the answers have not been graded, rather
than implying they have. Retrieval is graded on every build.

Changing the generator, the contracts or the pipeline changes the output:
rebuild with `--write-manifest` and commit `infra-azure/build.sha256`.

## Deploy

Every push to `main` runs the checks, then builds both images and publishes
them to GitHub Container Registry (`.github/workflows/ci.yml`), tagged with
the short commit SHA. A commit whose build does not match the pinned manifest
fails there and is never published. CI holds no cloud credential: deploying
is a separate, deliberate step.

```bash
cd infra-azure
cp terraform.tfvars.example terraform.tfvars    # subscription, alert e-mail, model key (gitignored)
terraform init
terraform apply -var "image_tag=$(git rev-parse --short HEAD)"
terraform output                                # the URL; -raw demo_write_token for the unlock link
```

### What it costs

Built to cost nothing while nobody is looking at it.

| Resource | Why it is free at rest |
|---|---|
| Resource group `rg-kanda-data` | Holds everything and nothing else. Deleting it removes the deployment. |
| Container Apps, consumption plan | Scales to zero; the monthly free grant covers a demo's traffic. One replica at most. An optional business-hours warm replica is off by default. |
| Log Analytics workspace | Daily cap of 0.05 GB, inside the free allowance (none when sharing an environment). |
| Budget alert | A tripwire at $3 a month. Budgets are free. |

There is no database server, no storage account, no private registry and no
vault. The data is built inside the image; the images are public on GitHub;
the two secrets are Container Apps secrets.

A subscription may allow only two Container Apps environments in total. When
both are taken, set `existing_environment_id` in `terraform.tfvars` to one of
them: the app, its secrets and its budget still live in `rg-kanda-data` and
are removed with it.
