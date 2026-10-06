# CareLens 360: Evidence-First Patient and Member Copilot
## Snowflake Hackathon Design Document

---

## Executive Summary

Build a **governed Patient and Member 360 Copilot** that combines structured patient/member data from EHR, claims, medications, encounters, labs, providers, and care plans with unstructured clinical and regulatory documents such as progress notes, discharge summaries, safety reports, treatment guidelines, and payer policies.

The product should not position itself as a diagnostic system. It should be a **traceable evidence and decision-support copilot** that explicitly distinguishes between facts found in structured data, evidence found in documents, calculated risk indicators, missing or conflicting information, and unsupported conclusions.

---

## 1. Product Concept

### Product Name
**CareLens 360 — Evidence-First Patient and Member Copilot**

### Primary User
A care manager, clinical reviewer, utilization management nurse, pharmacovigilance analyst, or regulatory affairs specialist.

### Core User Questions

#### Patient-specific
- "Give me a longitudinal summary of member P001."
- "Why is P001 classified as high risk?"
- "Which evidence supports the risk classification?"

#### Evidence and regulatory
- "Which guideline evidence is relevant to this member's A1C level?"
- "What safety reports mention Drug A?"
- "Which source documents support this answer?"

#### Population-level
- "Which members have high-risk diabetes and no recent follow-up?"
- "What safety themes appear across all adverse-event reports?"

---

## 2. Validation of Existing Design

### ✅ Correct: Synthetic Data First
Generate a **referentially consistent healthcare ecosystem** with realistic relationships across patients, providers, encounters, diagnoses, medications, labs, claims, and documents.

### ✅ Correct: Structured and Unstructured Data Combined
A patient-level answer should combine laboratory data, claims, encounters, medication data, clinical notes, and guideline evidence.

### 🔴 Important Correction: AI_PARSE_DOCUMENT Syntax
Use `TO_FILE` with file objects, not raw stage paths:

```sql
SELECT
    relative_path,
    AI_PARSE_DOCUMENT(
        TO_FILE('@RAW_DOCUMENT_STAGE', relative_path),
        OBJECT_CONSTRUCT(
            'mode', 'LAYOUT',
            'page_split', TRUE
        ),
        TRUE
    ) AS parsed_result
FROM DOCUMENT_MANIFEST
WHERE processing_status = 'PENDING';
```

### 🔴 Important Correction: Use Cortex Search Instead of Custom Vector DB
Prefer: **Parsed document pages/chunks → Cortex Search Service → Cortex Agent**

Cortex Search is more naturally integrated with Cortex Agents and provides source-path metadata for citations.

### 🔴 Important Correction: Semantic Views are Governed Business Layers
Use semantic views to define business entities, relationships, dimensions, metrics, and synonyms—not ordinary views layered on top of semantic views.

---

## 3. Target Architecture

```
Synthetic Data Factory
        ↓
    ┌───┴───┐
    ↓       ↓
Structured  Documents
Files       PDF/DOCX
    ↓       ↓
Stages → Manifests
    ↓       ↓
Ingestion   AI_PARSE_DOCUMENT
    ↓       ↓
Curated   Document_Chunks
Tables  →  Cortex_Search
    ↓           ↓
Member_360  ← ┘
    ↓
Semantic_View
    ↓
Cortex_Agent
    ↓
Streamlit_App
```

---

## 4. Data Model (Layered)

### Raw Layer
- `RAW_EHR_FILES`: File manifests with status tracking
- `DOCUMENT_MANIFEST`: Document registry with parse modes
- `DOCUMENT_PARSE_RESULTS`: Parse results and error tracking

### Curated Layer
- `DIM_MEMBER`, `DIM_PROVIDER`, `DIM_CONDITION`, `DIM_MEDICATION`
- `FACT_ENCOUNTER`, `FACT_DIAGNOSIS`, `FACT_MEDICATION`, `FACT_LAB_RESULT`, `FACT_CLAIM`

