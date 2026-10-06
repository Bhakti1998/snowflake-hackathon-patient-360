# Full MVP scope and implementation sequence

Approved by the user on 2026-10-05: **full MVP scope now**, based on the main PDF.
This is a documentation/skills specification, not a claim of deployed software.

## Source precedence

1. Supplied `CareLens360_Design_Document (1).pdf`, v1.0 dated 2026-09-29, is
   authoritative for full scope, architecture, risk, safety, governance, UI,
   evaluation, and lifecycle evidence.
2. The [repository Markdown design](./CareLens360_Design_Document.md) is the
   readable companion inspected against that PDF.
3. `CareLens360_PoC_Plan_v1.docx` supplies named workstreams and handoffs only.
   Its smaller dataset, two-day timing, omitted screens/roles/controls, and
   document restrictions are superseded.
4. Existing SQL/YAML/upload drafts are prior art, not approved requirements or
   evidence of deployment. Earlier RTF brainstorming is superseded by the PDF's
   corrections to parsing, Search, and semantic views.

The original attachments remain unchanged in the parent workspace's `Docs/`.
This repository carries the operational requirements without depending on that
folder being present in another checkout.

## Mandatory scope from PDF section 18

| Surface | Full MVP commitment |
|---|---|
| Members | 500 synthetic |
| Encounters | 5,000 |
| Claims | 10,000 |
| Lab results | 3,000 |
| Medication events | 1,000 |
| Clinical notes | 500 |
| Safety/regulatory documents | 100 |
| Conditions | Diabetes, hypertension, chronic kidney disease, asthma, heart failure |
| Risk | Six rule factors, four tier bands, evidence-backed contributions |
| UI | Member Search, Member 360, Evidence Copilot, Population Insights |
| Tools | Cortex Analyst + Cortex Search feeding Cortex Agent |
| Documents | Clinical/regulatory evidence with page provenance; PDF/DOCX source handling per architecture |
| Governance | Five roles, four-schema separation, member/plan row filtering, classification, audit logging, pipeline audit records |
| Lifecycle | CoCo Planning, Development, Execution, Testing artifacts |
| Operations | Automated ingestion, validation, incremental processing and demonstrated refresh |
| Answers | Eight golden questions, cited mixed evidence, explicit missing/conflicting information |

No one-year history cap is inherited from the PoC. Freeze history coverage and
as-of date suitable for the required longitudinal/date-window questions.
Analytical Search remains **optional** under PDF section 9. ML scoring and
clinical validation are not implied by "full MVP."

## Workstreams and handoffs

The named ownership is retained from the split document, expanded to full scope.

| Owner | Responsibility | Handoff |
|---|---|---|
| Spurthi | Scope, five-role governance, isolation/classification/audits, golden rubric, demo/lifecycle | Approved namespace/access/policies and acceptance evidence |
| Vinay | Risk engine, semantic view, Analyst, agent, response contract | Versioned score/metric/agent inputs for UI and evaluation |
| Bhakti | Stages/manifests/parsing/chunks, Search, page citations | Authorized retrieval, provenance and refresh outputs |
| Adithya | Full-volume synthetic fixtures, DIM/FACT tables, snapshot, DQ | Stable keys/grains and display sources for scoring/semantics/UI |

Vinay owns scoring; Adithya integrates it rather than maintaining a second
engine. Screen 3 and full Population Insights implementation ownership require
explicit team coordination; this kit does not invent approval for a new owner.
Spurthi coordinates governance definitions; each owner enforces them in their
pipeline, Search/agent, and app surfaces.

## Seven implementation phases from PDF section 17

The PDF's eight-day schedule is a sequencing guide, not evidence of elapsed work.
Parallelize independent work only after its actual prerequisites are satisfied.

| Phase | PDF timing | Deliverables and exit |
|---|---|---|
| 1. Foundation | Days 1-2 | Approved database/schema/role plan, full-volume generator, stages/manifests, zero-orphan fixture validation |
| 2. Curated data | Days 2-3 | DIM/FACT model, snapshot, approved risk factors, DQ and lineage reconciliation for all 500 members |
| 3. Documents | Days 3-4 | Parse results/errors, page-aware token-measured chunks, complete metadata and repeatable ingestion |
| 4. Search and semantics | Days 4-5 | Authorized/fresh Search, governed semantic view, exact metrics and source-page query tests |
| 5. Agent | Days 5-6 | Analyst/Search wiring, strict five-section answers, citations, conflict/missing/tool-error guards |
| 6. Application | Days 6-7 | All four Streamlit screens, population metrics, source display, isolation and role checks |
| 7. Evaluation | Days 7-8 | Eight golden questions, negative/boundary tests, citation metrics, governance and refresh evidence |

Roles, classification and policies begin in Foundation and are validated again
at every consuming surface; they are not optional final-week enhancements.
Capture the four CoCo lifecycle phases across these seven implementation phases.

## PDF coverage map

| PDF sections | Active kit surface |
|---|---|
| 1-3: product, corrections, architecture | [AGENTS](../AGENTS.md), [architecture](./ARCHITECTURE.md) |
| 4: layered model | [architecture](./ARCHITECTURE.md), member-360-builder skill |
| 5: risk | [risk contract](./RISK_MODEL.md), risk-factor-explainer skill |
| 6-7: documents/Search | [architecture](./ARCHITECTURE.md), document-evidence-extractor skill |
| 8-9: semantics/agent | [answer contract](./AGENT_CONTRACT.md), semantic/guardrails skills |
| 10: five-section answers | [answer contract](./AGENT_CONTRACT.md), citation-validator skill |
| 11: four screens | Streamlit skill, [evaluation](./EVALUATION.md) |
| 12: CoCo lifecycle | [demo runbook](./DEMO_RUNBOOK.md), lifecycle skill |
| 13: all governance controls | [governance](./GOVERNANCE.md), governance skill |
| 14: DQ and integrity | [evaluation](./EVALUATION.md), data/document/evaluator skills |
| 15: seven-step demo | [demo runbook](./DEMO_RUNBOOK.md) |
| 16: differentiators | Evidence links, explicit conflicts, dated reasoning and visible skill handoffs |
| 17-18: sequence, volumes, golden set | This file, [evaluation](./EVALUATION.md) |

The seven skill names in PDF section 16 are all present; five supporting skills
cover project memory, semantics/agent, Streamlit, governance, and lifecycle/demo.
Keep evidence-graph links explicit across member, factor, record, document,
page and citation. Demonstrate temporal comparisons with dated sources and
report conflicts; do not expose hidden model reasoning.

## Definition of done

All mandatory scope above and [evaluation gates](./EVALUATION.md) are verified
with actual results and versions, including four-screen behavior, five-role
authorization, member/plan isolation, audit/classification controls and refresh.
Do not label the system production-ready or clinically validated.
Record unresolved definitions and deployment choices in
[DECISIONS.md](../.cortex/memory/DECISIONS.md), without silently shrinking scope.
