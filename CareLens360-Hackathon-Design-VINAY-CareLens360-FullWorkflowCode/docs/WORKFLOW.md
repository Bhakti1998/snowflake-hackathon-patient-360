# Implemented adaptation and Snowflake workflow

## State and approvals

The user approved `CARELENS360_MVP`, seed 42,
as-of 2026-09-30 and `synthetic-demo-v1` rules on 2026-10-05.
`config/workflow.json` uses a `<YOUR_CONNECTION>` placeholder; replace it with
your named connection from `~/.snowflake/connections.toml` before deploying.
The original seed folder is read-only input and is not modified.

**Live execution is blocked by authentication.** Existing OAuth timed out;
the explicitly approved external-browser retry returned Snowflake 390190
(SAML identity-provider configuration). The user chose local implementation
and validation while fixing authentication. No account resources were created.

## Files and data boundaries

- [Workflow configuration](../config/workflow.json): approved synthetic rules and names; no credentials.
- [Adapter](../src/carelens/dataset.py): deterministic full-volume JSONL and PDF fixtures, source checksums, missingness, exclusions and local oracle.
- [Risk oracle](../src/carelens/risk.py): independently testable six-factor scoring.
- [SQL builders](../src/carelens/sql.py): stages, RAW payloads, curated model, secure views, scoring and semantics.
- [Refresh handler](../snowflake/refresh.py): Snowflake-hosted incremental load/parse/chunk procedure and audit.
- [Deployment runner](../src/carelens/deploy.py): bounded stages with actual query evidence and failure logging.
- [Streamlit](../app/streamlit_app.py): all four screens and plan-specific native Agent invocation.
- [Verifier](../src/carelens/verify.py): account DQ, independent risk comparison, page/chunk checks and scoped Search smoke tests.

Generated data goes to `data/generated/<version>/` (ignored by Git). The adapter
hashes all original files before/after generation. It does not execute or modify
the seed generators or copy their legacy scores, expected answers, traces,
derived summaries or contradictory policy documents into the retrieval corpus.

The new corpus contains 500 members, 5,000 encounters, 10,000 **medical** claims,
3,000 labs, 1,000 medications, 500 two-page notes and 100 distinct synthetic
safety/regulatory references (50 Safety Reports and 50 Regulatory Guidelines).
Pharmacy fills and conditions are additional.
These are synthetic testing references, not official medical guidelines.
Normalization reuses linked observations but generates new claims and notes;
it is not a lossless migration of every seed artifact.

Condition and medication metadata are string arrays; use Search `@contains`
to match individual values, preserving coexisting conditions and drugs.
P002 contains an explicitly
marked contradictory adherence observation on page 2, alongside fill-derived
PDC. Evaluation must report both without silently changing the deterministic
fill-based score. Other negatives cover absent labs and discharge-summary type,
unknown members, unsupported conditions and treatment requests.

Members with no source lab observations remain explicit missing-data fixtures;
their scores are Incomplete. Do not manufacture normal labs to fill missingness.
Patient P001 resolves to enrollment MBR-10001. Ages are recomputed from DOB.
Medication PDC is covered distinct days clipped to the 183-day window, not the
seed's randomly assigned percentage. Full-history ED counts are separate from
the 90-day risk trigger; Analyst queries exact event dates.

## Approved synthetic rule definitions

Windows include the as-of day: N days means `[as_of-(N-1), as_of]`.

| Factor | Demo trigger | Points |
|---|---|---:|
| Uncontrolled lab | Latest observation per test within 180 days is source-flagged HIGH/LOW/ABNORMAL | 30 |
| Recent ED | At least one distinct ED encounter within 90 days | 20 |
| Adherence concern | Active non-PRN medication covered-days PDC <80% over 183 days | 15 |
| Multiple chronic conditions | At least two distinct active condition keys | 15 |
| Care gap | Unresolved TRC follow-up gap with due date <= as-of | 10 |
| Recent adverse event | Recorded event within 90 days | 10 |

High-risk population is High + Critical. Drug A aliases Lisinopril.
Absent labs/eligible medication inputs produce UNKNOWN, not a finalized low tier.
Source collection completeness is a synthetic-fixture assumption for encounter,
condition, care-gap and adverse-event absence. These rules are not clinical guidance.

## Local commands

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/carelens generate \
  --seed-folder /Users/vr11/Downloads/hcls360_dataset \
  --output data/generated/v5
