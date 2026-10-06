"""SQL builders for isolated project resources, not the legacy draft objects."""

import re
from typing import Dict, List

ENTITIES = ["patients", "members", "providers", "conditions", "encounters", "lab_results",
            "medications", "pharmacy_claims", "medical_claims", "adverse_events", "care_gaps",
            "document_manifest", "expected_factors"]


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,254}", value):
        raise ValueError(f"Invalid Snowflake identifier: {value!r}")
    return value.upper()


def literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def foundation(database: str) -> List[str]:
    db = identifier(database)
    statements = [f"CREATE DATABASE IF NOT EXISTS {db} COMMENT='CareLens360 managed synthetic MVP'"]
    statements += [f"CREATE SCHEMA IF NOT EXISTS {db}.{schema}" for schema in ["RAW", "CURATED", "SEMANTIC", "APP"]]
    statements += [
        f"CREATE STAGE IF NOT EXISTS {db}.RAW.DATA_STAGE DIRECTORY=(ENABLE=TRUE) ENCRYPTION=(TYPE='SNOWFLAKE_SSE')",
        f"CREATE STAGE IF NOT EXISTS {db}.APP.CODE_STAGE ENCRYPTION=(TYPE='SNOWFLAKE_SSE')",
        f"CREATE FILE FORMAT IF NOT EXISTS {db}.RAW.JSON_FORMAT TYPE=JSON",
        f"""CREATE TABLE IF NOT EXISTS {db}.RAW.WORKFLOW_CONFIG (ID STRING, DATA VARIANT)""",
        f"""CREATE TABLE IF NOT EXISTS {db}.APP.USER_ENTITLEMENTS (
          USER_NAME STRING, PLAN_ID STRING, CLASSIFICATION STRING DEFAULT 'SYNTHETIC')""",
        f"""CREATE TABLE IF NOT EXISTS {db}.RAW.PIPELINE_AUDIT (
          RUN_ID STRING, OPERATION STRING, STATUS STRING, DETAILS STRING,
          STARTED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(), FINISHED_AT TIMESTAMP_LTZ)""",
        f"""CREATE TABLE IF NOT EXISTS {db}.APP.ACCESS_AUDIT (
          REQUEST_ID STRING, USER_NAME STRING, PLAN_ID STRING, OPERATION STRING,
          STATUS STRING, CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""",
        f"""CREATE TABLE IF NOT EXISTS {db}.RAW.DOCUMENT_PARSE_RESULTS (
          DOCUMENT_ID STRING, SHA256 STRING, PARSED_RESULT VARIANT, ERROR STRING,
          RUN_ID STRING, PROCESSED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""",
        f"""CREATE TABLE IF NOT EXISTS {db}.CURATED.DOCUMENT_CHUNKS (
          CHUNK_ID STRING, DOCUMENT_ID STRING, MEMBER_ID STRING, PATIENT_ID STRING,
          PLAN_ID STRING, DOCUMENT_TYPE STRING, DOCUMENT_DATE DATE, SOURCE_SYSTEM STRING,
          AUTHOR_ROLE STRING, CONDITION_GROUP ARRAY, MEDICATION_NAME ARRAY,
          PAGE_NUMBER NUMBER, SECTION STRING, SOURCE_FILE STRING, CHUNK_TEXT STRING,
          START_OFFSET NUMBER, END_OFFSET NUMBER,
          TOKEN_COUNT NUMBER, OVERLAP_TOKENS NUMBER, CHUNK_EXCEPTION STRING,
          TOKENIZER STRING, SHA256 STRING, CLASSIFICATION STRING,
          CREATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())
          CHANGE_TRACKING=TRUE""",
    ]
    for name in ENTITIES:
        tracking = " CHANGE_TRACKING=TRUE" if name == "document_manifest" else ""
        statements.append(f"""CREATE TABLE IF NOT EXISTS {db}.RAW.{name.upper()} (
          ID STRING, DATA VARIANT, SOURCE_FILE STRING,
          UPDATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()){tracking}""")
    return statements


