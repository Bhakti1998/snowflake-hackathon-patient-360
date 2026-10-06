"""Snowpark procedure handler: incremental parsing, measured chunks and audit."""

import json
import uuid

from carelens.chunks import split_page


def run_wrapper(session, parse_limit):
    return run(session, "CARELENS360_MVP", int(parse_limit))


def run(session, database, parse_limit):
    if database != "CARELENS360_MVP":
        raise ValueError("Procedure restricted to the approved database")
    if not 1 <= parse_limit <= 600:
        raise ValueError("Parse limit must be between 1 and 600")
    run_id = str(uuid.uuid4())
    session.sql(f"""INSERT INTO {database}.RAW.PIPELINE_AUDIT
      (RUN_ID,OPERATION,STATUS) VALUES(?, 'PARSE_AND_CHUNK','RUNNING')""", params=[run_id]).collect()
    completed = 0
    active_document = None
    try:
        session.sql(f"ALTER STAGE {database}.RAW.DATA_STAGE REFRESH").collect()
        pending = session.sql(f"""
          WITH done AS (
            SELECT DISTINCT p.DOCUMENT_ID, p.SHA256 FROM {database}.RAW.DOCUMENT_PARSE_RESULTS p
            JOIN {database}.CURATED.DOCUMENT_CHUNKS c
              ON c.DOCUMENT_ID=p.DOCUMENT_ID AND c.SHA256=p.SHA256
            WHERE p.ERROR IS NULL)
          SELECT m.ID, m.DATA FROM {database}.RAW.DOCUMENT_MANIFEST m
          LEFT JOIN done d ON d.DOCUMENT_ID=m.ID AND d.SHA256=m.DATA:sha256::STRING
          WHERE d.DOCUMENT_ID IS NULL
          ORDER BY m.ID LIMIT {parse_limit}""").collect()
        for row in pending:
            document = json.loads(row["DATA"]) if isinstance(row["DATA"], str) else row["DATA"]
            doc_id = row["ID"]
            active_document = (doc_id, document["sha256"])
            parsed_row = session.sql(f"""
              SELECT AI_PARSE_DOCUMENT(TO_FILE('@{database}.RAW.DATA_STAGE',?),
                OBJECT_CONSTRUCT('mode','LAYOUT','page_split',TRUE), TRUE) AS RESULT""",
                params=[document["source_file"]]).collect()[0]
            result = parsed_row["RESULT"]
            if isinstance(result, str):
                result = json.loads(result)
            error = result.get("error") if result else "Parser returned NULL"
            session.sql(f"""INSERT INTO {database}.RAW.DOCUMENT_PARSE_RESULTS
              (DOCUMENT_ID,SHA256,PARSED_RESULT,ERROR,RUN_ID)
              SELECT ?,?,PARSE_JSON(?),NULLIF(?,''),?""",
                # Snowpark binds Python None as the string 'None'; bind '' and convert to NULL.
                params=[doc_id, document["sha256"], json.dumps(result), str(error) if error else "", run_id]).collect()
            if error:
                raise RuntimeError(f"Document {doc_id}: parse failed; see DOCUMENT_PARSE_RESULTS")
            value = result["value"]
            if isinstance(value, str):
                value = json.loads(value)
            pages = value.get("pages") if isinstance(value, dict) else None
            if not pages:
                raise RuntimeError(f"Document {doc_id}: missing page-aware parse output")
            records = []
            for page in pages:
                page_number = int(page["index"]) + 1
                def counter(text):
                    return int(session.sql(
                        "SELECT SNOWFLAKE.CORTEX.COUNT_TOKENS('snowflake-arctic-embed-m-v1.5',?)",
                        params=[text]).collect()[0][0])
                for i, chunk in enumerate(split_page(page["content"], counter)):
                    records.append([
                        f"{doc_id}:{document['sha256']}:{page_number}:{i}", doc_id,
                        document["member_id"], document["patient_id"], document["plan_id"],
                        document["document_type"], document["document_date"], document["source_system"],
                        document["author_role"], json.dumps(document["condition_group"]),
                        json.dumps(document["medication_name"]),
                        page_number, ("Parser-rendered DOCX layout page" if
                                      document["source_file"].lower().endswith(".docx") else "Parsed page"),
                        document["source_file"], chunk["text"],
                        chunk["start"], chunk["end"],
                        chunk["tokens"], chunk["overlap_tokens"], chunk["exception"],
                        "snowflake-arctic-embed-m-v1.5/COUNT_TOKENS", document["sha256"], document["classification"],
                    ])
            if not records:
                raise RuntimeError(f"Document {doc_id}: no chunks")
            session.sql("BEGIN").collect()
            try:
                session.sql(f"DELETE FROM {database}.CURATED.DOCUMENT_CHUNKS WHERE DOCUMENT_ID=?",
                            params=[doc_id]).collect()
                for record in records:
                    session.sql(f"""INSERT INTO {database}.CURATED.DOCUMENT_CHUNKS
                      (CHUNK_ID,DOCUMENT_ID,MEMBER_ID,PATIENT_ID,PLAN_ID,DOCUMENT_TYPE,DOCUMENT_DATE,
                       SOURCE_SYSTEM,AUTHOR_ROLE,CONDITION_GROUP,MEDICATION_NAME,PAGE_NUMBER,
                       SECTION,SOURCE_FILE,CHUNK_TEXT,START_OFFSET,END_OFFSET,TOKEN_COUNT,OVERLAP_TOKENS,CHUNK_EXCEPTION,
                       TOKENIZER,SHA256,CLASSIFICATION)
                      SELECT {','.join('PARSE_JSON(?)' if j in (9, 10) else '?'
                                      for j in range(len(record)))}""", params=record).collect()
                session.sql("COMMIT").collect()
            except Exception:
                session.sql("ROLLBACK").collect()
                raise
            completed += 1
            active_document = None
        session.sql(f"""UPDATE {database}.RAW.PIPELINE_AUDIT SET STATUS='SUCCEEDED',
          DETAILS=?,FINISHED_AT=CURRENT_TIMESTAMP() WHERE RUN_ID=?""",
            params=[f"Parsed {completed} documents", run_id]).collect()
        return {"run_id": run_id, "parsed_documents": completed}
    except Exception as exc:
        # Mark any apparent parse success unusable if its chunking did not commit.
        if active_document:
            session.sql(f"""UPDATE {database}.RAW.DOCUMENT_PARSE_RESULTS SET ERROR=?
              WHERE RUN_ID=? AND DOCUMENT_ID=? AND SHA256=? AND ERROR IS NULL""",
                params=[f"Chunking/processing failed: {type(exc).__name__}", run_id,
                        *active_document]).collect()
        session.sql(f"""UPDATE {database}.RAW.PIPELINE_AUDIT SET STATUS='FAILED',
          DETAILS=?,FINISHED_AT=CURRENT_TIMESTAMP() WHERE RUN_ID=?""",
            params=[str(exc)[:2000], run_id]).collect()
        raise
