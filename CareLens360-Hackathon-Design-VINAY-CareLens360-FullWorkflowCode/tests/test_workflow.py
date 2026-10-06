import json
import os
import hashlib
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from carelens.agent import parse_response, specification
from carelens.chunks import split_page
from carelens.dataset import generate, validate
from carelens.risk import covered_days, evaluate, tier
from carelens.sql import identifier, curated, foundation, load_sql, semantics
from carelens.response import validate_format, DISCLAIMER
from carelens.deploy import Deployment

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("score,expected", [(0, "Low"), (24, "Low"), (25, "Moderate"),
    (49, "Moderate"), (50, "High"), (74, "High"), (75, "Critical"), (100, "Critical")])
def test_tiers(score, expected):
    assert tier(score) == expected


@pytest.mark.parametrize("score", [-1, 101, True, 1.5])
def test_invalid_score(score):
    with pytest.raises(ValueError):
        tier(score)


def test_adherence_deduplicates_overlap_and_clips_window():
    fills = [{"fill_date": "2026-09-01", "days_supply": 30},
             {"fill_date": "2026-09-15", "days_supply": 30}]
    assert covered_days(fills, date(2026, 9, 30), 183) == 30


def test_chunks_measured_overlap_and_spans():
    text = " ".join(f"word{i}" for i in range(1900))
    chunks = split_page(text, lambda s: len(s.split()))
    assert [c["tokens"] for c in chunks] == [800, 800, 450]
    assert all(c["overlap_tokens"] == 75 for c in chunks[:-1])
    assert chunks[-1]["exception"] == "RESIDUAL"
    assert all(text[c["start"]:c["end"]] == c["text"] for c in chunks)
    assert split_page("short page", lambda s: len(s.split()))[0]["exception"] == "SHORT_PAGE"


def test_empty_page_is_error():
    with pytest.raises(ValueError):
        split_page("", len)


def test_sql_rejects_identifier_injection():
    with pytest.raises(ValueError):
        identifier("MYDB; DROP DATABASE OTHER")
    assert identifier("carelens360_mvp") == "CARELENS360_MVP"
    with pytest.raises(ValueError):
        load_sql("CARELENS360_MVP", "not_an_entity")


def test_sql_builders_and_agent_wire_plan_scopes():
    config = json.loads((ROOT / "config/workflow.json").read_text())
    assert len(foundation(config["database"])) > 20
    sql = "\n".join(curated(config["database"], config))
    assert "'uncontrolled_lab'" in sql and "'recent_adverse_event'" in sql
    assert "183" in sql and "COUNT(DISTINCT c.DAY)" in sql
    semantic = semantics(config["database"], "PLAN_1", "PLAN-1")
    assert "FACT_LAB_RESULT_PLAN_1" in semantic and "RELATIONSHIPS" in semantic
    spec = yaml.safe_load(specification(config["database"], "PLAN_1"))
    resources = spec["tool_resources"]
    assert resources["ClinicalDocumentSearch"]["search_service"].endswith("_PLAN_1")
    assert resources["SharedEvidenceSearch"]["search_service"].endswith("SHARED_EVIDENCE_SEARCH")
    assert resources["PatientAnalytics"]["semantic_view"].endswith("_PLAN_1")


def test_agent_response_drops_hidden_reasoning_and_surfaces_errors():
    data = ('event: response.thinking.delta\ndata: {"text":"private"}\n\n'
            'event: response.text.delta\ndata: {"text":"Summary"}\n\n')
    assert parse_response(data)["text"] == "Summary"
    with pytest.raises(RuntimeError):
        parse_response('event: error\ndata: {"message":"failed"}\n')


def test_unknown_labs_not_zero_risk():
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    tables = {k: [] for k in ["lab_results", "encounters", "medications",
                              "conditions", "care_gaps", "adverse_events"]}
    factors = evaluate({"patient_id": "P001", "member_id": "MBR-10001"}, tables, cfg)
    assert len(factors) == 6
    assert next(r for r in factors if r["factor_id"] == "uncontrolled_lab")["state"] == "UNKNOWN"
    assert next(r for r in factors if r["factor_id"] == "adherence_concern")["state"] == "UNKNOWN"


