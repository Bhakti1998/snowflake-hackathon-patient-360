CREATE ROLE IF NOT EXISTS PATIENT_360_ROLE;

GRANT USAGE
ON DATABASE PATIENT_360_RAG
TO ROLE PATIENT_360_ROLE;

GRANT USAGE
ON SCHEMA PATIENT_360_RAG.CURATED
TO ROLE PATIENT_360_ROLE;

GRANT CREATE AGENT
ON SCHEMA PATIENT_360_RAG.CURATED
TO ROLE PATIENT_360_ROLE;

GRANT CREATE AGENT
ON SCHEMA PATIENT_360_RAG.AI
TO ROLE PATIENT_360_ROLE;


GRANT USAGE
ON WAREHOUSE COMPUTE_WH
TO ROLE PATIENT_360_ROLE;

GRANT DATABASE ROLE SNOWFLAKE.CORTEX_AGENT_USER
TO ROLE PATIENT_360_ROLE;


GRANT USAGE
ON CORTEX SEARCH SERVICE PATIENT_360_RAG.AI.RETRIEVE_STRUCTURED_CHUNKS
TO ROLE PATIENT_360_ROLE;

GRANT USAGE
ON CORTEX SEARCH SERVICE PATIENT_360_RAG.AI.RETRIEVE_UNSTRUCTURED_CHUNKS
TO ROLE PATIENT_360_ROLE;


GRANT USAGE
ON CORTEX SEARCH SERVICE PATIENT_360_RAG.AI.RETRIEVE_UNSTRUCTURED_DATA_MULTI_INDEX
TO ROLE PATIENT_360_ROLE;


GRANT USAGE
ON CORTEX SEARCH SERVICE PATIENT_360_RAG.AI.RETRIEVE_STRUCTURED_DATA_MULTI_INDEX
TO ROLE PATIENT_360_ROLE;


show semantic views in database PATIENT_360_RAG;

GRANT SELECT
ON SEMANTIC VIEW PATIENT_360_RAG.AI.PATIENT_360_SEMANTIC_VIEW
TO ROLE PATIENT_360_ROLE;

select current_user();

GRANT ROLE PATIENT_360_ROLE
TO USER <YOUR_USER>;

USE ROLE PATIENT_360_ROLE;


------------ RETRIVAL AGENT -----------------
--This is a latest version of configuration , more changes can be done from Agent AI Studio to fine tune the configuration


create or replace agent PATIENT_360_RAG.AI.PATIENT_360_RETRIVAL_AGENT
comment='Patient 360 document retrieval agent'
profile='{"display_name":"Patient 360 Copilot","avatar":"business-icon.png","color":"blue"}'
from specification
$$
models:
  orchestration: "claude-opus-4-8"
orchestration:
  budget:
    seconds: 300
    tokens: 1100
  capabilities:
    analytical_search: true
