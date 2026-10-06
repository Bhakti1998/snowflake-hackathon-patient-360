# Demo and CoCo lifecycle runbook

Owner: Spurthi; handoffs per [MVP_SCOPE.md](./MVP_SCOPE.md).
Use either CLI or Desktop to perform the work, and label which surface produced
each artifact. The original plan names coco-cli as lifecycle driver; Desktop
reuse does not retroactively prove a required CLI run occurred.

## Evidence layout

Create these paths only when there are actual artifacts to save:

```text
evidence/
  planning/       Scope, ontology/table map, risk definitions, access plan
  development/    DDL, generator/seed, parse/chunk/search, semantics, agent/UI versions
  execution/      Load/parse/refresh/invocation outputs and query/run IDs
  testing/        DQ, golden/negative cases, citation metrics, permissions
  demo/           Rehearsal notes, approved recording, final manifest
```

Evidence is an explicit run output, not a skeleton full of presumed passes.
The final manifest maps artifact path, phase, owner, timestamp, runtime surface,
namespace/config version, outcome, and relevant query/run ID.

## Four lifecycle boundaries

| Phase | Capture | Timing |
|---|---|---|
| Planning | Ontology/table relationships, semantic plan, risk-factor definitions, five-role/isolation/classification/audit plan | Foundation kickoff |
| Development | Actual DDL/code, full-volume generator/seed, parse/chunker/Search, semantic YAML, agent, all four screens and governance controls | Implementation phases 1-6 |
| Execution | Ingestion, parse/chunk/index runs, actual agent/population queries, app launch, incremental/automated refresh | As each pipeline and application milestone becomes runnable |
| Testing & Validation | Eight golden results, negatives, citation metrics, full-corpus DQ, five-role/isolation/classification/audit/refresh tests | Phase 7 and milestone regressions |

Incremental refresh and rerun behavior should be demonstrated with actual logs.
Automated ingestion/validation and refresh are required full-MVP deliverables.
If unimplemented, record them as blockers to completion, not optional deferrals.

## Seven-step demo

1. **Data foundation:** show linked synthetic structured rows, clinical notes,
   safety/regulatory files, manifests, and data-quality results.
2. **P001 Member 360:** demographics, conditions/meds, A1C trend, ED utilization,
   snapshot, risk contributions and fixed as-of date.
3. **Structured:** "How many diabetes-related ED visits did P001 have in the
   last 90 days?" Show Analyst result, exact count, date window and lineage.
4. **Document:** "What did the latest clinical note say about medication
   adherence?" Show Search output, actual excerpt, date, original page and file.
5. **Mixed:** "Why is P001 high risk, and what evidence supports it?" Show
   fixture-consistent tier, factor sum, structured input and document citations.
   If the fixture is Critical, correct the premise rather than saying High.
6. **Regulatory:** "Which guideline evidence is relevant to A1C and follow-up
   gap?" Show shared guideline passages; distinguish reference from patient fact.
7. **Failure:** "What is P001's confirmed diagnosis of condition X?" Select a
   condition deliberately unsupported by the fixture. Show:
   "I could not find sufficient evidence in the synthetic records."

Run the remaining golden population, safety, and citation-follow-up questions
before handover even if they are not all shown in this short demo.

## Rehearsal checklist

- Freeze source corpus, seed/date, scoring definitions, and all configurations.
- Verify known member and Search smoke query immediately before presenting.
- Test as demo role; verify denied raw access and visible disclaimer.
- Confirm all four screens and citation links/snippets; no hidden reasoning panel.
- Run all eight golden questions plus negative cases; fix and rerun failures.
- Show original page metadata, not a made-up PDF page or stale signed URL.
- Keep actual insufficient-evidence and tool-error cases distinct.
- Show Population Insights: risk by condition, ED utilization, adherence and
  care-gap metrics backed by independent exact-count queries.
- Show all five role checks, member/plan isolation, classification and actual
  audit records; demonstrate changed-input automated refresh.

## Final handover

Export approved agent configuration/version, semantic YAML, Search definition,
structured seed/generator configuration, DQ/evaluation results, sanitized
lifecycle manifest, and approved demo recording. Update
[project status](../.cortex/memory/STATUS.md) and
[handoff](../.cortex/memory/HANDOFF.md) with real evidence paths.
