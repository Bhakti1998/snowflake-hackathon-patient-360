# Architecture and cross-workstream contracts

## Target flow

```text
Seeded synthetic factory
  -> structured files -> RAW staging/load -> CURATED DIM/FACT tables
      -> MEMBER_RISK_FACTORS + MEMBER_360_SNAPSHOT -> semantic view -> Analyst
  -> documents -> stage + manifest -> AI_PARSE_DOCUMENT -> page-aware chunks
      -> CARE_DOCUMENT_SEARCH -> Search
Analyst + Search -> CARE_LENS_AGENT -> Streamlit Screens 1-4
```

Both tools feed the agent. Documents need not be routed through the semantic
view, and raw document text is not a replacement for governed structured metrics.

## Approved implementation placement

Database: `CARELENS360_MVP`, explicitly approved by the user.
The main PDF prescribes no database name. Do not migrate or overwrite the
legacy `PATIENT_360_RAG` drafts/resources.
`CARELENS360_POC` is a historical split-plan proposal, not the active default.
These placements are implementation conventions; `APP` represents
the PDF's application layer.

| Schema | Objects / responsibility |
|---|---|
| `RAW` | `RAW_DOCUMENT_STAGE`, structured file stage as approved, `RAW_EHR_FILES`, `DOCUMENT_MANIFEST`, `DOCUMENT_PARSE_RESULTS`, structured landing tables |
| `CURATED` | `DIM_MEMBER`, `DIM_PROVIDER`, `DIM_CONDITION`, `DIM_MEDICATION`, `FACT_ENCOUNTER`, `FACT_DIAGNOSIS`, `FACT_MEDICATION`, `FACT_LAB_RESULT`, `FACT_CLAIM`, `DOCUMENT_CHUNKS`, `MEMBER_RISK_FACTORS`, `MEMBER_360_SNAPSHOT` |
| `SEMANTIC` | `PATIENT_MEMBER_360_SEMANTIC_VIEW`, `CARE_DOCUMENT_SEARCH` |
| `APP` | `CARE_LENS_AGENT`, Streamlit application and approved display views |

Fully qualify objects in deployment artifacts. Verify existing objects and
ownership before migrations or replacements.
The [workflow](./WORKFLOW.md) uses internal `RAW.DATA_STAGE`/`APP.CODE_STAGE`,
typed secure DIM/FACT views, live snapshot/risk views, four plan-scoped
Search/semantic/Agent sets and a shared reference service. Original draft
object names in the table are logical prior art, not additional deployed stages.

## Structured contract

- `member_id` is the canonical cross-surface key. Map legacy patient/member
  identifiers explicitly; do not assume similarly named fields share a namespace.
- Each fact has a stable record key, member key, event date, and source lineage.
  Encounters/claims/medications reference applicable dimension keys consistently.
- Snapshot grain: one row per member per fixed as-of date; explicit derived
  refresh/version metadata. Do not multiply counts through one-to-many joins.
- Risk grain: one factor evaluation per member, rule version, and scoring run;
  contributions and evidence satisfy [RISK_MODEL.md](./RISK_MODEL.md).
- Labs preserve units, reference/abnormal flags, dates, and missingness.
- Counts, average A1C, adherence, care gaps, and utilization require documented
  grain, eligibility, time window, null handling, and deduplication.
- Full fixture counts and five-condition coverage follow [MVP_SCOPE](./MVP_SCOPE.md).
  Preserve member/plan keys and classification metadata for policy evaluation.

## Document contract

Manifest tracks document ID, relative stage path, type, member association if
applicable, document date, source system, author role, condition, medication,
status, attempt/run metadata, and actionable errors.

`DOCUMENT_PARSE_RESULTS` preserves original parse output and error details.
Use `TO_FILE` and supported `LAYOUT`/`OCR` options; inspect output shape before
flattening pages. Verify whether provider page indexes are zero-based; the UI
contract is a positive, one-based original page number. No invented page numbers.

Include PDF/DOCX sources from the PDF architecture; do not inherit the PoC's
DOCX exclusion. Check actual supported formats before parsing. If DOCX requires
conversion, use an approved reproducible local/Snowflake workflow, retain source
and converted artifact identities, and cite the explicitly rendered page version.
Never invent an intrinsic original DOCX page number or pass unsupported formats
as if parsing succeeded. Log unsupported-format blockers explicitly.

Each chunk has:

| Field | Requirement |
|---|---|
| `chunk_id` | Stable identifier; deduplication and retrieval tracing |
| `document_id` | Links to manifest and parse result |
| `member_id` | Valid member for member-specific notes; nullable for shared evidence |
| `chunk_text` | Text from one original page, with supporting source span |
| `page_number` | Original one-based page, not chunk sequence |
| `section` | Source section where known; explicitly unknown if absent |
| `source_file` | Durable relative stage path; no persisted signed URL |
| Metadata | Document type/date, source system, author role, condition group, medication name |