instructions:
  response: "You are a healthcare document retrieval assistant.\n\nRetrieve relevant\
    \ information from clinical notes,\ndischarge summaries, safety reports and regulatory\n\
    documents.\n\nAnswer only using information supported by the\nretrieved documents.\n\
    \nIf relevant information cannot be found, clearly state\nthat it was not found.\n"
  orchestration: "You are a Patient 360 assistant serving clinicians, analysts, and\
    \ care coordinators.\n\nUse clear, conversational language. Avoid unnecessary\
    \ medical jargon unless the user's question uses clinical terminology.\n\n###\
    \ Response Guidelines\n\n* Lead with a direct answer, followed by relevant supporting\
    \ details.\n* Always include available patient identifiers: Patient ID, MRN, and\
    \ Encounter ID.\n* Use bullet points for lists of patients, medications, diagnoses,\
    \ or findings.\n* Use tables when comparing multiple data points or presenting\
    \ laboratory results.\n* Do not speculate, infer unsupported information, or provide\
    \ medical advice.\n* Present only information supported by retrieved data. \n\
    * Strictly Do Not create or cite any new information or sources that is not present\
    \ in the data.\n* Always include the correct tool name in reasoning steps, that\
    \ is used for extracting the answer.\n* Return only the final answer and relevant\
    \ supporting evidence.\n* Clearly distinguish structured-data results from information\
    \ retrieved\n  from clinical documents.\n* When a claim comes from structured\
    \ data, identify the source table.\n* When a claim comes from a clinical document,\
    \ cite the document filename\n  or file path and page number when available.\n\
    * Do not use a clinical document citation to support a value that was\n  obtained\
    \ only from structured data.\n* If a retrieved document does not contain enough\
    \ information to verify\n  a claim, explicitly state that the claim could not\
    \ be confirmed from\n  the retrieved document.\n* When multiple documents support\
    \ an answer, cite each relevant document\n  next to the corresponding finding.\n\
    \n### Tool Selection\n\n* Use `ClinicalDocumentSearch` whenever the user asks\
    \ about information contained in clinical documents, including clinical notes,\
    \ admission notes, discharge summaries, safety reports, regulatory documents,\
    \ or other document content.\n* Use `StructuredPatientSearch` for retrieving structured\
    \ patient records such as diagnoses, medications, laboratory results, encounters,\
    \ and claims.\n* Use `PatientAnalytics` for analytical questions requiring calculations,\
    \ aggregations, trends, comparisons, or metrics over structured Patient 360 data.\n\
    * When a question requires both structured and unstructured information, use the\
    \ appropriate tools and combine the results.\n* Do not query `DOCUMENT_CHUNKS`\
    \ directly when `ClinicalDocumentSearch` can answer the question.\n* Do not use\
    \ SQL as a fallback for document-retrieval questions unless `ClinicalDocumentSearch`\
    \ cannot retrieve the requested information.\n\n### Citations and Sources\n\n\
    * Cite the source of information clearly whenever possible.\n* For information\
    \ retrieved using `ClinicalDocumentSearch`, identify the source document using\
    \ the document filename or file path and include the page number when available.\n\
    * For information retrieved from structured search or analytics, identify the\
    \ relevant source table or record when available.\n* Clearly distinguish information\
    \ retrieved from different sources.\n* Do not claim that a document supports an\
    \ answer unless the information was actually retrieved from that document.\n\n\
    ### Missing Information\n\n* If the requested information cannot be found, clearly\
    \ state what was searched and that no matching information was found.\n* Do not\
    \ fabricate documents, records, citations, patient identifiers, or clinical information.\n\
    * When appropriate, suggest a more specific search using available identifiers\
    \ such as Patient ID, MRN, or Encounter ID.\n\n### Patient Identification\n\n\
    When multiple patients or encounters could match the request:\n\n* Use available\
    \ Patient ID, MRN, and Encounter ID to disambiguate.\n* Do not assume that records\
    \ belonging to different patients represent the same patient.\n* Clearly identify\
    \ the patient and encounter associated with each result.\n"
  sample_questions: []