### Derived Layer
- `MEMBER_360_SNAPSHOT`: Denormalized patient view
- `MEMBER_RISK_FACTORS`: Transparent risk components
- `DOCUMENT_CHUNKS`: Page-aware chunks with provenance

---

## 5. Risk Stratification (Transparent, Not Opaque)

Use an interpretable rule-based model:

```
30 points: uncontrolled lab value
20 points: recent ED utilization
15 points: medication adherence concern
15 points: multiple chronic conditions
10 points: care-gap detected
10 points: recent adverse event

0–24   Low
25–49  Moderate
50–74  High
75+    Critical
```

Store every point contribution in `MEMBER_RISK_FACTORS` so the agent can answer:
> "Why is P001 high risk?" with full transparency.

---

## 6. Document Processing Pipeline

1. Generate/upload file to stage
2. Register in `DOCUMENT_MANIFEST`
3. Parse with `AI_PARSE_DOCUMENT` (LAYOUT or OCR mode)
4. Split into pages
5. Create chunks (500–900 tokens, 50–100 token overlap)
6. Preserve metadata and source paths
7. Index with Cortex Search

Each chunk retains:
```json
{
  "document_id": "DOC-000123",
  "member_id": "P001",
  "document_type": "Clinical Note",
  "document_date": "2026-08-14",
  "page_number": 2,
  "section": "Assessment and Plan",
  "source_file": "clinical_notes/P001/visit_2026_08_14.pdf"
}
```

---

## 7. Cortex Search Configuration

**Service Name:** `CARE_DOCUMENT_SEARCH`

**Searchable:** `CHUNK_TEXT`

**Filterable Attributes:**
- `MEMBER_ID`
- `DOCUMENT_TYPE`
- `DOCUMENT_DATE`
- `SOURCE_SYSTEM`
- `AUTHOR_ROLE`
- `CONDITION_GROUP`
- `MEDICATION_NAME`

---

## 8. Semantic View Design

**View Name:** `PATIENT_MEMBER_360_SEMANTIC_VIEW`

**Entities:** Members, Conditions, Encounters, Diagnoses, Medications, Labs, Claims, Risk Factors, Care Gaps

**Key Metrics:**
- Member count
- Encounter count
- Emergency visit count
- Total claim amount
- Average A1C
- Abnormal lab count
- Medication adherence rate
- Care gap count
- High-risk member count

**Synonyms:**
- member = patient, enrollee, beneficiary
- emergency visit = ED visit, ER visit
- medication adherence = compliance, refill adherence

---

## 9. Cortex Agent Configuration

**Agent Name:** `CARE_LENS_AGENT`

**Tools:**
1. **Cortex Analyst**: Query `PATIENT_MEMBER_360_SEMANTIC_VIEW`
2. **Cortex Search**: Retrieve from `CARE_DOCUMENT_SEARCH`
3. **Optional Analytical Search**: Corpus-wide counts, trends, themes

**Instructions (Guardrails):**
- Use Cortex Analyst for structured facts
- Use Cortex Search for document evidence
- Never invent data
- Every factual statement must be cited
- Distinguish facts from calculated indicators
- Report conflicting evidence explicitly
- State when evidence is missing
- Do not diagnose or recommend treatment

---

## 10. Answer Format (Strict Template)

### Summary
Member P001 is currently classified as **High Risk**.

### Key Evidence
| Evidence | Value | Source |
|---|---:|---|
| Most recent A1C | 8.2% | Lab result, 2026-08-14 |
| ED visits, last 90 days | 2 | Claims and encounters |

### Risk Drivers
- Uncontrolled A1C: +30 points
- Recent emergency utilization: +20 points
- Documented adherence concern: +15 points
- Specialty follow-up gap: +10 points

### Evidence Citations
- `Clinical Note — 2026-08-14 — page 2`
- `Lab Result — A1C — 2026-08-14`
- `Encounter Record — ED — 2026-07-02`

