# CareLens360

Evidence-First Patient & Member 360 Copilot built on Snowflake Cortex.

CareLens360 is a healthcare evidence copilot that uses synthetic data to
demonstrate traceable, governed answers over structured records and clinical
documents. It distinguishes between structured facts, document evidence,
calculated risk indicators, missing or conflicting information, and
unsupported conclusions. It is not a diagnostic or treatment system.

## What it does

- **Member Search** — filter 500 synthetic members by risk tier, condition,
  and plan
- **Member 360** — diagnoses, medications, encounters, labs, claims, care
  gaps, and a transparent six-factor risk breakdown
- **Evidence Copilot** — natural-language questions answered by a Cortex
  Agent that orchestrates Cortex Analyst (structured SQL) and Cortex Search
  (clinical notes and safety guidelines), with page-level citations and
  scope-refusal guardrails
- **Population Insights** — risk distribution, condition cross-tabs,
  utilization and adherence metrics

## Architecture

```text
CARELENS360_MVP
  RAW         16 tables — EHR files, document manifest, parse results, pipeline audit
  CURATED     13 views + document chunks — dimensions, facts, derived tables
  SEMANTIC    5 semantic views + 6 Cortex Search services
  APP         5 Cortex Agents + Streamlit app + governance views + audit log
```

| Component | Count |
|-----------|-------|
| Synthetic members | 500 |
| Documents (parsed via AI_PARSE_DOCUMENT) | 600 |
| Document chunks (measured overlap) | 1,100 |
| Cortex Search Services (plan-scoped + shared) | 6 |
| Semantic Views (plan-scoped) | 5 |
| Cortex Agents (plan-scoped) | 5 |
| Governance roles (RBAC) | 5 |
| Streamlit screens | 4 |
| Unit tests | 42 |

## Tech stack

- **Snowflake Cortex Agents** — orchestration with 300s/32k-token budget
- **Cortex Analyst** — text-to-SQL over semantic views
- **Cortex Search** — vector search over parsed document chunks
- **AI_PARSE_DOCUMENT** — PDF text extraction with page provenance
- **Streamlit in Snowflake** — four-screen governed application
- **Cortex Code (CoCo) Desktop** — development, deployment, and testing

## Quick start

### Prerequisites

- Python 3.9+
- A Snowflake account with Cortex features enabled
- A named connection in `~/.snowflake/connections.toml`

### Setup

```bash
git clone <this-repo>
cd CareLens360-Hackathon-Design

# Python environment
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'

# Run tests
.venv/bin/python -m pytest -q
# Expected: 42 passed

# Configure connection
# Edit config/workflow.json — set connection_name to your named connection
```

### Deploy to Snowflake

```bash
WH=COMPUTE_WH
DB=CARELENS360_MVP

# Phase 1: Database, schemas, structured data, documents
.venv/bin/carelens deploy --warehouse $WH --phase base --apply --confirm-database $DB

# Phase 2: Stored procedure
.venv/bin/carelens deploy --warehouse $WH --phase procedure --apply --confirm-database $DB

# Phase 3: Parse documents (600 PDFs)
.venv/bin/carelens deploy --warehouse $WH --phase parse --parse-limit 10 --apply --confirm-database $DB
.venv/bin/carelens deploy --warehouse $WH --phase parse --parse-limit 590 --apply --confirm-database $DB

# Phase 4: Search services, semantic views, agents
# (can run while parsing is in progress via Python — see docs/WORKFLOW.md)

# Phase 5: Governance roles
.venv/bin/carelens deploy --warehouse $WH --phase roles --apply --confirm-database $DB

# Phase 6: Streamlit app
.venv/bin/carelens deploy --warehouse $WH --phase app --apply --confirm-database $DB

# Verify
.venv/bin/carelens deploy --warehouse $WH --phase verify --apply --confirm-database $DB
# Expected: 26/26 checks pass
```

## Governance

Five roles with least-privilege access:

| Role | Access |
|------|--------|
| CARE_ADMIN | Full access to all schemas and agents |
| CARE_DATA_ENGINEER | Pipeline access (RAW, CURATED, SEMANTIC) |
| CARE_ANALYST | Curated views |
| CARE_REVIEWER | Member 360 views |
| CARE_DEMO_USER | Streamlit app only |

Every Copilot interaction is logged to `APP.ACCESS_AUDIT` with request ID,
username, plan, operation, and status.

## Risk model

Transparent rule-based scoring (not a validated clinical model):

| Factor | Points | Trigger |
|--------|--------|---------|
| Uncontrolled lab | 30 | HIGH/LOW/ABNORMAL flag within 180 days |
| Recent ED visit | 20 | ED encounter within 90 days |
| Adherence concern | 15 | PDC below 0.8 over 183 days |
| Multiple chronic conditions | 15 | 2+ active chronic condition keys |
| Care gap | 10 | Open or missed care gap |
| Recent adverse event | 10 | Adverse event within 90 days |

Tiers: Low (0-24), Moderate (25-49), High (50-74), Critical (75-100).

## Agent answer contract

Every Copilot answer follows a strict five-section format:

1. **Summary** — one-paragraph evidence synthesis
2. **Key Evidence** — table with Evidence, Value, Source columns
3. **Risk Drivers** — factor breakdown with point values
4. **Evidence Citations** — document ID, page number, source file, date
5. **Limitations** — data boundaries and caveats

Answers end with a synthetic-data disclaimer. Diagnostic or treatment
requests receive a scope refusal. Answers without verifiable citations
are withheld.

## Project structure

```text
app/                    Streamlit application files
config/workflow.json    Deployment configuration (set your connection_name)
data/                   Seed data and generation scripts
docs/                   Scope, contracts, architecture, evaluation, governance
evidence/               Deployment logs (gitignored)
snowflake/              Stored procedure source
src/carelens/           Python package — CLI, deployment, agent, risk, response
tests/                  42 unit tests
```

## Documentation

- [AGENTS.md](./AGENTS.md) — project instructions and validation rules
- [docs/MVP_SCOPE.md](./docs/MVP_SCOPE.md) — full MVP scope and ownership
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — object placement and contracts
- [docs/RISK_MODEL.md](./docs/RISK_MODEL.md) — six-factor scoring rules
- [docs/AGENT_CONTRACT.md](./docs/AGENT_CONTRACT.md) — answer format and guardrails
- [docs/GOVERNANCE.md](./docs/GOVERNANCE.md) — roles, policies, and audit
- [docs/EVALUATION.md](./docs/EVALUATION.md) — golden questions and gates
- [docs/WORKFLOW.md](./docs/WORKFLOW.md) — deployment phases and state
- [docs/DEMO_RUNBOOK.md](./docs/DEMO_RUNBOOK.md) — demo steps and evidence

## Built with

[Cortex Code (CoCo) Desktop](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code)
on Snowflake Cortex.