def load_sql(database: str, entity: str) -> List[str]:
    db = identifier(database)
    if entity not in ENTITIES:
        raise ValueError("Unknown entity")
    table = entity.upper()
    return [
        f"CREATE OR REPLACE TEMP TABLE {db}.RAW.LOAD_{table} (\"ROW\" VARIANT)",
        f"""COPY INTO {db}.RAW.LOAD_{table} FROM @{db}.RAW.DATA_STAGE/{entity}.jsonl
          FILE_FORMAT=(FORMAT_NAME={db}.RAW.JSON_FORMAT) FORCE=TRUE ON_ERROR=ABORT_STATEMENT""",
        f"""MERGE INTO {db}.RAW.{table} t USING (
          SELECT \"ROW\":id::STRING ID, \"ROW\":data DATA FROM {db}.RAW.LOAD_{table}
        ) s ON t.ID=s.ID
        WHEN MATCHED AND t.DATA != s.DATA THEN UPDATE SET DATA=s.DATA,
          SOURCE_FILE={literal(entity+'.jsonl')}, UPDATED_AT=CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (ID,DATA,SOURCE_FILE)
          VALUES(s.ID,s.DATA,{literal(entity+'.jsonl')})""",
    ]


def curated(database: str, config: Dict) -> List[str]:
    db = identifier(database)
    out = []
    definitions = {
        "DIM_MEMBER": """SELECT p.ID PATIENT_ID, p.DATA:member_id::STRING MEMBER_ID,
          p.DATA:name::STRING NAME, p.DATA:age::NUMBER AGE, p.DATA:mrn::STRING MRN,
          p.DATA:provider_id::STRING PROVIDER_ID, m.DATA:plan_id::STRING PLAN_ID,
          m.DATA:plan_type::STRING PLAN_TYPE, 'SYNTHETIC' CLASSIFICATION
          FROM {db}.RAW.PATIENTS p JOIN {db}.RAW.MEMBERS m ON m.DATA:patient_id::STRING=p.ID""",
        "DIM_PROVIDER": "SELECT ID PROVIDER_ID, DATA:name::STRING NAME FROM {db}.RAW.PROVIDERS",
        "DIM_CONDITION": """SELECT DISTINCT DATA:condition_key::STRING CONDITION_KEY,
          DATA:icd10::STRING ICD10, DATA:description::STRING DESCRIPTION FROM {db}.RAW.CONDITIONS""",
        "DIM_MEDICATION": "SELECT DISTINCT DATA:drug::STRING DRUG FROM {db}.RAW.MEDICATIONS",
        "FACT_DIAGNOSIS": """SELECT ID DIAGNOSIS_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:condition_key::STRING CONDITION_KEY, DATA:icd10::STRING ICD10,
          DATA:description::STRING DESCRIPTION, DATA:status::STRING STATUS FROM {db}.RAW.CONDITIONS""",
        "FACT_ENCOUNTER": """SELECT ID ENCOUNTER_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:provider_id::STRING PROVIDER_ID, DATA:encounter_type::STRING ENCOUNTER_TYPE,
          DATA:admit_date::DATE EVENT_DATE, DATA:primary_icd10::STRING PRIMARY_ICD10
          FROM {db}.RAW.ENCOUNTERS""",
        "FACT_LAB_RESULT": """SELECT ID LAB_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:encounter_id::STRING ENCOUNTER_ID, DATA:collected_date::DATE EVENT_DATE,
          DATA:test::STRING TEST, DATA:value::FLOAT VALUE, DATA:unit::STRING UNIT,
          DATA:flag::STRING FLAG FROM {db}.RAW.LAB_RESULTS""",
        "FACT_MEDICATION": """SELECT ID MED_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:drug::STRING DRUG, DATA:start_date::DATE START_DATE,
          DATA:status::STRING STATUS, DATA:is_prn::BOOLEAN IS_PRN,
          IFF(DATA:is_prn::BOOLEAN,NULL,(
            SELECT COUNT(DISTINCT c.DAY)::FLOAT/183 FROM (
              SELECT DATEADD(day,ROW_NUMBER() OVER(ORDER BY SEQ4())-1,
                DATEADD(day,-182,'{asof}'::DATE)) DAY FROM TABLE(GENERATOR(ROWCOUNT=>183))
            ) c JOIN {db}.RAW.PHARMACY_CLAIMS rx
              ON c.DAY BETWEEN rx.DATA:fill_date::DATE AND
                DATEADD(day,rx.DATA:days_supply::NUMBER-1,rx.DATA:fill_date::DATE)
            WHERE rx.DATA:med_id::STRING=m.ID)) PDC
          FROM {db}.RAW.MEDICATIONS m""",
        "FACT_CLAIM": """SELECT ID CLAIM_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:encounter_id::STRING ENCOUNTER_ID, DATA:service_date::DATE EVENT_DATE,
          DATA:billed_amount::FLOAT BILLED_AMOUNT FROM {db}.RAW.MEDICAL_CLAIMS""",
        "CARE_GAPS": """SELECT ID GAP_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:measure::STRING MEASURE, DATA:status::STRING STATUS,
          DATA:due_date::DATE DUE_DATE FROM {db}.RAW.CARE_GAPS""",
        "ADVERSE_EVENTS": """SELECT ID AE_ID, DATA:member_id::STRING MEMBER_ID,
          DATA:onset_date::DATE EVENT_DATE, DATA:suspect_drug::STRING SUSPECT_DRUG
          FROM {db}.RAW.ADVERSE_EVENTS""",
    }
    for name, query in definitions.items():
        out.append(f"CREATE OR REPLACE SECURE VIEW {db}.CURATED.{name} AS " +
                   query.format(db=db, asof=config["as_of_date"]))
    asof = literal(config["as_of_date"])
    lab_days = int(config["lab_window_days"]) - 1
    ed_days = int(config["ed_window_days"]) - 1
    ae_days = int(config["adverse_event_window_days"]) - 1
    explanations = {
        "uncontrolled_lab": f"Latest observation per test within {lab_days+1} days has source HIGH/LOW/ABNORMAL flag",
        "recent_ed": f"At least one distinct ED encounter within {ed_days+1} days",
        "adherence_concern": f"Active non-PRN medication covered-days PDC below {config['adherence_threshold']} over {config['adherence_window_days']} days",
        "multiple_chronic_conditions": f"At least {config['chronic_condition_minimum']} distinct active chronic condition keys",
        "care_gap": "Unresolved OPEN/MISSED TRC follow-up gap due on or before the frozen as-of date",
        "recent_adverse_event": f"Recorded adverse event within {ae_days+1} days; association does not establish causation",
    }
    explanation_sql = "CASE f.FACTOR_ID " + " ".join(
        f"WHEN {literal(key)} THEN {literal(text)}" for key, text in explanations.items()) + " END"
    out.append(f"""CREATE OR REPLACE SECURE VIEW {db}.CURATED.MEMBER_RISK_FACTORS AS
      WITH latest AS (
        SELECT * FROM {db}.CURATED.FACT_LAB_RESULT
        WHERE EVENT_DATE BETWEEN DATEADD(day,-{lab_days},{asof}::DATE) AND {asof}::DATE
        QUALIFY ROW_NUMBER() OVER(PARTITION BY MEMBER_ID,TEST ORDER BY EVENT_DATE DESC,LAB_ID DESC)=1
      ), observations AS (
        SELECT m.MEMBER_ID,m.PATIENT_ID,m.PLAN_ID,
          (SELECT COUNT(*) FROM latest l WHERE l.MEMBER_ID=m.MEMBER_ID) LAB_COUNT,
          (SELECT COUNT(*) FROM latest l WHERE l.MEMBER_ID=m.MEMBER_ID AND FLAG IN ('HIGH','LOW','ABNORMAL')) ABNORMAL,
          (SELECT COUNT(*) FROM {db}.CURATED.FACT_ENCOUNTER e WHERE e.MEMBER_ID=m.MEMBER_ID
            AND ENCOUNTER_TYPE='ED' AND EVENT_DATE BETWEEN DATEADD(day,-{ed_days},{asof}::DATE) AND {asof}::DATE) ED,
          (SELECT COUNT(*) FROM {db}.CURATED.FACT_MEDICATION x WHERE x.MEMBER_ID=m.MEMBER_ID AND STATUS='active' AND NOT IS_PRN) MED_COUNT,
          (SELECT COUNT(*) FROM {db}.CURATED.FACT_MEDICATION x WHERE x.MEMBER_ID=m.MEMBER_ID AND STATUS='active' AND NOT IS_PRN AND PDC IS NULL) MED_UNKNOWN,
          (SELECT COUNT(*) FROM {db}.CURATED.FACT_MEDICATION x WHERE x.MEMBER_ID=m.MEMBER_ID AND STATUS='active' AND NOT IS_PRN AND PDC<{float(config['adherence_threshold'])}) LOW_PDC,
          (SELECT COUNT(DISTINCT CONDITION_KEY) FROM {db}.CURATED.FACT_DIAGNOSIS x WHERE x.MEMBER_ID=m.MEMBER_ID AND STATUS='active') CHRONIC_COUNT,
          (SELECT COUNT(*) FROM {db}.CURATED.CARE_GAPS x WHERE x.MEMBER_ID=m.MEMBER_ID AND MEASURE='TRC'
            AND STATUS IN ('OPEN','MISSED') AND DUE_DATE<={asof}::DATE) FOLLOW_UP_GAPS,
          (SELECT COUNT(*) FROM {db}.CURATED.ADVERSE_EVENTS x WHERE x.MEMBER_ID=m.MEMBER_ID
            AND EVENT_DATE BETWEEN DATEADD(day,-{ae_days},{asof}::DATE) AND {asof}::DATE) AE_COUNT
        FROM {db}.CURATED.DIM_MEMBER m
      ), factors AS (
        SELECT MEMBER_ID,PATIENT_ID,PLAN_ID,'uncontrolled_lab' FACTOR_ID,
          IFF(LAB_COUNT=0,'UNKNOWN',IFF(ABNORMAL>0,'MET','NOT_MET')) STATE,30 WEIGHT FROM observations
        UNION ALL SELECT MEMBER_ID,PATIENT_ID,PLAN_ID,'recent_ed',IFF(ED>0,'MET','NOT_MET'),20 FROM observations
        UNION ALL SELECT MEMBER_ID,PATIENT_ID,PLAN_ID,'adherence_concern',
          IFF(LOW_PDC>0,'MET',IFF(MED_COUNT=0 OR MED_UNKNOWN>0,'UNKNOWN','NOT_MET')),15 FROM observations
        UNION ALL SELECT MEMBER_ID,PATIENT_ID,PLAN_ID,'multiple_chronic_conditions',
          IFF(CHRONIC_COUNT>={int(config['chronic_condition_minimum'])},'MET','NOT_MET'),15 FROM observations
        UNION ALL SELECT MEMBER_ID,PATIENT_ID,PLAN_ID,'care_gap',IFF(FOLLOW_UP_GAPS>0,'MET','NOT_MET'),10 FROM observations
        UNION ALL SELECT MEMBER_ID,PATIENT_ID,PLAN_ID,'recent_adverse_event',IFF(AE_COUNT>0,'MET','NOT_MET'),10 FROM observations
      ), lineage AS (
        SELECT MEMBER_ID,'uncontrolled_lab' FACTOR_ID,LAB_ID SOURCE_ID
          FROM latest WHERE FLAG IN ('HIGH','LOW','ABNORMAL')
        UNION ALL SELECT MEMBER_ID,'recent_ed',ENCOUNTER_ID FROM {db}.CURATED.FACT_ENCOUNTER
          WHERE ENCOUNTER_TYPE='ED' AND EVENT_DATE BETWEEN DATEADD(day,-{ed_days},{asof}::DATE) AND {asof}::DATE
        UNION ALL SELECT MEMBER_ID,'adherence_concern',MED_ID FROM {db}.CURATED.FACT_MEDICATION
          WHERE STATUS='active' AND NOT IS_PRN AND PDC<{float(config['adherence_threshold'])}
        UNION ALL SELECT MEMBER_ID,'multiple_chronic_conditions',DIAGNOSIS_ID
          FROM {db}.CURATED.FACT_DIAGNOSIS WHERE STATUS='active'
        UNION ALL SELECT MEMBER_ID,'care_gap',GAP_ID FROM {db}.CURATED.CARE_GAPS
          WHERE MEASURE='TRC' AND STATUS IN ('OPEN','MISSED') AND DUE_DATE<={asof}::DATE
        UNION ALL SELECT MEMBER_ID,'recent_adverse_event',AE_ID FROM {db}.CURATED.ADVERSE_EVENTS
          WHERE EVENT_DATE BETWEEN DATEADD(day,-{ae_days},{asof}::DATE) AND {asof}::DATE
      ), sources AS (
        SELECT MEMBER_ID,FACTOR_ID,ARRAY_SORT(ARRAY_AGG(DISTINCT SOURCE_ID)) SOURCE_IDS
          FROM lineage GROUP BY MEMBER_ID,FACTOR_ID
      )
      SELECT f.MEMBER_ID,f.PATIENT_ID,f.PLAN_ID,f.FACTOR_ID,STATE,WEIGHT,IFF(STATE='MET',WEIGHT,0) POINTS,
        {explanation_sql} TRIGGER_EXPLANATION,
        COALESCE(s.SOURCE_IDS,ARRAY_CONSTRUCT()) SOURCE_IDS,
        {literal(config['rule_version'])} RULE_VERSION,{asof}::DATE AS_OF_DATE,
        'SYNTHETIC' CLASSIFICATION FROM factors f LEFT JOIN sources s
          ON f.MEMBER_ID=s.MEMBER_ID AND f.FACTOR_ID=s.FACTOR_ID""")
    out.append(f"""CREATE OR REPLACE SECURE VIEW {db}.CURATED.MEMBER_360_SNAPSHOT AS
      WITH r AS (SELECT MEMBER_ID,SUM(POINTS) RISK_SCORE,COUNT_IF(STATE='UNKNOWN') UNKNOWN_FACTORS
        FROM {db}.CURATED.MEMBER_RISK_FACTORS GROUP BY MEMBER_ID)
      SELECT m.*,r.RISK_SCORE,r.UNKNOWN_FACTORS,
        IFF(UNKNOWN_FACTORS>0,'Incomplete',CASE WHEN RISK_SCORE<25 THEN 'Low'
          WHEN RISK_SCORE<50 THEN 'Moderate' WHEN RISK_SCORE<75 THEN 'High' ELSE 'Critical' END) RISK_TIER,
        {asof}::DATE AS_OF_DATE,
        (SELECT COUNT(*) FROM {db}.CURATED.FACT_ENCOUNTER x WHERE x.MEMBER_ID=m.MEMBER_ID) ENCOUNTER_COUNT,
        (SELECT COUNT(*) FROM {db}.CURATED.FACT_ENCOUNTER x WHERE x.MEMBER_ID=m.MEMBER_ID AND ENCOUNTER_TYPE='ED') ED_COUNT,
        (SELECT COALESCE(SUM(BILLED_AMOUNT),0) FROM {db}.CURATED.FACT_CLAIM x WHERE x.MEMBER_ID=m.MEMBER_ID) CLAIM_AMOUNT,
        (SELECT AVG(VALUE) FROM {db}.CURATED.FACT_LAB_RESULT x WHERE x.MEMBER_ID=m.MEMBER_ID AND TEST='HbA1c') AVERAGE_A1C,
        (SELECT COUNT(*) FROM {db}.CURATED.FACT_LAB_RESULT x WHERE x.MEMBER_ID=m.MEMBER_ID AND FLAG IN ('HIGH','LOW','ABNORMAL')) ABNORMAL_LAB_COUNT,
        (SELECT AVG(PDC) FROM {db}.CURATED.FACT_MEDICATION x WHERE x.MEMBER_ID=m.MEMBER_ID AND NOT IS_PRN AND STATUS='active') ADHERENCE,
        (SELECT COUNT(*) FROM {db}.CURATED.CARE_GAPS x WHERE x.MEMBER_ID=m.MEMBER_ID AND STATUS IN ('OPEN','MISSED')) CARE_GAP_COUNT,
        (SELECT COUNT(*) FROM {db}.CURATED.CARE_GAPS x WHERE x.MEMBER_ID=m.MEMBER_ID AND MEASURE='TRC'
          AND STATUS IN ('OPEN','MISSED') AND DUE_DATE<={asof}::DATE) FOLLOW_UP_GAP_COUNT
      FROM {db}.CURATED.DIM_MEMBER m JOIN r ON r.MEMBER_ID=m.MEMBER_ID""")
    return out