### Limitations
This is synthetic data. The risk score is a demonstration rule, not a validated clinical model.

---

## 11. Streamlit Application (4 Screens)

### Screen 1: Member Search
- Search by member ID
- Filter by risk tier, condition, plan
- Show member count and risk distribution

### Screen 2: Member 360
- Demographics
- Active conditions & medications
- Recent encounters & labs
- Claims utilization
- Care gaps & risk score breakdown

### Screen 3: Evidence Copilot
- Natural-language question box
- Answer with evidence snippets
- Page-level citations
- "Show reasoning inputs" panel
- Warning banners for insufficient/conflicting evidence

### Screen 4: Population Insights
- High-risk member count
- Risk distribution by condition
- ED utilization patterns
- Medication adherence metrics
- Care-gap distribution

---

## 12. CoCo Lifecycle Evidence (Required for Judging)

### Phase 1: Planning
- Explore structured and document data
- Draft domain ontology
- Propose table relationships
- Design semantic view
- Define risk factors
- Identify security controls

### Phase 2: Development
- Generate synthetic data
- Create ingestion pipelines
- Parse documents
- Create chunks
- Configure Cortex Search
- Define semantic views
- Configure Cortex Agent
- Build Streamlit app

### Phase 3: Execution
- Execute ingestion
- Parse documents
- Run incremental processing
- Refresh tables
- Invoke agent
- Run population analysis
- Launch Streamlit app
- Demonstrate automated refresh

### Phase 4: Testing & Validation
- Build golden question set
- Test happy paths
- Test missing data scenarios
- Test conflicting data
- Test unknown member IDs
- Test unsupported questions
- Measure citation quality

---

## 13. Security & Governance

**Roles:**
- `CARE_ADMIN`: Full access
- `CARE_DATA_ENGINEER`: Pipeline access
- `CARE_ANALYST`: Curated views access
- `CARE_REVIEWER`: Member 360 access
- `CARE_DEMO_USER`: Streamlit only

**Controls:**
- Separate schemas: raw, curated, semantic, application
- Role-based access
- Row-level filtering by member/plan
- Data classification columns
- Audit logging
- Pipeline audit records
- Synthetic data disclaimer

---

## 14. Data Quality Checks

**Referential Integrity:**
- Every encounter → valid member
- Every claim → valid member
- Every document → existing member (if member-specific)

**Clinical Plausibility:**
- A1C values reasonable
- Medication start < end dates
- Encounter dates not in future
- Patient ages plausible

**Pipeline Integrity:**
- Every staged file in manifest
- Every processed file has parse result
- Failed files logged with error details
- No duplicate processing

**Agent Integrity:**
- Structured questions use Cortex Analyst
- Document questions use Cortex Search
- Mixed questions use both
- Unsupported questions get safe fallback

---

## 15. Demo Storyline (Critical for Success)

### Step 1: Show Data Foundation
- Structured records
- Clinical documents
- Safety reports
- Regulatory documents

### Step 2: Open Member P001
- Demographics, diagnoses, medications
- A1C trend, ED utilization
- Risk tier, care gaps

### Step 3: Structured Question
Q: "How many diabetes-related ED visits did P001 have in the last 90 days?"
- Show exact count and underlying facts

### Step 4: Document Question
Q: "What did the latest clinical note say about medication adherence?"
- Show document snippet, date, page, source path

### Step 5: Mixed Question
Q: "Why is P001 high risk, and what evidence supports it?"
- Show structured data, claims, encounters
- Show document evidence
- List risk factors with points and citations

### Step 6: Regulatory Question
Q: "Which guideline evidence is relevant to A1C and follow-up gap?"
- Show guideline excerpts with citations
- Distinguish guideline evidence from patient facts

### Step 7: Failure Case
Q: "What is P001's confirmed diagnosis of condition X?"
Answer: "I could not find sufficient evidence in the synthetic records."