tools:
  - tool_spec:
      type: "cortex_analyst_text_to_sql"
      name: "PatientAnalytics"
      description: "ADVERSE_EVENTS:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Records\
        \ adverse events experienced by patients during clinical encounters, capturing\
        \ drug-related incidents and their outcomes.\n- Links to ENCOUNTERS and PATIENTS\
        \ via ENCOUNTER_ID and PATIENT_ID.\n- LIST OF COLUMNS: ae_id (adverse event\
        \ ID), encounter_id (link to encounter_id in ENCOUNTERS), patient_id (link\
        \ to patient_id in PATIENTS), suspect_drug, event, meddra_pt (MedDRA preferred\
        \ term), severity, serious, outcome, action_taken, evidence, onset_date\n\n\
        CARE_GAPS:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Tracks unmet clinical\
        \ quality measures per patient with status and due dates.\n- LIST OF COLUMNS:\
        \ gap_id, patient_id (link to patient_id in PATIENTS), care_gap, measure,\
        \ status, due_date, evidence, policy_doc\n\nCONDITIONS:\n- Database: PATIENT_360_RAG,\
        \ Schema: RAW\n- Records diagnosed medical conditions per patient with ICD-10\
        \ codes and onset year.\n- LIST OF COLUMNS: patient_id (link to patient_id\
        \ in PATIENTS), condition_key, description, icd10, status, onset_year\n\n\
        DOCUMENT_CHUNKS:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Stores segmented\
        \ text chunks from clinical documents (PDFs, JPEGs) linked to encounters.\n\
        - LIST OF COLUMNS: document_id (link to document_id in DOCUMENT_MANIFEST/PARSED_DOCUMENTS),\
        \ encounter_id (link to encounter_id in ENCOUNTERS), mrn (link to mrn in PATIENTS),\
        \ patient_details, chunk_text, chunk_index, page_number, doc_type, file_path,\
        \ metadata, created_at\n\nDOCUMENT_MANIFEST:\n- Database: PATIENT_360_RAG,\
        \ Schema: RAW\n- Tracks uploaded documents and their ingestion/processing\
        \ pipeline status.\n- LIST OF COLUMNS: document_id, file_name, file_path,\
        \ file_type, document_type, ingestion_status, parsed_content, upload_timestamp,\
        \ processed_timestamp, file_url\n\nENCOUNTERS:\n- Database: PATIENT_360_RAG,\
        \ Schema: RAW\n- Records all clinical interactions including outpatient, inpatient,\
        \ and ED visits with diagnosis and provider info.\n- LIST OF COLUMNS: encounter_id,\
        \ patient_id (link to patient_id in PATIENTS), facility, department, encounter_type,\
        \ attending, reason, primary_icd10, admit_date, discharge_date, los_days,\
        \ days_since_discharge, readmit_30d, prior_encounter_id (link to encounter_id\
        \ self-reference)\n\nIMMUNIZATIONS:\n- Database: PATIENT_360_RAG, Schema:\
        \ RAW\n- Records vaccination events per patient with vaccine type and CVX\
        \ code.\n- LIST OF COLUMNS: patient_id (link to patient_id in PATIENTS), vaccine,\
        \ cvx, date\n\nLAB_RESULTS:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Stores\
        \ laboratory test results tied to encounters with values, units, and flags.\n\
        - LIST OF COLUMNS: lab_id, patient_id (link to patient_id in PATIENTS), encounter_id\
        \ (link to encounter_id in ENCOUNTERS), test, value, unit, reference, flag,\
        \ collected_date\n\nMEDICAL_CLAIMS:\n- Database: PATIENT_360_RAG, Schema:\
        \ RAW\n- Contains medical claim lines with financial and processing details\
        \ per encounter.\n- LIST OF COLUMNS: claim_id, patient_id (link to patient_id\
        \ in PATIENTS), member_id (link to member_id in MEMBERS), encounter_id (link\
        \ to encounter_id in ENCOUNTERS), code, code_type, description, primary_icd10,\
        \ billed_amount, allowed_amount, paid_amount, claim_status, denial_reason,\
        \ service_date, claim_received\n\nMEDICATIONS:\n- Database: PATIENT_360_RAG,\
        \ Schema: RAW\n- Records patient prescriptions with adherence metrics over\
        \ six months.\n- LIST OF COLUMNS: med_id, patient_id (link to patient_id in\
        \ PATIENTS), drug, sig, indication, status, pdc_6mo (proportion of days covered,\
        \ 6-month adherence), start_date\n\nMEMBERS:\n- Database: PATIENT_360_RAG,\
        \ Schema: RAW\n- Tracks health plan membership, coverage periods, and PCP\
        \ attribution.\n- LIST OF COLUMNS: member_id, patient_id (link to patient_id\
        \ in PATIENTS), payer, plan_type, pcp_attributed, coverage_start, coverage_end\n\
        \nMEMBER_360_SEARCH_SOURCE:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Links\
        \ patients to various source tables with search text for retrieval.\n- LIST\
        \ OF COLUMNS: patient_id (link to patient_id in PATIENTS), source_table, source_type,\
        \ search_text\n\nPARSED_DOCUMENTS:\n- Database: PATIENT_360_RAG, Schema: RAW\n\
        - Stores parsed JSON content from clinical documents.\n- LIST OF COLUMNS:\
        \ document_id (link to document_id in DOCUMENT_MANIFEST), file_path, document_type,\
        \ parsed_json\n\nPATIENTS:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Core\
        \ patient demographics including age, sex, DOB, location, and PCP.\n- LIST\
        \ OF COLUMNS: patient_id, mrn (medical record number), name, dob, age, sex,\
        \ city, state, zip3, pcp\n\nPHARMACY_CLAIMS:\n- Database: PATIENT_360_RAG,\
        \ Schema: RAW\n- Records prescription fills with drug, supply days, and paid\
        \ amounts.\n- LIST OF COLUMNS: rx_claim_id, patient_id (link to patient_id\
        \ in PATIENTS), member_id (link to member_id in MEMBERS), drug, days_supply,\
        \ paid_amount, fill_date\n\nRISK_SCORES:\n- Database: PATIENT_360_RAG, Schema:\
        \ RAW\n- Patient composite risk scores with clinical, utilization, and social\
        \ sub-scores.\n- LIST OF COLUMNS: patient_id (link to patient_id in PATIENTS),\
        \ risk_score, risk_tier, clinical_severity, utilization, social_risk, care_gap_burden,\
        \ readmission, open_gaps, inpatient_12mo, ed_12mo, top_drivers, as_of_date\n\
        \nSDOH:\n- Database: PATIENT_360_RAG, Schema: RAW\n- Social determinants of\
        \ health assessments capturing barriers per patient.\n- LIST OF COLUMNS: patient_id\
        \ (link to patient_id in PATIENTS), food_insecurity, lives_alone, low_health_literacy,\
        \ medication_cost_barrier, transportation_barrier, assessed_date\n\nVITALS:\n\
        - Database: PATIENT_360_RAG, Schema: RAW\n- Vital sign measurements per encounter\
        \ including BP, HR, and BMI.\n- LIST OF COLUMNS: encounter_id (link to encounter_id\
        \ in ENCOUNTERS), patient_id (link to patient_id in PATIENTS), sbp, dbp, heart_rate,\
        \ bmi, date\n\nREASONING:\nThis semantic view integrates a comprehensive set\
        \ of clinical, administrative, and social health data tables centered on individual\
        \ patients. The PATIENTS table is the core entity, linked to ENCOUNTERS, CONDITIONS,\
        \ MEDICATIONS, CARE_GAPS, RISK_SCORES, SDOH, IMMUNIZATIONS, MEMBERS, LAB_RESULTS,\
        \ and VITALS via PATIENT_ID. ENCOUNTERS further connect to LAB_RESULTS, VITALS,\
        \ and ADVERSE_EVENTS via ENCOUNTER_ID. MEMBERS bridge to MEDICAL_CLAIMS and\
        \ PHARMACY_CLAIMS via MEMBER_ID. Document tables (DOCUMENT_CHUNKS, DOCUMENT_MANIFEST,\
        \ PARSED_DOCUMENTS) store unstructured clinical notes linked by DOCUMENT_ID\
        \ and ENCOUNTER_ID. MEMBER_360_SEARCH_SOURCE aggregates search text across\
        \ all source tables.\n\nDESCRIPTION:\nThe PATIENT_360_SEMANTIC_VIEW (Database:\
        \ PATIENT_360_RAG, Schema: RAW) provides a comprehensive 360-degree view of\
        \ patient health by integrating clinical, administrative, financial, and social\
        \ data. The PATIENTS table serves as the central entity, connected to ENCOUNTERS\
        \ (visits and admissions), CONDITIONS (diagnoses), MEDICATIONS (prescriptions\
        \ and adherence), LAB_RESULTS (test outcomes), VITALS (clinical measurements),\
        \ IMMUNIZATIONS (vaccines), CARE_GAPS (unmet quality measures), RISK_SCORES\
        \ (composite risk tiers), and SDOH (social barriers) all via PATIENT_ID. MEMBERS\
        \ links to MEDICAL_CLAIMS and PHARMACY_CLAIMS via MEMBER_ID, enabling financial\
        \ and coverage analysis, while ENCOUNTERS further connect to ADVERSE_EVENTS,\
        \ LAB_RESULTS, and VITALS via ENCOUNTER_ID. Unstructured clinical documents\
        \ are captured in DOCUMENT_CHUNKS, DOCUMENT_MANIFEST, and PARSED_DOCUMENTS,\
        \ linked by DOCUMENT_ID and ENCOUNTER_ID, with MEMBER_360_SEARCH_SOURCE aggregating\
        \ searchable text across all source tables. This view supports queries spanning\
        \ patient demographics, clinical outcomes, medication adherence, care quality,\
        \ risk stratification, claims financials, and social determinants of health."
  - tool_spec:
      type: "cortex_search"
      name: "StructuredPatientSearch"
      description: "Search across structured patient data including conditions, medications,\
        \ lab results, encounters, and vital signs. This service indexes the MEMBER_360_SEARCH_SOURCE\
        \ table with multi-index search across PATIENT_ID and SOURCE_TYPE columns.\
        \ Use this tool to find patient clinical records by querying natural language\
        \ descriptions of diagnoses, treatments, lab values, or encounter details.\
        \ Returns PATIENT_ID, SOURCE_TABLE, SOURCE_TYPE, and SEARCH_TEXT columns.\n"
  - tool_spec:
      type: "cortex_search"
      name: "ClinicalDocumentSearch"
      description: "Search across unstructured clinical documents such as discharge\
        \ summaries, clinical notes, and medical reports. This service indexes the\
        \ DOCUMENT_CHUNKS table with multi-index search across PATIENT_DETAILS, MRN,\
        \ and ENCOUNTER_ID and CHUNK_TEXT columns. Use this tool to retrieve relevant\
        \ document chunks by querying natural language descriptions of clinical narratives,\
        \ discharge instructions, diagnoses, or treatment plans. Supports filtering\
        \ by MRN or ENCOUNTER_ID. Returns DOCUMENT_ID, CHUNK_TEXT, CHUNK_INDEX, FILE_PATH,\
        \ PAGE_NUMBER, CREATED_AT, PATIENT_DETAILS, MRN, and ENCOUNTER_ID columns.\n"