def governed(database: str) -> List[str]:
    db = identifier(database)
    result = [f"""CREATE ROW ACCESS POLICY IF NOT EXISTS {db}.APP.MEMBER_PLAN_POLICY
      AS (PLAN STRING) RETURNS BOOLEAN -> EXISTS (
        SELECT 1 FROM {db}.APP.USER_ENTITLEMENTS e
        WHERE e.USER_NAME=CURRENT_USER() AND (PLAN='SHARED' OR e.PLAN_ID=PLAN OR e.PLAN_ID='*'))"""]
    result.extend([
        f"""CREATE OR REPLACE SECURE VIEW {db}.APP.DOCUMENT_CHUNKS AS
          SELECT c.* FROM {db}.CURATED.DOCUMENT_CHUNKS c
          JOIN {db}.RAW.DOCUMENT_MANIFEST m
            ON m.ID=c.DOCUMENT_ID AND m.DATA:sha256::STRING=c.SHA256""",
        f"""ALTER VIEW {db}.APP.DOCUMENT_CHUNKS ADD ROW ACCESS POLICY
          {db}.APP.MEMBER_PLAN_POLICY ON(PLAN_ID)""",
    ])
    for name in ["DIM_MEMBER", "MEMBER_360_SNAPSHOT", "MEMBER_RISK_FACTORS"]:
        result.append(f"""CREATE OR REPLACE SECURE VIEW {db}.APP.{name} AS
          SELECT s.* FROM {db}.CURATED.{name} s WHERE EXISTS (
            SELECT 1 FROM {db}.APP.USER_ENTITLEMENTS e WHERE e.USER_NAME=CURRENT_USER()
              AND (e.PLAN_ID=s.PLAN_ID OR e.PLAN_ID='*'))""")
    for name in ["FACT_ENCOUNTER", "FACT_LAB_RESULT", "FACT_MEDICATION", "FACT_DIAGNOSIS", "FACT_CLAIM", "CARE_GAPS", "ADVERSE_EVENTS"]:
        result.append(f"""CREATE OR REPLACE SECURE VIEW {db}.APP.{name} AS
          SELECT f.* FROM {db}.CURATED.{name} f JOIN {db}.APP.DIM_MEMBER m USING(MEMBER_ID)""")
    result.extend([
        f"""CREATE OR REPLACE SECURE VIEW {db}.APP.DIM_PROVIDER AS
          SELECT DISTINCT p.* FROM {db}.CURATED.DIM_PROVIDER p JOIN {db}.APP.DIM_MEMBER m USING(PROVIDER_ID)""",
        f"""CREATE OR REPLACE SECURE VIEW {db}.APP.DIM_CONDITION AS
          SELECT DISTINCT c.* FROM {db}.CURATED.DIM_CONDITION c
            JOIN {db}.APP.FACT_DIAGNOSIS d USING(CONDITION_KEY,ICD10)""",
    ])
    revision_sql = " UNION ALL ".join(
        f"SELECT MAX(UPDATED_AT) UPDATED_AT FROM {db}.RAW.{entity.upper()}" for entity in ENTITIES)
    result.extend([
        f"""CREATE OR REPLACE SECURE VIEW {db}.APP.WORKFLOW_STATE AS
          SELECT (SELECT MAX(UPDATED_AT) FROM ({revision_sql})) SOURCE_VERSION,
            (SELECT STATUS FROM {db}.RAW.PIPELINE_AUDIT ORDER BY STARTED_AT DESC LIMIT 1) PIPELINE_STATUS""",
        f"""CREATE OR REPLACE SECURE VIEW {db}.APP.DOCUMENT_STATUS AS
          SELECT m.ID DOCUMENT_ID,m.DATA:patient_id::STRING PATIENT_ID,
            m.DATA:plan_id::STRING PLAN_ID,
            IFF(c.DOCUMENT_ID IS NOT NULL,'READY','PENDING_OR_FAILED') STATUS
          FROM {db}.RAW.DOCUMENT_MANIFEST m LEFT JOIN
            (SELECT DISTINCT DOCUMENT_ID,SHA256 FROM {db}.CURATED.DOCUMENT_CHUNKS) c
            ON c.DOCUMENT_ID=m.ID AND c.SHA256=m.DATA:sha256::STRING
          WHERE EXISTS (
            SELECT 1 FROM {db}.APP.USER_ENTITLEMENTS e WHERE e.USER_NAME=CURRENT_USER()
              AND (m.DATA:plan_id::STRING='SHARED' OR e.PLAN_ID=m.DATA:plan_id::STRING OR e.PLAN_ID='*'))""",
    ])
    return result