Chunk target: **500-900 tokens, 50-100 token overlap** within a page. Short pages
and final residual chunks may be shorter and must be identified. Measure token
counts with an explicit tokenizer; the legacy character splitter is not proof
of token compliance. Preserve page boundaries even when a page is short.

Searchable field: `CHUNK_TEXT`. Filter attributes:
`MEMBER_ID`, `DOCUMENT_TYPE`, `DOCUMENT_DATE`, `SOURCE_SYSTEM`, `AUTHOR_ROLE`,
`CONDITION_GROUP`, `MEDICATION_NAME`. Return all citation metadata plus chunk ID.
In the implementation, condition and medication attributes are string arrays,
queried with `@contains`; member/other scalar attributes use `@eq`.

Member-note searches must use the selected member filter. Query shared guidelines
separately with relevant condition/medication filters; never broaden a failed
member query into other members' notes. Search filters are not authorization.

## Semantic / agent contract

Entities: members, conditions, encounters, diagnoses, medications, labs, claims,
risk factors, care gaps. Metrics: member/encounter/ED counts, total claim amount,
average A1C, abnormal labs, adherence, care gaps, high-risk members.
Synonyms: member/patient/enrollee/beneficiary; emergency/ED/ER visit;
adherence/compliance/refill adherence.

Validate uniqueness/cardinality before authoring relationships. Use Analyst for
exact structured results and population questions, Search for document evidence.
Wire the approved [guardrails and response contract](./AGENT_CONTRACT.md).

## Evidence, temporal and operational contracts

Retain explicit links Member -> Risk Factor -> Structured Record -> Document ->
Page -> Citation so explanations can be independently traced. Date observations,
state lookback intervals, and test temporal comparisons such as "What changed
in the last 30 days?" against frozen history. Report conflicting evidence with
both dates/sources. Analytical Search is optional, not a replacement for Analyst.

Implement automated ingestion/validation and an approved refresh mechanism:
stable file/version identities, run status/errors, idempotent replay, incremental
processing, snapshot/risk refresh, Search freshness and audit records. Choose
schedules/tasks only after approval; demonstrate an actual changed-input refresh.
Apply [governance](./GOVERNANCE.md) to tables, views, Search, agent and UI.

## Existing draft mapping

| Existing artifact/object | MVP target | Reuse caution |
|---|---|---|
| [DATA PARSING SCRIPT.sql](../scripts/legacy/DATA%20PARSING%20SCRIPT.sql): `PATIENT_360_RAG` | Approved MVP database | PDF prescribes no DB name; no live renaming without approval |
| `RAW.DOCUMENT_STAGE` | `RAW.RAW_DOCUMENT_STAGE` | Verify uploaded files, grants, and directory metadata |
| `RAW.PARSED_DOCUMENTS` | `RAW.DOCUMENT_PARSE_RESULTS` | Preserve errors/status, verify actual page output |
| `RAW.DOCUMENT_CHUNKS` | `CURATED.DOCUMENT_CHUNKS` | Reconcile member key, page flattening, token sizing, provenance |
| `AI.RETRIEVE_UNSTRUCTURED_CHUNKS` / multi-index variant | `SEMANTIC.CARE_DOCUMENT_SEARCH` | Verify complete filter attributes and returned citations |
| `AI.RETRIEVE_STRUCTURED_CHUNKS` | Governed semantic view + Analyst | Retrieval cannot replace exact structured computation |
| [semantic_view.yaml](../scripts/legacy/semantic_view.yaml): `PATIENT_360_SEMANTIC_VIEW` on RAW tables | `PATIENT_MEMBER_360_SEMANTIC_VIEW` on curated facts | Revalidate keys, relationships, grain, and metrics |
| [CREATE RETRIVAL AGENT.sql](../scripts/legacy/CREATE%20RETRIVAL%20AGENT.sql): `AI.PATIENT_360_RETRIVAL_AGENT` | `APP.CARE_LENS_AGENT` | Reconcile tools, permissions, output template, and fallbacks |
| [SNOWFLAKE_INGESTION.sql](../scripts/legacy/SNOWFLAKE_INGESTION.sql) | Approved raw DDL | Contains placeholders; not directly runnable |
| [upload_dataset_flies.ps1](../scripts/legacy/upload_dataset_flies.ps1) | Approved upload workflow | PowerShell/path assumptions; verify target and overwrite behavior |

These are inspection findings, not completed migrations. Treat scripts as
non-runnable until reviewed for incomplete statements and replacement effects.
