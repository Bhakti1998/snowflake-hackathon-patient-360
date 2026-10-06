"""Account validation against local independent oracles, not presumed successes."""

import json
from pathlib import Path

from .dataset import TARGETS
from .sql import identifier


def verify(workflow, data: Path):
    db = identifier(workflow.db)
    report = {"database": db, "checks": [], "unrun": [
        "Eight golden agent answers and claim-level semantic support",
        "Five-role positive/negative privilege tests with separate user entitlements",
        "Two-user member/plan isolation through owner-rights Streamlit and direct APIs",
        "Changed-input scheduled task execution and Search freshness",
        "Browser UI and synthetic missing/conflicting operational-error scenarios",
    ]}

    def record(name, actual, expected):
        status = "PASS" if actual == expected else "FAIL"
        report["checks"].append({"check": name, "actual": actual, "expected": expected, "status": status})

    for entity, count in TARGETS.items():
        rows = workflow.execute(f"SELECT COUNT(*),COUNT(DISTINCT ID) FROM {db}.RAW.{entity.upper()}")
        record(entity + " count", rows[0][0], count)
        record(entity + " unique keys", rows[0][1], count)
    record("snapshot count", workflow.execute(f"SELECT COUNT(*) FROM {db}.CURATED.MEMBER_360_SNAPSHOT")[0][0], 500)
    record("factor count", workflow.execute(f"SELECT COUNT(*) FROM {db}.CURATED.MEMBER_RISK_FACTORS")[0][0], 3000)
    factors = workflow.execute(f"""SELECT PATIENT_ID,FACTOR_ID,STATE,POINTS,SOURCE_IDS
      FROM {db}.CURATED.MEMBER_RISK_FACTORS ORDER BY PATIENT_ID,FACTOR_ID""")
    actual = [list(r[:4]) + [sorted(json.loads(r[4]) if isinstance(r[4], str) else r[4])]
              for r in factors]
    expected_rows = [json.loads(line)["data"] for line in (data / "expected_factors.jsonl").read_text().splitlines()]
    expected = sorted([[r["patient_id"], r["factor_id"], r["state"], r["points"], sorted(r["source_ids"])]
                       for r in expected_rows])
    record("independent risk oracle", actual, expected)
    record("manifest count", workflow.execute(f"SELECT COUNT(*) FROM {db}.RAW.DOCUMENT_MANIFEST")[0][0], 600)
    record("original-page coverage", workflow.execute(f"""SELECT COUNT(DISTINCT DOCUMENT_ID||':'||PAGE_NUMBER)
      FROM {db}.CURATED.DOCUMENT_CHUNKS""")[0][0], 1100)
    record("chunk violations", workflow.execute(f"""SELECT COUNT(*) FROM {db}.CURATED.DOCUMENT_CHUNKS
      WHERE TOKEN_COUNT>900 OR (TOKEN_COUNT<500 AND CHUNK_EXCEPTION IS NULL)
        OR (OVERLAP_TOKENS!=0 AND OVERLAP_TOKENS NOT BETWEEN 50 AND 100)
        OR PAGE_NUMBER<1 OR SOURCE_FILE IS NULL OR START_OFFSET<0
        OR END_OFFSET-START_OFFSET!=LENGTH(CHUNK_TEXT)""")[0][0], 0)
    for i in range(1, 5):
        result = workflow.execute(f"""SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
          '{db}.SEMANTIC.CARE_DOCUMENT_SEARCH_PLAN_{i}',
          '{{"query":"adherence","columns":["PLAN_ID","DOCUMENT_ID","PAGE_NUMBER"],"limit":5}}'))""")
        value = result[0][0]
        if isinstance(value, str):
            value = json.loads(value)
        hits = value.get("results", [])
        record(f"plan {i} Search nonempty", bool(hits), True)
        record(f"plan {i} Search isolation", all(r["PLAN_ID"] == f"PLAN-{i}" for r in hits), True)
    output = workflow.evidence / f"verification-{workflow.run_id}.json"
    output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    if any(c["status"] == "FAIL" for c in report["checks"]):
        raise RuntimeError(f"Account validation failed; see {output}")
    return output