---

## 16. What Makes the Solution Stand Out

1. **Evidence Graph**: Explicit relationship from Member → Risk Factor → Structured Record → Document → Page → Citation

2. **Conflict Detection**: If structured data and documents disagree, report both sources

3. **Time-Aware Reasoning**: Support "What changed in the last 30 days?" and temporal comparisons

4. **Reusable CoCo Skills**:
   - `synthetic-healthcare-data-generator`
   - `document-evidence-extractor`
   - `member-360-builder`
   - `clinical-question-evaluator`
   - `citation-validator`
   - `risk-factor-explainer`
   - `healthcare-agent-guardrails`

5. **Multi-Skill Orchestration**: Visible handoffs between specialized components

---

## 17. Implementation Sequence

### Phase 1 — Foundation (Days 1-2)
- Database and schemas
- Synthetic data generation
- Stages and manifests
- Referential integrity validation

### Phase 2 — Curated Data (Days 2-3)
- Dimensions and fact tables
- Member 360 snapshot
- Risk factor tables
- Data quality checks

### Phase 3 — Document Processing (Days 3-4)
- Parse documents
- Create chunks
- Preserve metadata

### Phase 4 — Search & Semantics (Days 4-5)
- Cortex Search creation
- Semantic view definition
- Query testing

### Phase 5 — Agent (Days 5-6)
- Cortex Agent configuration
- Tool attachment
- Guardrails and fallback

### Phase 6 — Application (Days 6-7)
- Streamlit interface
- All four screens
- Citation display

### Phase 7 — Evaluation (Days 7-8)
- Golden question set
- Happy path testing
- Edge case testing
- CoCo evidence capture

---

## 18. Recommended MVP Scope

**Data Volume:**
- 500 synthetic members
- 5,000 encounters
- 10,000 claims
- 3,000 lab results
- 1,000 medication events
- 500 clinical notes
- 100 safety and regulatory documents

**Conditions:**
- Diabetes
- Hypertension
- Chronic kidney disease
- Asthma
- Heart failure

**Core Capabilities:**
- Member 360 dashboard
- Explainable risk score
- Clinical note retrieval
- Regulatory evidence retrieval
- Mixed structured/unstructured Q&A
- Page-level citations
- Missing-evidence fallback
- CoCo lifecycle demonstration
- Streamlit application
- Automated ingestion and validation

**Questions to Guarantee:**
1. "Summarize member P001."
2. "Why is P001 high risk?"
3. "What are P001's recent abnormal labs?"
4. "What did the latest note say about medication adherence?"
5. "Which guideline evidence is relevant?"
6. "How many high-risk members have a follow-up gap?"
7. "What safety reports mention Drug A?"
8. "What evidence supports this answer?"

---

## Conclusion

The winning architecture integrates:

```
Synthetic referentially consistent data
  ↓
Governed Snowflake ingestion
  ↓
AI_PARSE_DOCUMENT with page-aware output
  ↓
Document chunks with complete provenance
  ↓
Cortex Search
  ↓
Curated Patient/Member 360 tables
  ↓
Semantic view
  ↓
Cortex Analyst
  ↓
Cortex Agent with strict evidence guardrails
  ↓
Streamlit evidence-first application
  ↓
CoCo-driven planning, development, execution, and testing
```

**Key Success Factors:**
1. Use `TO_FILE` and structured error handling
2. Prefer Cortex Search over custom embeddings
3. Make risk scoring transparent and factor-based
4. Make every answer citation-aware and source-traceable
5. Demonstrate CoCo in every lifecycle phase
6. Include failure scenarios in the demo
7. Prioritize evidence and guardrails over chatbot fluency

---

**Document Version:** 1.0  
**Date:** 2026-09-29  
**Accessibility:** Private Repository (vinay-r1_dentsu only)  
**Next Steps:** Convert to PDF and download from repository