def semantics(database: str, suffix: str = "", plan_id: str = "") -> str:
    db = identifier(database)
    tag = "_" + identifier(suffix) if suffix else ""
    base = f"{db}.APP.MEMBER_360_SNAPSHOT"
    if plan_id:
        base = f"{db}.SEMANTIC.SNAPSHOT{tag}"
    fact_prefix = f"{db}.SEMANTIC." if plan_id else f"{db}.APP."
    def fact(name: str) -> str:
        return fact_prefix + name + tag if plan_id else fact_prefix + name
    return f"""CREATE OR REPLACE SEMANTIC VIEW {db}.SEMANTIC.PATIENT_MEMBER_360_SEMANTIC_VIEW{tag}
      TABLES (members AS {base} PRIMARY KEY(MEMBER_ID)
        WITH SYNONYMS=('patients','enrollees','beneficiaries'),
        encounters AS {fact('FACT_ENCOUNTER')} PRIMARY KEY(ENCOUNTER_ID),
        labs AS {fact('FACT_LAB_RESULT')} PRIMARY KEY(LAB_ID),
        medications AS {fact('FACT_MEDICATION')} PRIMARY KEY(MED_ID),
        conditions AS {fact('DIM_CONDITION')} PRIMARY KEY(CONDITION_KEY,ICD10),
        providers AS {fact('DIM_PROVIDER')} PRIMARY KEY(PROVIDER_ID),
        diagnoses AS {fact('FACT_DIAGNOSIS')} PRIMARY KEY(DIAGNOSIS_ID),
        claims AS {fact('FACT_CLAIM')} PRIMARY KEY(CLAIM_ID),
        care_gaps AS {fact('CARE_GAPS')} PRIMARY KEY(GAP_ID),
        risk_factors AS {fact('MEMBER_RISK_FACTORS')} PRIMARY KEY(MEMBER_ID,FACTOR_ID),
        adverse_events AS {fact('ADVERSE_EVENTS')} PRIMARY KEY(AE_ID))
      RELATIONSHIPS (
        encounters(MEMBER_ID) REFERENCES members(MEMBER_ID),
        labs(MEMBER_ID) REFERENCES members(MEMBER_ID),
        medications(MEMBER_ID) REFERENCES members(MEMBER_ID),
        diagnoses(MEMBER_ID) REFERENCES members(MEMBER_ID),
        claims(MEMBER_ID) REFERENCES members(MEMBER_ID),
        care_gaps(MEMBER_ID) REFERENCES members(MEMBER_ID),
        risk_factors(MEMBER_ID) REFERENCES members(MEMBER_ID),
        adverse_events(MEMBER_ID) REFERENCES members(MEMBER_ID),
        members(PROVIDER_ID) REFERENCES providers(PROVIDER_ID),
        diagnoses(CONDITION_KEY,ICD10) REFERENCES conditions(CONDITION_KEY,ICD10))
      DIMENSIONS (
        members.member_id AS MEMBER_ID, members.patient_id AS PATIENT_ID,
        members.plan_id AS PLAN_ID, members.risk_tier AS RISK_TIER,
        members.as_of_date AS AS_OF_DATE, members.risk_score AS RISK_SCORE,
        members.provider_id AS PROVIDER_ID, providers.provider_id AS PROVIDER_ID,
        providers.provider_name AS NAME,
        conditions.condition_key AS CONDITION_KEY, conditions.icd10 AS ICD10,
        conditions.description AS DESCRIPTION,
        risk_factors.factor_id AS FACTOR_ID, risk_factors.state AS STATE,
        risk_factors.points AS POINTS, risk_factors.source_ids AS TO_JSON(SOURCE_IDS),
        risk_factors.weight AS WEIGHT, risk_factors.trigger_explanation AS TRIGGER_EXPLANATION,
        risk_factors.rule_version AS RULE_VERSION, risk_factors.as_of_date AS AS_OF_DATE,
        adverse_events.ae_id AS AE_ID, adverse_events.event_date AS EVENT_DATE,
        adverse_events.suspect_drug AS SUSPECT_DRUG,
        encounters.encounter_id AS ENCOUNTER_ID, encounters.event_date AS EVENT_DATE,
        encounters.encounter_type AS ENCOUNTER_TYPE, encounters.primary_icd10 AS PRIMARY_ICD10,
        labs.lab_id AS LAB_ID, labs.event_date AS EVENT_DATE, labs.test AS TEST,
        labs.value AS VALUE, labs.unit AS UNIT, labs.flag AS FLAG,
        medications.med_id AS MED_ID, medications.drug AS DRUG,
        medications.pdc AS PDC, medications.status AS STATUS,
        diagnoses.condition_key AS CONDITION_KEY, diagnoses.icd10 AS ICD10,
        diagnoses.description AS DESCRIPTION, diagnoses.status AS STATUS,
        care_gaps.measure AS MEASURE, care_gaps.status AS STATUS,
        care_gaps.due_date AS DUE_DATE)
      METRICS (
        members.member_count AS COUNT(DISTINCT MEMBER_ID),
        encounters.encounter_count AS COUNT(DISTINCT ENCOUNTER_ID),
        encounters.emergency_visit_count AS COUNT(DISTINCT IFF(ENCOUNTER_TYPE='ED',ENCOUNTER_ID,NULL)),
        claims.total_claim_amount AS SUM(BILLED_AMOUNT),
        labs.average_a1c AS AVG(IFF(TEST='HbA1c',VALUE,NULL)),
        labs.abnormal_lab_count AS COUNT(DISTINCT IFF(FLAG IN ('HIGH','LOW','ABNORMAL'),LAB_ID,NULL)),
        medications.medication_adherence_rate AS AVG(IFF(NOT IS_PRN AND STATUS='active',PDC,NULL)),
        care_gaps.care_gap_count AS COUNT(DISTINCT IFF(STATUS IN ('OPEN','MISSED'),GAP_ID,NULL)),
        members.high_risk_member_count AS COUNT(DISTINCT IFF(RISK_TIER IN ('High','Critical'),MEMBER_ID,NULL)),
        members.follow_up_gap_count AS COUNT(DISTINCT IFF(FOLLOW_UP_GAP_COUNT>0 AND RISK_TIER IN ('High','Critical'),MEMBER_ID,NULL)))
      COMMENT='Synthetic demo; High-risk includes High and Critical; one row per member'
      AI_SQL_GENERATION 'Use governed facts for individual labs, medications, diagnoses and dated encounter details.
        Snapshot counts cover full fixture history. Do not interpret all-history ED_COUNT as a 90-day count.
        Do not diagnose or recommend treatment. Scores are synthetic-demo-v1, not clinically validated.'"""