def test_full_generated_dataset():
    output = ROOT / "data/generated/v5"
    if not output.exists():
        pytest.skip("Generate the full fixture before this integration test")
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["clinical_notes"] == 500 and manifest["reference_documents"] == 100
    assert len(list((output / "documents").glob("*.pdf"))) == 600
    documents = [json.loads(line)["data"] for line in (output / "document_manifest.jsonl").read_text().splitlines()]
    assert len([d for d in documents if d["document_type"] in {"Safety Report", "Regulatory Guideline"}]) == 100
    assert {g for d in documents if d["document_type"] == "Clinical Note" for g in d["condition_group"]} >= {
        "Diabetes", "Hypertension", "CKD", "Asthma", "Heart failure"}
    for document in documents:
        path = output / document["source_file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == document["sha256"]
        assert len(re.findall(rb"/Type\s*/Page\b", path.read_bytes())) == document["page_count"]
    tables = {}
    for key in ["patients", "members", "providers", "conditions", "encounters",
                "medications", "lab_results", "medical_claims", "pharmacy_claims",
                "adverse_events", "care_gaps"]:
        tables[key] = [json.loads(line)["data"] for line in (output / f"{key}.jsonl").read_text().splitlines()]
    counts = validate(tables)
    assert counts["members"] == 500 and counts["medical_claims"] == 10000
    assert {"T2D", "HTN", "CKD3", "ASTHMA", "HF"}.issubset(
        {r["condition_key"] for r in tables["conditions"]})
    assert all("pdc_6mo" not in r for r in tables["medications"])
    expected = [json.loads(line)["data"] for line in (output / "expected_factors.jsonl").read_text().splitlines()]
    actual = [r for m in tables["members"] for r in evaluate(m, tables, manifest["config"])]
    assert actual == expected
    assert len(expected) == 3000
    conflict = manifest["conflict_fixture"]
    assert conflict["patient_id"] == "P002" and conflict["page_number"] == 2
    assert conflict["structured_pdc"] != conflict["document_pdc"]


def test_preserve_seed_guard(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        generate(tmp_path, tmp_path / "generated", {})


def test_public_events_do_not_duplicate_text_or_expose_thoughts():
    events = [
        {"event": "response.text.delta", "data": '{"text":"Sum","content_index":0}'},
        {"event": "response.tool_result.analyst.delta", "data": {"delta": {"think": "private"}}},
        {"event": "response.text", "data": {"text": "Summary", "content_index": 0}},
        {"event": "response.tool_result", "data": {"status": "success", "content": [
            {"type": "json", "json": {"sql": "SELECT 1", "think": "private"}},
            {"type": "thinking", "text": "private"}]}},
        {"event": "response", "data": {"status": "completed", "content": [
            {"type": "thinking", "text": "private"}, {"type": "text", "text": "Summary"}]}},
    ]
    parsed = parse_response(events)
    assert parsed["text"] == "Summary"
    assert "private" not in json.dumps(parsed)
    assert "SELECT 1" in json.dumps(parsed)


@pytest.mark.parametrize("events", [
    [{"event": "response", "data": {"warnings": [{"message": "tool missing"}]}}],
    [{"event": "response.tool_result", "data": {"status": "error"}}],
    [{"event": "response", "data": {"status": "incomplete"}}],
    [{"event": "response.error", "data": {"message": "failed"}}],
    [{"event": "response.thinking.delta", "data": {"text": "private"}}],
])
def test_agent_errors_are_not_successful_answers(events):
    with pytest.raises(RuntimeError):
        parse_response(events)


def test_final_json_annotations_and_format_gate():
    text = "\n".join("## " + h for h in [
        "Summary", "Key Evidence", "Risk Drivers", "Evidence Citations", "Limitations"])
    text += "\n" + DISCLAIMER
    annotation = {"type": "cortex_search_citation", "doc_id": "NOTE-P001:hash:2:0"}
    parsed = parse_response(json.dumps({"status": "completed", "content": [
        {"type": "text", "text": text, "annotations": [annotation]}]}))
    assert parsed["annotations"] == [annotation]
    cleaned = validate_format(parsed["text"])
    assert "## Summary" in cleaned
    with pytest.raises(ValueError):
        validate_format(text.replace("## Key Evidence", "## Wrong"))
    with pytest.raises(ValueError):
        validate_format(text.replace(DISCLAIMER, "This is synthetic data."))
    # Single-# and bold-wrapped headings are now normalised, not rejected
    assert "## Summary" in validate_format(text.replace("## Summary", "# Summary"))
    assert "## Summary" in validate_format(text.replace("## Summary", "## **Summary**"))
    assert "## Summary" in validate_format(text.replace("## Summary", "  ## Summary"))


@pytest.mark.parametrize("phase", ["procedure", "parse", "search_and_agents", "roles", "app"])
def test_mutating_phases_reject_unmanaged_database(tmp_path, phase):
    class Unmanaged(Deployment):
        def execute(self, statement, params=None):
            self.statements.append(statement)
            return [("Unrelated database",)]
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    workflow = Unmanaged(None, cfg, "TEST_WAREHOUSE", tmp_path)
    workflow.statements = []
    args = [10] if phase == "parse" else [ROOT] if phase in ("procedure", "app") else []
    with pytest.raises(RuntimeError, match="managed"):
        getattr(workflow, phase)(*args)
    assert len(workflow.statements) == 1
    assert workflow.statements[0].startswith("SELECT COMMENT")


def test_policy_and_risk_lineage_are_wired():
    from carelens.sql import governed
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    sql = "\n".join(governed(cfg["database"]))
    assert "ALTER VIEW CARELENS360_MVP.APP.DOCUMENT_CHUNKS ADD ROW ACCESS POLICY" in sql
    assert "PLAN='SHARED'" in sql
    assert "SOURCE_IDS" in "\n".join(curated(cfg["database"], cfg))
    assert "risk_factors" in semantics(cfg["database"], "PLAN_1", "PLAN-1")
    spec = yaml.safe_load(specification(cfg["database"], "PLAN_1", "TEST_WAREHOUSE"))
    assert spec["tool_resources"]["PatientAnalytics"]["execution_environment"]["warehouse"] == "TEST_WAREHOUSE"


def test_full_generation_is_reproducible_and_keeps_seed_immutable(tmp_path):
    seed = Path(os.environ.get("CARELENS_SEED_FOLDER", "/Users/vr11/Downloads/hcls360_dataset"))
    if not seed.exists():
        pytest.skip("Set CARELENS_SEED_FOLDER to the reviewed synthetic seed corpus")
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    first, second = tmp_path / "first", tmp_path / "second"
    result = generate(seed, first, cfg)
    assert generate(seed, second, cfg) == result
    def hashes(root):
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file()}
    assert hashes(first) == hashes(second)
    cases = json.loads((first / "evaluation_cases.json").read_text())
    assert len([c for c in cases if c["case_id"].startswith("G")]) == 8
    assert all(c["status"] == "NOT RUN" for c in cases)
    refs = list((first / "documents").glob("REF-*.pdf"))
    assert len({hashlib.sha256(p.read_bytes()).hexdigest() for p in refs}) == 100
    with pytest.raises(ValueError, match="not empty"):
        generate(seed, first, cfg)


def test_complete_zero_and_full_score_with_duplicate_observations():
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    member = {"patient_id": "P001", "member_id": "MBR-10001"}
    tables = {k: [] for k in ["lab_results", "encounters", "medications", "conditions", "care_gaps", "adverse_events"]}
    tables["lab_results"] = [{"patient_id": "P001", "lab_id": "L1",
                              "collected_date": "2026-09-30", "test": "Test", "flag": "NORMAL"}]
    tables["medications"] = [{"patient_id": "P001", "med_id": "M1", "status": "active", "is_prn": False, "pdc": 1.0}]
    factors = evaluate(member, tables, cfg)
    assert all(r["state"] == "NOT_MET" for r in factors)
    assert sum(r["points"] for r in factors) == 0
    tables["lab_results"][0]["flag"] = "HIGH"
    tables["lab_results"].append(dict(tables["lab_results"][0], lab_id="L2"))
    tables["medications"][0]["pdc"] = 0.5
    tables["conditions"] = [{"patient_id": "P001", "condition_id": f"DX{i}", "condition_key": key, "status": "active"}
                            for i, key in enumerate(["T2D", "HTN"])]
    tables["encounters"] = [{"patient_id": "P001", "encounter_id": f"E{i}", "encounter_type": "ED", "admit_date": "2026-09-30"}
                            for i in range(2)]
    tables["care_gaps"] = [{"patient_id": "P001", "gap_id": "G1", "measure": "TRC", "status": "OPEN", "due_date": "2026-09-30"}]
    tables["adverse_events"] = [{"patient_id": "P001", "ae_id": "AE1", "onset_date": "2026-09-30"}]
    factors = evaluate(member, tables, cfg)
    assert len(factors) == 6 and all(r["state"] == "MET" for r in factors)
    assert sum(r["points"] for r in factors) == 100


def test_inclusive_lookback_and_latest_lab_overrides_older_flag():
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    tables = {k: [] for k in ["lab_results", "encounters", "medications", "conditions", "care_gaps", "adverse_events"]}
    tables["lab_results"] = [
        {"patient_id": "P001", "lab_id": "OLD", "test": "Test", "flag": "HIGH", "collected_date": "2026-09-29"},
        {"patient_id": "P001", "lab_id": "NEW", "test": "Test", "flag": "NORMAL", "collected_date": "2026-09-30"}]
    tables["encounters"] = [{"patient_id": "P001", "encounter_id": key, "encounter_type": "ED", "admit_date": day}
                            for key, day in [("IN", "2026-07-03"), ("OUT", "2026-07-02"), ("FUTURE", "2026-10-01")]]
    factors = {r["factor_id"]: r for r in evaluate({"patient_id": "P001", "member_id": "MBR-10001"}, tables, cfg)}
    assert factors["uncontrolled_lab"]["state"] == "NOT_MET"
    assert factors["recent_ed"]["source_ids"] == ["IN"]


def test_document_staging_checks_paths_versions_and_formats(tmp_path):
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    workflow = Deployment(None, cfg, "TEST_WAREHOUSE", tmp_path / "evidence")
    data = tmp_path / "data"
    (data / "documents").mkdir(parents=True)
    document = data / "documents/test.docx"
    document.write_bytes(b"Versioned test payload; not a live parse fixture")
    row = {"id": "DOC1", "data": {"document_id": "DOC1", "classification": "SYNTHETIC",
           "source_file": "documents/test.docx", "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
           "condition_group": ["CKD"], "medication_name": []}}
    manifest = data / "document_manifest.jsonl"
    manifest.write_text(json.dumps(row) + "\n")
    assert workflow.staged_documents(data) == [(document.resolve(), "documents")]
    row["data"]["sha256"] = "wrong"
    manifest.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="checksum"):
        workflow.staged_documents(data)
    row["data"]["source_file"] = "../private.pdf"
    manifest.write_text(json.dumps(row) + "\n")
    with pytest.raises(ValueError, match="Unsafe"):
        workflow.staged_documents(data)


