# CareLens360 project instructions

## Mission and default scope

Build an evidence-first Patient and Member 360 copilot on Snowflake. Use only
synthetic healthcare fixtures. Separate structured facts, document evidence,
calculated risk, missing evidence, and conflicting evidence. Never diagnose,
recommend treatment, or present demo scores as clinically validated.

Implement the **full MVP in the main PDF**, as explicitly approved on 2026-10-05:
500 members; 5,000 encounters; 10,000 claims; 3,000 labs; 1,000 medication events;
500 clinical notes; 100 safety/regulatory documents; diabetes, hypertension,
CKD, asthma, and heart failure; all four screens; all five roles and governance
controls. The two-day PoC reductions are superseded, not defaults.

## Load context before implementation

1. Read [.cortex/memory/MEMORY.md](./.cortex/memory/MEMORY.md), then its project,
   decision, and status entries. Memory is curated Markdown, not an assumption
   that arbitrary files are automatically injected by Cortex.
2. Read [MVP scope](./docs/MVP_SCOPE.md) and the relevant contract:
   [architecture](./docs/ARCHITECTURE.md), [risk model](./docs/RISK_MODEL.md),
   [agent answers](./docs/AGENT_CONTRACT.md), or [governance](./docs/GOVERNANCE.md).
3. Check the current files and Snowflake state before treating stored status as
   current. Existing scripts are drafts, not proof of deployment.
4. Use the relevant [project skills](./.cortex/skills/). Resolve their relative
   links from the canonical `.cortex/skills/<name>/` location.

## Implementation rules

- Confirm the approved database and four-schema placement before deployment;
  the PDF does not prescribe a database name. Reconcile existing
  `PATIENT_360_RAG` drafts and the historical `CARELENS360_POC` proposal. Never silently
  rename deployed objects or execute destructive `CREATE OR REPLACE` scripts.
  Current approval is isolated `CARELENS360_MVP` with RAW/CURATED/SEMANTIC/APP.
  Use the managed-database guard and [workflow](./docs/WORKFLOW.md), not legacy drafts.
- Use Cortex Analyst over the governed semantic view for structured facts and
  exact counts; Cortex Search for documents; both for mixed questions. Never
  infer population counts from top-k search results.
- Parse documents with `AI_PARSE_DOCUMENT(TO_FILE(...), ...)`, preserving pages.
  Check the installed/account-supported signature and output before deployment.
  Do not parse CSVs as documents or introduce a custom vector database.
- Preserve document ID, member association, source path, date, section, page,
  chunk ID, and all seven filter attributes. A shared guideline may have no
  member ID; it is not evidence that the member has a diagnosis.
- Cite every factual claim. Validate actual page content, not just the existence
  of a filename. Cite structured records or query lineage for table-derived facts.
- Use the five-section [answer template](./docs/AGENT_CONTRACT.md). Reject
  ungrounded output; explicitly distinguish tool errors from missing evidence.
- Risk points are fixed by the design; clinical trigger thresholds and time
  windows are not. Do not invent them. Record and obtain approval for unresolved
  definitions in [decisions](./.cortex/memory/DECISIONS.md).
- Apply each of the six risk factors at most once per member per scoring run.
  Record source evidence and rule version; missing data is not a negative finding.
- Freeze seed, as-of date, configuration versions, and expected answers for
  evaluation. Do not use the machine's changing date for demo lookback windows.
- Use least privilege. Never store secrets, tokens, real PHI, account credentials,
  or temporary signed URLs in Markdown or evidence logs.
- Keep contributor ownership: Spurthi coordination/governance/demo; Vinay
  semantics/agent/risk; Bhakti documents/Search; Adithya synthetic/curated data.
  Make handoffs explicit and avoid unrelated edits in another workstream.
- Implement Population Insights, member/plan row-level filtering, classification,
  audit logging, pipeline audit records, and automated refresh as MVP deliverables,
  not post-PoC stretch work. Negative-test every role and isolation boundary.
- Use dated evidence and explicit conflict reporting; preserve evidence-graph
  relationships. Analytical Search remains optional because the PDF labels it so.

## Validation and session completion

Follow [evaluation gates](./docs/EVALUATION.md). Capture actual artifacts for
Planning, Development, Execution, and Testing; do not manufacture successful
logs. UI evidence inputs mean tool results and citations, not hidden reasoning.

At a meaningful milestone, use
[carelens-project-memory](./.cortex/skills/carelens-project-memory/SKILL.md)
to update status and handoff with evidence, blockers, and exact next steps.
Mark unrun validation as **NOT RUN**. Keep memory small and avoid duplicating
contracts or persisting private conversation transcripts.

See [Cortex setup](./docs/CORTEX_SETUP.md) for CLI/Desktop discovery. Do not modify
global user configuration or install skills globally unless explicitly requested.