skills: []
tool_resources:
  ClinicalDocumentSearch:
    columns_and_descriptions:
      CHUNK_INDEX:
        description: "Sequential number identifying the position of the chunk within\
          \ the source document."
        filterable: false
        searchable: false
        type: "FIXED"
      CHUNK_TEXT:
        description: "Text content extracted from a specific section or chunk of the\
          \ document, used to answer natural-language queries."
        filterable: false
        searchable: true
        type: "TEXT"
      DOCUMENT_ID:
        description: "Unique identifier for the source clinical or healthcare document."
        filterable: false
        searchable: false
        type: "TEXT"
      ENCOUNTER_ID:
        description: "Unique identifier linking the document content to a specific\
          \ patient healthcare encounter."
        filterable: false
        searchable: true
        type: "TEXT"
      MRN:
        description: "A unique identifier assigned by a healthcare organization to\
          \ identify a patient’s medical record and link their clinical information\
          \ across encounters."
        filterable: false
        searchable: true
        type: "TEXT"
      PATIENT_DETAILS:
        description: "This is name of the patient"
        filterable: false
        searchable: true
        type: "TEXT"
    id_column: "DOCUMENT_ID"
    max_results: 5
    relative_path_column: "FILE_PATH"
    search_service: "PATIENT_360_RAG.AI.RETRIEVE_UNSTRUCTURED_DATA_MULTI_INDEX"
    stage_path: "@PATIENT_360_RAG.RAW.DOCUMENT_STAGE"
    target_results: 5
    title_column: "FILE_PATH"
  PatientAnalytics:
    execution_environment:
      type: "warehouse"
      warehouse: "COMPUTE_WH"
    semantic_view: "PATIENT_360_RAG.AI.PATIENT_360_SEMANTIC_VIEW"
  StructuredPatientSearch:
    columns_and_descriptions:
      PATIENT_ID:
        description: "Unique identifier for each patient , no two patients can have\
          \ same patient id"
        filterable: false
        searchable: true
        type: "TEXT"
      SEARCH_TEXT:
        description: "Use this as the searchable natural-language description of the\
          \ structured patient record, allowing the Agent to find relevant information\
          \ based on the user’s query."
        filterable: false
        searchable: true
        type: "TEXT"
      SOURCE_TYPE:
        description: "This identifies the type of structured patient record, such\
          \ as diagnosis, medication, lab result, encounter, or claim, so the Agent\
          \ can understand and filter the retrieved data appropriately."
        filterable: false
        searchable: true
        type: "TEXT"
    id_column: "PATIENT_ID"
    max_results: 5
    search_service: "PATIENT_360_RAG.AI.RETRIEVE_STRUCTURED_DATA_MULTI_INDEX"
    target_results: 5
    title_column: "SOURCE_TABLE"
$$;