def test_app_does_not_share_with_demo_or_reviewer_before_isolation_acceptance(tmp_path):
    class Capture(Deployment):
        def require_managed(self):
            return None
        def put(self, path, stage):
            assert path.is_file()
        def execute(self, statement, params=None):
            self.statements.append(statement)
            return []
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    workflow = Capture(None, cfg, "TEST_WAREHOUSE", tmp_path)
    workflow.statements = []
    workflow.app(ROOT)
    grants = [s for s in workflow.statements if s.startswith("GRANT USAGE ON STREAMLIT")]
    assert len(grants) == 1 and grants[0].endswith("TO ROLE CARE_ADMIN")


def test_put_preserves_actual_filename_spaces(tmp_path):
    class Capture(Deployment):
        def execute(self, statement, params=None):
            self.statement = statement
            return [("", "", "", "", "", "", "UPLOADED")]
    cfg = json.loads((ROOT / "config/workflow.json").read_text())
    workflow = Capture(None, cfg, "TEST_WAREHOUSE", tmp_path / "evidence")
    path = tmp_path / "input with spaces.jsonl"
    path.write_text("{}\n")
    workflow.put(path, "@CARELENS360_MVP.RAW.DATA_STAGE")
    assert f"'file://{path.resolve().as_posix()}'" in workflow.statement
    assert "%20" not in workflow.statement
