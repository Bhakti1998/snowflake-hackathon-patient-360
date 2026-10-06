"""Explicit, resumable Snowflake deployment with bounded resource changes."""

import json
import hashlib
import re
import uuid
import zipfile
from pathlib import Path
from typing import Dict, Optional

import snowflake.connector

from .agent import specification
from .sql import ENTITIES, curated, foundation, governed, identifier, literal, load_sql, semantics


def connect(name: str, authenticator: Optional[str] = None):
    options = {"connection_name": name, "login_timeout": 60}
    if authenticator:
        options["authenticator"] = authenticator
    return snowflake.connector.connect(**options)


class Deployment:
    def __init__(self, connection, config: Dict, warehouse: str, evidence: Path):
        self.connection = connection
        self.config = config
        self.db = identifier(config["database"])
        if self.db != "CARELENS360_MVP":
            raise ValueError("Only the approved isolated CARELENS360_MVP database may be modified")
        self.warehouse = identifier(warehouse)
        self.evidence = evidence
        evidence.mkdir(parents=True, exist_ok=True)
        self.run_id = str(uuid.uuid4())
        self.log = evidence / f"deployment-{self.run_id}.jsonl"

    def execute(self, statement, params=None):
        with self.connection.cursor() as cursor:
            try:
                cursor.execute(statement, params)
                rows = cursor.fetchall() if cursor.description else []
                entry = {"run_id": self.run_id, "status": "PASS", "query_id": cursor.sfqid,
                         "statement": statement, "rows": len(rows)}
            except snowflake.connector.Error as exc:
                entry = {"run_id": self.run_id, "status": "FAIL", "statement": statement,
                         "error_code": exc.errno, "sqlstate": exc.sqlstate}
                with self.log.open("a") as f:
                    f.write(json.dumps(entry) + "\n")
                raise
            with self.log.open("a") as f:
                f.write(json.dumps(entry) + "\n")
            return rows

    def put(self, path: Path, stage: str):
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        rows = self.execute(f"PUT {literal('file://' + resolved.as_posix())} {stage} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        if not rows or any(row[6] not in ("UPLOADED", "SKIPPED") for row in rows):
            raise RuntimeError(f"Stage upload failed for {path.name}")

    def require_managed(self):
        rows = self.execute(f"""SELECT COMMENT FROM {self.db}.INFORMATION_SCHEMA.DATABASES
          WHERE DATABASE_NAME='{self.db}'""")
        if len(rows) != 1 or rows[0][0] != "CareLens360 managed synthetic MVP":
            raise RuntimeError("Database is not marked as this workflow's managed database")
        self.execute(f"USE WAREHOUSE {self.warehouse}")

    def staged_documents(self, data: Path):
        documents = []
        root = (data / "documents").resolve()
        seen = set()
        for line in (data / "document_manifest.jsonl").read_text().splitlines():
            row = json.loads(line)
            doc = row["data"]
            relative = Path(doc["source_file"])
            if (relative.is_absolute() or any(part in (".", "..") or
                    not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in relative.parts)):
                raise ValueError("Unsafe document stage path")
            path = (data / relative).resolve()
            if root not in path.parents or path.suffix.lower() not in {".pdf", ".docx", ".pptx"}:
                raise ValueError("Document must be a supported file inside the generated documents folder")
            if doc["classification"] != "SYNTHETIC" or row["id"] != doc["document_id"] or row["id"] in seen:
                raise ValueError("Invalid synthetic document manifest identity/classification")
            if any(not isinstance(doc[key], list) or any(not isinstance(v, str) for v in doc[key])
                   for key in ("condition_group", "medication_name")):
                raise ValueError("Condition and medication attributes must be string arrays")
            if hashlib.sha256(path.read_bytes()).hexdigest() != doc["sha256"]:
                raise ValueError(f"Document version checksum mismatch: {row['id']}")
            seen.add(row["id"])
            documents.append((path, relative.parent.as_posix()))
        return documents

    def base(self, data: Path):
        documents = self.staged_documents(data)
        self.execute(f"USE WAREHOUSE {self.warehouse}")
        existing = self.execute(f"SHOW DATABASES LIKE '{self.db}'")
        if existing:
            self.require_managed()
        for statement in foundation(self.db):
            self.execute(statement)
        self.execute(f"""MERGE INTO {self.db}.RAW.WORKFLOW_CONFIG t
          USING (SELECT 'active' ID,PARSE_JSON(%s) DATA) s ON t.ID=s.ID
          WHEN MATCHED THEN UPDATE SET DATA=s.DATA
          WHEN NOT MATCHED THEN INSERT(ID,DATA) VALUES(s.ID,s.DATA)""",
                     (json.dumps(self.config),))
        # Bootstrap only the authenticated deployment principal. All other users
        # remain denied until explicitly entitled by an administrator.
        self.execute(f"""MERGE INTO {self.db}.APP.USER_ENTITLEMENTS t USING
          (SELECT CURRENT_USER() USER_NAME,'*' PLAN_ID) s
          ON t.USER_NAME=s.USER_NAME AND t.PLAN_ID=s.PLAN_ID
          WHEN NOT MATCHED THEN INSERT(USER_NAME,PLAN_ID) VALUES(s.USER_NAME,s.PLAN_ID)""")
        for entity in ENTITIES:
            self.put(data / f"{entity}.jsonl", f"@{self.db}.RAW.DATA_STAGE")
            for sql in load_sql(self.db, entity):
                self.execute(sql)
        for path, directory in documents:
            self.put(path, f"@{self.db}.RAW.DATA_STAGE/{directory}")
        self.execute(f"ALTER STAGE {self.db}.RAW.DATA_STAGE REFRESH")
        for statement in curated(self.db, self.config) + governed(self.db):
            self.execute(statement)

    def procedure(self, repository: Path):
        self.require_managed()
        build = repository / "build"
        build.mkdir(exist_ok=True)
        bundle = build / "workflow.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            for path in sorted((repository / "src/carelens").glob("*.py")):
                archive.write(path, "carelens/" + path.name)
            archive.write(repository / "snowflake/refresh.py", "refresh.py")
        self.put(bundle, f"@{self.db}.APP.CODE_STAGE")
        self.execute(f"""CREATE OR REPLACE PROCEDURE {self.db}.APP.REFRESH_WORKFLOW(PARSE_LIMIT NUMBER)
          RETURNS VARIANT LANGUAGE PYTHON RUNTIME_VERSION='3.11'
          PACKAGES=('snowflake-snowpark-python')
          IMPORTS=('@{self.db}.APP.CODE_STAGE/workflow.zip')
          HANDLER='refresh.run_wrapper' EXECUTE AS OWNER""")
        self.execute(f"""CREATE TASK IF NOT EXISTS {self.db}.APP.REFRESH_TASK
          WAREHOUSE={self.warehouse} SCHEDULE={literal(self.config['refresh_schedule'])}
          AS CALL {self.db}.APP.REFRESH_WORKFLOW({int(self.config['parse_batch_size'])})""")
        # Task stays suspended until explicit, separate approval.

    def parse(self, limit: int):
        if not 1 <= limit <= 600:
            raise ValueError("Parse limit must be 1-600")
        self.require_managed()
        return self.execute(f"CALL {self.db}.APP.REFRESH_WORKFLOW({limit})")

    def search_and_agents(self):
        self.require_managed()
        attrs = "MEMBER_ID,DOCUMENT_TYPE,DOCUMENT_DATE,SOURCE_SYSTEM,AUTHOR_ROLE,CONDITION_GROUP,MEDICATION_NAME,PATIENT_ID"
        for tag, condition in [("SHARED_EVIDENCE_SEARCH", "PLAN_ID='SHARED'"),
                               ("CARE_DOCUMENT_SEARCH", "PLAN_ID!='SHARED'")] + [
                                   (f"CARE_DOCUMENT_SEARCH_PLAN_{i}", f"PLAN_ID='PLAN-{i}'") for i in range(1, 5)]:
            self.execute(f"""CREATE CORTEX SEARCH SERVICE IF NOT EXISTS {self.db}.SEMANTIC.{tag}
              ON CHUNK_TEXT ATTRIBUTES {attrs}
              WAREHOUSE={self.warehouse} TARGET_LAG={literal(self.config['search_target_lag'])}
              AS
              SELECT c.* FROM {self.db}.CURATED.DOCUMENT_CHUNKS c
              JOIN {self.db}.RAW.DOCUMENT_MANIFEST m
                ON m.ID=c.DOCUMENT_ID AND m.DATA:sha256::STRING=c.SHA256
              WHERE {condition}""")
        self.execute(semantics(self.db))
        self.execute(f"""CREATE OR REPLACE AGENT {self.db}.APP.CARE_LENS_AGENT
          FROM SPECIFICATION $${specification(self.db, warehouse=self.warehouse)}$$""")
        for i in range(1, 5):
            tag = f"PLAN_{i}"
            self.execute(f"""CREATE OR REPLACE SECURE VIEW {self.db}.SEMANTIC.SNAPSHOT_{tag}
              AS SELECT * FROM {self.db}.APP.MEMBER_360_SNAPSHOT WHERE PLAN_ID='PLAN-{i}'""")
            for name in ["FACT_ENCOUNTER", "FACT_LAB_RESULT", "FACT_MEDICATION",
                         "FACT_DIAGNOSIS", "FACT_CLAIM", "CARE_GAPS", "MEMBER_RISK_FACTORS", "ADVERSE_EVENTS"]:
                self.execute(f"""CREATE OR REPLACE SECURE VIEW {self.db}.SEMANTIC.{name}_{tag}
                  AS SELECT f.* FROM {self.db}.APP.{name} f JOIN {self.db}.SEMANTIC.SNAPSHOT_{tag}
                  m USING(MEMBER_ID)""")
            self.execute(f"""CREATE OR REPLACE SECURE VIEW {self.db}.SEMANTIC.DIM_PROVIDER_{tag}
              AS SELECT DISTINCT p.* FROM {self.db}.APP.DIM_PROVIDER p
              JOIN {self.db}.SEMANTIC.SNAPSHOT_{tag} m USING(PROVIDER_ID)""")
            self.execute(f"""CREATE OR REPLACE SECURE VIEW {self.db}.SEMANTIC.DIM_CONDITION_{tag}
              AS SELECT DISTINCT c.* FROM {self.db}.APP.DIM_CONDITION c
              JOIN {self.db}.SEMANTIC.FACT_DIAGNOSIS_{tag} d USING(CONDITION_KEY,ICD10)""")
            self.execute(semantics(self.db, tag, f"PLAN-{i}"))
            self.execute(f"""CREATE OR REPLACE AGENT {self.db}.APP.CARE_LENS_AGENT_{tag}
              FROM SPECIFICATION $${specification(self.db, tag, self.warehouse)}$$""")

    def roles(self):
        self.require_managed()
        for role in ["CARE_ADMIN", "CARE_DATA_ENGINEER", "CARE_ANALYST", "CARE_REVIEWER", "CARE_DEMO_USER"]:
            self.execute(f"CREATE ROLE IF NOT EXISTS {role}")
            self.execute(f"GRANT USAGE ON DATABASE {self.db} TO ROLE {role}")
            self.execute(f"GRANT USAGE ON WAREHOUSE {self.warehouse} TO ROLE {role}")
            self.execute(f"GRANT USAGE ON SCHEMA {self.db}.APP TO ROLE {role}")
        for role in ["CARE_ADMIN", "CARE_DATA_ENGINEER"]:
            for schema in ["RAW", "CURATED", "SEMANTIC"]:
                self.execute(f"GRANT USAGE ON SCHEMA {self.db}.{schema} TO ROLE {role}")
            self.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {self.db}.RAW TO ROLE {role}")
            self.execute(f"GRANT USAGE ON PROCEDURE {self.db}.APP.REFRESH_WORKFLOW(NUMBER) TO ROLE {role}")
            self.execute(f"GRANT READ,WRITE ON STAGE {self.db}.RAW.DATA_STAGE TO ROLE {role}")
            self.execute(f"GRANT READ,WRITE ON STAGE {self.db}.APP.CODE_STAGE TO ROLE {role}")
            self.execute(f"GRANT CREATE TABLE ON SCHEMA {self.db}.RAW TO ROLE {role}")
            self.execute(f"GRANT USAGE ON FILE FORMAT {self.db}.RAW.JSON_FORMAT TO ROLE {role}")
            self.execute(f"GRANT SELECT ON ALL VIEWS IN SCHEMA {self.db}.CURATED TO ROLE {role}")
            self.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE {self.db}.CURATED.DOCUMENT_CHUNKS TO ROLE {role}")
        for role in ["CARE_ADMIN", "CARE_ANALYST", "CARE_REVIEWER"]:
            self.execute(f"GRANT SELECT ON ALL VIEWS IN SCHEMA {self.db}.APP TO ROLE {role}")
        # Reviewer/demo app sharing is gated on live isolation acceptance.
        self.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE {self.db}.APP.USER_ENTITLEMENTS TO ROLE CARE_ADMIN")
        self.execute(f"GRANT USAGE ON SCHEMA {self.db}.SEMANTIC TO ROLE CARE_ADMIN")
        self.execute(f"GRANT SELECT ON ALL VIEWS IN SCHEMA {self.db}.CURATED TO ROLE CARE_ADMIN")
        self.execute(f"GRANT SELECT ON ALL SEMANTIC VIEWS IN SCHEMA {self.db}.SEMANTIC TO ROLE CARE_ADMIN")
        self.execute(f"GRANT USAGE ON ALL CORTEX SEARCH SERVICES IN SCHEMA {self.db}.SEMANTIC TO ROLE CARE_ADMIN")
        self.execute(f"GRANT USAGE ON ALL AGENTS IN SCHEMA {self.db}.APP TO ROLE CARE_ADMIN")
        self.execute(f"GRANT MONITOR,OPERATE ON TASK {self.db}.APP.REFRESH_TASK TO ROLE CARE_ADMIN")

    def app(self, repository: Path):
        self.require_managed()
        for path in sorted((repository / "app").glob("*")):
            if path.is_file():
                self.put(path, f"@{self.db}.APP.CODE_STAGE/app")
        self.put(repository / "src/carelens/response.py", f"@{self.db}.APP.CODE_STAGE/app")
        self.execute(f"""CREATE OR REPLACE STREAMLIT {self.db}.APP.CARELENS360
          ROOT_LOCATION='@{self.db}.APP.CODE_STAGE/app'
          MAIN_FILE='streamlit_app.py' QUERY_WAREHOUSE={self.warehouse}
          TITLE='CareLens360 - Synthetic Evidence Copilot'""")
        for role in ["CARE_ADMIN"]:
            self.execute(f"GRANT USAGE ON STREAMLIT {self.db}.APP.CARELENS360 TO ROLE {role}")