.venv/bin/python -m pytest -q
.venv/bin/carelens render-sql
```

The validated local corpus is version v5; earlier versions are development outputs.
Generation rejects a nonempty destination. Use a new version directory on rerun,
not deletion/overwrite of the original seed. `manifest.json` records source
checksums, exclusions, counts and config; `expected_factors.jsonl` is an independent
local scoring oracle; `evaluation_cases.json` holds NOT RUN golden/negative cases.
Rendered SQL is a review artifact, not a claim of successful Snowflake compilation.

## Deploy after authentication is fixed

Select an existing authorized warehouse; `YOUR_WAREHOUSE` below is a placeholder.
The setup principal needs project DDL/grant/role privileges plus the Cortex and
Streamlit capabilities used. Do not paste passwords or tokens into chat/files.
The warehouse-runtime app uses `CURRENT_USER()` and a row access policy.
Snowflake requires an ACCOUNTADMIN to grant **READ SESSION** on the account to
the app's owner role for this use. Arrange that privilege separately; the runner
does not silently grant account-global privileges. See
[Snowflake's row-access guidance](https://docs.snowflake.com/en/developer-guide/streamlit/features/row-access).
Do not switch to container owner-rights runtime without reworking authorization.

```bash
.venv/bin/carelens check-access
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase base \
  --apply --confirm-database CARELENS360_MVP
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase procedure \
  --apply --confirm-database CARELENS360_MVP
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase parse --parse-limit 10 \
  --apply --confirm-database CARELENS360_MVP
```

Start with ten documents to verify parse/model availability and actual spending.
Then repeat parse batches or use `--parse-limit 600` to finish the corpus.
The workflow logs parse/chunk failures, preserves old committed chunks when a
replacement fails, and retries only pending/changed versions. All generated
inputs are PDFs; seed format variants remain quarantined rather than silently
passed to unsupported parser modes.

Manifest-driven uploads also accept version-checked PDF/DOCX/PPTX artifacts
inside the generated documents directory. Account support remains a live gate.
For DOCX, the section labels the parser-rendered layout page; it is not a claim
that Word has an immutable native page number. Preserve source SHA/version and
review the rendered-page citation before release.

```bash
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase services \
  --apply --confirm-database CARELENS360_MVP
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase roles \
  --apply --confirm-database CARELENS360_MVP
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase app \
  --apply --confirm-database CARELENS360_MVP
.venv/bin/carelens deploy --warehouse YOUR_WAREHOUSE --phase verify \
  --apply --confirm-database CARELENS360_MVP
```

Each phase is explicit; `all` stops if unparsed documents remain after its bounded
parse batch. Do not run it expecting all 600 documents to parse with the default 10.
Deployments replace **managed MVP** views/procedures/agents/app, not legacy drafts.
Existing unmarked databases are rejected. JSONL loads MERGE stable keys and
updated versions; this is upsert semantics, not implicit deletion sync.

## Governance and costs

Only the deployment principal is initially entitled to all plans. Other users
are denied until a project administrator explicitly adds their entitlement and
assigns an appropriate role. Do not grant `*` to demo users.

Four plan-specific Search services and plan-specific Agents are the backend
boundaries used by the app; shared references have a separate service. The
all-plan `CARE_LENS_AGENT` and Search are admin-only, not demo endpoints.
The role phase does not assign roles to users or open direct Agent/Search access
to reviewer/demo roles. Analyst/reviewer display access uses governed APP views.
App deployment grants Streamlit usage only to CARE_ADMIN. Reviewer/demo sharing
is deliberately gated, not automatic. Before granting their app usage, provision
and test a dedicated least-privilege app owner role with no direct RAW access,
the required READ SESSION privilege, and only the governed views/scoped services
needed by the app. The development app is initially owned by the deployment
role and must not be broadly shared with that role's unrestricted privileges.
The current entitlement granularity is a plan (or administrator `*`), not an
arbitrary individual-member grant. Member selection constrains displayed
citations, but is not itself a separate user authorization grant.
Check owner-rights behavior and CURRENT_USER propagation with two real
entitled users before sharing the Streamlit application. A local test cannot
prove those account-specific authorization semantics.

Search creates serving/embedding costs; warehouse/parse/Agent calls also cost
credits. The hourly refresh task is created **suspended**. After measuring costs
and passing account checks, explicitly approve its schedule, then run:

```sql
ALTER TASK CARELENS360_MVP.APP.REFRESH_TASK RESUME;
```

The task reloads staged JSONL idempotently, refreshes live curated/risk views,
parses a bounded pending batch, and commits chunks for Search's target-lag refresh.
Its owner executes the pipeline. Uploads are explicit external inputs; scheduling
does not magically upload new local files.

## What remains NOT RUN

- Snowflake DDL compilation/feature availability, upload, parsing and SQL/Python scoring comparison.
- Agent tool specifications/model readiness and all eight golden answers.
- Full factual support review: format/source traceability checks are not an
  automatic proof that every natural-language claim is entailed by a citation.
- All-role/two-user policy tests, source access, UI behavior and actual audit outcomes.
- Dedicated least-privilege app-owner provisioning and reviewer/demo sharing.
- Changed-input task execution and measured Search/index/app freshness.

The app checks pipeline status and source-update version, invalidates cached
answers/conversation after changed inputs, and refuses questions while required
documents are pending/failed. Serving/display queries match manifest SHA to
committed chunks; stale cached Search citations are rejected rather than
accepted as fresh evidence. Verify these guards in the account.

Use [evaluation gates](./EVALUATION.md); failing or unrun mandatory gates block
MVP completion. Authentication repair is the immediate live-deployment prerequisite.
