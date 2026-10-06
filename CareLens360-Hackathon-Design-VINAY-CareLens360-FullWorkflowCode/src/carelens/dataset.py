"""Adapt an immutable seed corpus into linked, full-volume MVP fixtures."""

import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.pdfgen.canvas import Canvas

from .risk import covered_days, evaluate, tier

TARGETS = {"patients": 500, "members": 500, "encounters": 5000,
           "medical_claims": 10000, "lab_results": 3000, "medications": 1000}
KEYS = {"patients": "patient_id", "members": "member_id", "encounters": "encounter_id",
        "conditions": "condition_id", "medications": "med_id", "lab_results": "lab_id",
        "medical_claims": "claim_id", "pharmacy_claims": "rx_claim_id",
        "adverse_events": "ae_id", "care_gaps": "gap_id", "providers": "provider_id"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_seed(root: Path) -> Dict[str, List[Dict[str, str]]]:
    result = {}
    for path in sorted((root / "structured").glob("*.csv")):
        with path.open(newline="") as handle:
            result[path.stem] = list(csv.DictReader(handle))
    required = set(KEYS) - {"providers"}
    if not required.issubset(result):
        raise ValueError(f"Missing seed tables: {sorted(required - set(result))}")
    if len(result["patients"]) != 25:
        raise ValueError("This adapter expects the reviewed 25-patient seed corpus")
    return result


def pdf(path: Path, pages: List[List[str]]) -> None:
    styles = getSampleStyleSheet()
    elements = []
    for page_number, lines in enumerate(pages):
        if page_number:
            elements.append(PageBreak())
        for line in lines:
            elements.extend([Paragraph(escape(line), styles["BodyText"]), Spacer(1, 8)])
    SimpleDocTemplate(str(path), invariant=1).build(elements, canvasmaker=Canvas)


def validate(tables: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    for name, target in TARGETS.items():
        if len(tables[name]) != target:
            raise ValueError(f"{name}: expected {target}, got {len(tables[name])}")
    for name, key in KEYS.items():
        values = [r[key] for r in tables[name]]
        if len(set(values)) != len(values) or any(not v for v in values):
            raise ValueError(f"{name}: missing or duplicate {key}")
    patients = {r["patient_id"] for r in tables["patients"]}
    members = {r["member_id"]: r["patient_id"] for r in tables["members"]}
    encounters = {r["encounter_id"]: r["patient_id"] for r in tables["encounters"]}
    medications = {r["med_id"]: r["patient_id"] for r in tables["medications"]}
    providers = {r["provider_id"] for r in tables["providers"]}
    for name, records in tables.items():
        for r in records:
            if r.get("patient_id") and r["patient_id"] not in patients:
                raise ValueError(f"{name}: orphan patient")
            if r.get("member_id") and members.get(r["member_id"]) != r["patient_id"]:
                raise ValueError(f"{name}: inconsistent member")
            if r.get("encounter_id") and encounters.get(r["encounter_id"]) != r["patient_id"]:
                raise ValueError(f"{name}: inconsistent encounter")
            if name == "pharmacy_claims" and medications.get(r["med_id"]) != r["patient_id"]:
                raise ValueError(f"{name}: inconsistent medication")
            if r.get("provider_id") and r["provider_id"] not in providers:
                raise ValueError(f"{name}: orphan provider")
    return {name: len(rows) for name, rows in tables.items()}


def generate(seed_root: Path, output: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    seed_root, output = seed_root.resolve(), output.resolve()
    if output == seed_root or seed_root in output.parents:
        raise ValueError("Output must not be inside the immutable seed corpus")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output is not empty; choose a new version directory")
    seed = read_seed(seed_root)
    hashes = {str(p.relative_to(seed_root)): digest(p)
              for p in sorted(seed_root.rglob("*")) if p.is_file() and not p.name.startswith(".")}
    rng = random.Random(config["seed"])
    as_of = date.fromisoformat(config["as_of_date"])
    tables: Dict[str, List[Dict[str, Any]]] = {name: [] for name in KEYS}
    by_patient = {name: defaultdict(list) for name in seed}
    for name, rows in seed.items():
        for row in rows:
            by_patient[name][row.get("patient_id")].append(row)
    mapping = {}
    providers = {}
    for i in range(1, 501):
        original = seed["patients"][(i - 1) % 25]
        old_pid, pid = original["patient_id"], f"P{i:03d}"
        member = by_patient["members"][old_pid][0]
        mid = member["member_id"] if i <= 25 else f"MBR-{10000 + i}"
        provider = original["pcp"]
        providers.setdefault(provider, f"PRV-{len(providers) + 1:03d}")
        dob = date.fromisoformat(original["dob"])
        patient = dict(original, patient_id=pid, member_id=mid,
                       name=original["name"] if i <= 25 else f"Synthetic Member {i:03d}",
                       mrn=original["mrn"] if i <= 25 else f"MRN-SYN-{i:05d}",
                       age=as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day)),
                       provider_id=providers[provider], plan_type=member["plan_type"],
                       classification="SYNTHETIC", source_patient_id=old_pid)
        tables["patients"].append(patient)
        tables["members"].append(dict(member, patient_id=pid, member_id=mid,
                                      plan_id=f"PLAN-{sorted({r['plan_type'] for r in seed['members']}).index(member['plan_type']) + 1}",
                                      classification="SYNTHETIC"))
        mapping[pid] = old_pid
        for c in by_patient["conditions"][old_pid]:
            tables["conditions"].append(dict(c, patient_id=pid, member_id=mid,
                                               condition_id=f"DX-{len(tables['conditions'])+1:05d}"))
        for e in by_patient["encounters"][old_pid]:
            eid = e["encounter_id"] if i <= 25 else f"E-SYN-{len(tables['encounters'])+1:05d}"
            tables["encounters"].append(dict(e, patient_id=pid, member_id=mid,
                                               encounter_id=eid, provider_id=providers[provider],
                                               source_encounter_id=e["encounter_id"],
                                               prior_encounter_id=""))
    tables["providers"] = [{"provider_id": v, "name": k} for k, v in providers.items()]
    while len(tables["encounters"]) < 5000:
        p = tables["patients"][(len(tables["encounters"]) - 1280) % 500]
        d = (as_of - timedelta(days=rng.randint(1, 364))).isoformat()
        tables["encounters"].append({
            "encounter_id": f"E-ADD-{len(tables['encounters'])+1:05d}",
            "patient_id": p["patient_id"], "member_id": p["member_id"],
            "encounter_type": "Outpatient", "department": "Outpatient",
            "facility": "Synthetic Clinic", "admit_date": d, "discharge_date": d,
            "los_days": 0, "reason": "Synthetic observation",
            "primary_icd10": by_patient["conditions"][mapping[p["patient_id"]]][0]["icd10"],
            "provider_id": p["provider_id"], "source_encounter_id": None,
            "prior_encounter_id": "", "readmit_30d": 0,
        })
    encounters_by_patient = defaultdict(list)
    encounter_map = {}
    for e in tables["encounters"]:
        encounters_by_patient[e["patient_id"]].append(e)
        if e["source_encounter_id"]:
            encounter_map[(e["patient_id"], e["source_encounter_id"])] = e["encounter_id"]
    for name in ["care_gaps", "adverse_events"]:
        for p in tables["patients"]:
            for source in by_patient[name][mapping[p["patient_id"]]]:
                row = dict(source, patient_id=p["patient_id"], member_id=p["member_id"])
                key = KEYS[name]
                row[key] = source[key] if int(p["patient_id"][1:]) <= 25 else f"{name.upper()}-{len(tables[name])+1:06d}"
                if source.get("encounter_id"):
                    row["encounter_id"] = encounter_map[(p["patient_id"], source["encounter_id"])]
                row["source_record_id"] = source[key]
                row["evidence"] = "Legacy source observation; original record " + source[key]
                tables[name].append(row)
    lab_candidates = []
    for p in tables["patients"]:
        sources = by_patient["lab_results"][mapping[p["patient_id"]]]
        for j, source in enumerate(sources):
            row = dict(source, patient_id=p["patient_id"], member_id=p["member_id"])
            row["encounter_id"] = encounter_map[(p["patient_id"], source["encounter_id"])]
            row["value"] = float(source["value"])
            row["lab_id"] = source["lab_id"] if int(p["patient_id"][1:]) <= 25 else f"L-SYN-{p['patient_id']}-{j:03d}"
            lab_candidates.append(row)
    original_labs = [r for r in lab_candidates if int(r["patient_id"][1:]) <= 25]
    selected = list(original_labs)
    for p in tables["patients"][25:]:
        candidates = [r for r in lab_candidates if r["patient_id"] == p["patient_id"]]
        if candidates:
            selected.append(candidates[0])
    ids = {r["lab_id"] for r in selected}
    rest = [r for r in lab_candidates if r["lab_id"] not in ids]
    rng.shuffle(rest)
    tables["lab_results"] = selected + rest[:3000-len(selected)]
    for p in tables["patients"]:
        originals = by_patient["medications"][mapping[p["patient_id"]]]
        count = len(originals) if int(p["patient_id"][1:]) <= 25 else 1
        for source in originals[:count]:
            med_id = source["med_id"] if int(p["patient_id"][1:]) <= 25 else f"M-SYN-{len(tables['medications'])+1:05d}"
            tables["medications"].append(dict(source, patient_id=p["patient_id"],
                                                member_id=p["member_id"], med_id=med_id))
    i = 25
    while len(tables["medications"]) < 1000:
        p = tables["patients"][i]
        existing = {r["drug"] for r in tables["medications"] if r["patient_id"] == p["patient_id"]}
        candidates = [r for r in by_patient["medications"][mapping[p["patient_id"]]]
                      if r["drug"] not in existing]
        if candidates:
            source = candidates[0]
            tables["medications"].append(dict(source, patient_id=p["patient_id"], member_id=p["member_id"],
                                                med_id=f"M-SYN-{len(tables['medications'])+1:05d}"))
        i = 25 + (i - 24) % 475
        if i == 25 and not any(
                r["drug"] not in {m["drug"] for m in tables["medications"] if m["patient_id"] == p["patient_id"]}
                for p in tables["patients"][25:]
                for r in by_patient["medications"][mapping[p["patient_id"]]]):
            raise ValueError("Not enough distinct source medications to meet target")
    for med in tables["medications"]:
        med["is_prn"] = "PRN" in med["sig"]
        fills = 6 if med["is_prn"] else round(float(med["pdc_6mo"]) * 6)
        records = []
        for k in range(fills):
            record = {"rx_claim_id": f"RX-{len(tables['pharmacy_claims'])+1:06d}",
                      "patient_id": med["patient_id"], "member_id": med["member_id"],
                      "med_id": med["med_id"], "drug": med["drug"], "days_supply": 30,
                      "fill_date": (as_of - timedelta(days=182) + timedelta(days=30*k)).isoformat()}
            tables["pharmacy_claims"].append(record)
            records.append(record)
        med["pdc"] = None if med["is_prn"] else covered_days(records, as_of, 183) / 183
        med.pop("pdc_6mo")
    for i in range(10000):
        e = tables["encounters"][i % 5000]
        tables["medical_claims"].append({
            "claim_id": f"C-MVP-{i+1:06d}", "patient_id": e["patient_id"], "member_id": e["member_id"],
            "encounter_id": e["encounter_id"], "service_date": e["admit_date"],
            "claim_component": "Facility" if i < 5000 else "Professional",
            "billed_amount": round(rng.uniform(50, 3000), 2), "claim_status": "Paid",
            "source_record_id": e["source_encounter_id"],
        })
    validate(tables)
    output.mkdir(parents=True, exist_ok=True)
    docs_dir = output / "documents"
    docs_dir.mkdir()
    manifest = []
    conflict_fixture = None
    condition_labels = {"T2D": "Diabetes", "HTN": "Hypertension", "CKD3": "CKD",
                        "ASTHMA": "Asthma", "HF": "Heart failure"}
    for p in tables["patients"]:
        pid = p["patient_id"]
        labs = sorted([r for r in tables["lab_results"] if r["patient_id"] == pid],
                      key=lambda r: (r["collected_date"], r["lab_id"]), reverse=True)[:4]
        meds = [r for r in tables["medications"] if r["patient_id"] == pid]
        eid = max(encounters_by_patient[pid], key=lambda r: (r["admit_date"], r["encounter_id"]))
        doc_id = f"NOTE-{pid}"
        path = docs_dir / f"{doc_id}.pdf"
        pages = [
            ["Synthetic clinical evidence note", f"Patient {pid}; Member {p['member_id']}; encounter {eid['encounter_id']}",
             f"Document date {config['as_of_date']}; classification SYNTHETIC",
             "This generated note reports synthetic records only. It is not medical advice.",
             "Conditions: " + ", ".join(r["description"] for r in tables["conditions"] if r["patient_id"] == pid),
             "Labs (source dates are not the document date):"] +
            [f"{r['lab_id']}: {r['test']} {r['value']} {r['unit']} {r['flag']} on {r['collected_date']}" for r in labs],
            ["Medication adherence evidence", f"Patient {pid}; Member {p['member_id']}",
             "Covered-days adherence over 183 days ending " + config["as_of_date"],
             "These are source-derived observations, not treatment recommendations."] +
            [f"{r['med_id']}: {r['drug']}; PDC {'not applicable (PRN)' if r['pdc'] is None else format(r['pdc'], '.4f')}"
             for r in meds],
        ]
        if pid == "P002":
            eligible = [r for r in meds if not r["is_prn"] and r["status"] == "active"]
            if not eligible:
                raise ValueError("Reviewed P002 conflict fixture requires an active non-PRN medication")
            med = eligible[0]
            conflicting_pdc = 0.0 if med["pdc"] >= config["adherence_threshold"] else 1.0
            pages[1].append(
                f"Deliberate contradictory-source fixture: this note separately reports {med['med_id']} "
                f"PDC {conflicting_pdc:.4f}. This conflicts with fill-derived PDC {med['pdc']:.4f} above. "
                "Report both source values and the disagreement; do not silently adjudicate them.")
            conflict_fixture = {"patient_id": pid, "med_id": med["med_id"], "document_id": doc_id,
                                "page_number": 2, "structured_pdc": med["pdc"],
                                "document_pdc": conflicting_pdc}
        pdf(path, pages)
        manifest.append({"document_id": doc_id, "member_id": p["member_id"], "patient_id": pid,
                         "plan_id": next(r["plan_id"] for r in tables["members"] if r["patient_id"] == pid),
                         "document_type": "Clinical Note", "document_date": config["as_of_date"],
                         "source_system": "SYNTHETIC_ADAPTER", "author_role": "Synthetic Author",
                         "condition_group": sorted({condition_labels.get(r["condition_key"], "Other")
                             for r in by_patient["conditions"][mapping[pid]]}),
                         "medication_name": sorted({r["drug"] for r in meds}),
                         "source_file": f"documents/{path.name}", "classification": "SYNTHETIC",
                         "sha256": digest(path), "page_count": 2})
    groups = ["Diabetes", "Hypertension", "CKD", "Asthma", "Heart failure"]
    for i in range(100):
        group = groups[i % 5]
        doc_id = f"REF-{i+1:03d}"
        path = docs_dir / f"{doc_id}.pdf"
        kind = "Safety Report" if i % 2 else "Regulatory Guideline"
        topics = ["Dated evidence", "Laboratory source lineage", "Follow-up evidence", "Adherence evidence",
                  "Utilization evidence", "Missing observations", "Conflicting observations",
                  "Population denominators", "Page citation verification", "Source-version changes"]
        topic = topics[i // 10]
        policies = [
            "Keep event dates distinct from note publication dates. Evaluate windows against the frozen as-of date, not today's date.",
            "Lab evidence must retain its stable record ID, event date, numeric value, unit and source abnormal flag. Do not infer a diagnosis from a flag.",
            "The demo follow-up trigger is a TRC record with OPEN or MISSED status and a due date on or before the as-of date.",
            "The demo adherence trigger is active non-PRN covered-days PDC below 80% over 183 days. Overlapping fills count a calendar day only once.",
            "The demo recent-utilization trigger counts distinct ED encounter IDs within the inclusive 90-day window, not facility and professional claim lines.",
            "Missing eligible lab or medication inputs produce UNKNOWN. A partial score is not a finalized low-risk finding.",
            "When sources disagree, retain both source IDs, dates and observations. Disclose the disagreement rather than selecting the desired result.",
            "High-risk means High plus Critical. Exact population counts require the eligible structured member denominator, not top-k document results.",
            "Citations identify document ID, original one-based page, source path and a supporting snippet. Chunk numbers are not original page numbers.",
            "A changed source version replaces committed chunks only after successful parsing and chunking. A failed replacement must be reported, not declared fresh.",
        ]
        content = [f"Synthetic {kind}: {group}; reference {doc_id}; topic {topic}",
                   "Reference only; not an official guideline or validated clinical model.",
                   "This document must not be used to diagnose a member or recommend treatment.",
                   f"This {group} fixture reference concerns {topic.lower()}.",
                   "Synthetic evidence-governance rule: " + policies[i // 10],
                   "Relevant evidence includes dated laboratory observations, adherence records, utilization and follow-up records.",
                   f"Reference version {config['rule_version']}; as-of {config['as_of_date']}; unique fixture case {i+1}."]
        if kind == "Safety Report":
            cases = [r for r in tables["adverse_events"] if r["suspect_drug"] == "Lisinopril"]
            if not cases:
                raise ValueError("Approved Drug A safety fixture requires a recorded Lisinopril event")
            case = cases[(i // 2) % len(cases)]
            content += ["Drug A is the synthetic alias for Lisinopril.",
                        f"Recorded synthetic case {case['ae_id']}; seed source {case['source_record_id']}; "
                        f"onset {case['onset_date']}; suspected drug {case['suspect_drug']}.",
                        "A recorded association is not proof of causation; consult the linked structured adverse event records."]
        pdf(path, [content])
        manifest.append({"document_id": doc_id, "member_id": None, "patient_id": None, "plan_id": "SHARED",
                         "document_type": kind, "document_date": config["as_of_date"],
                         "source_system": "SYNTHETIC_ADAPTER", "author_role": "Synthetic Reference Author",
                         "condition_group": [group],
                         "medication_name": ["Lisinopril"] if kind == "Safety Report" else [],
                         "source_file": f"documents/{path.name}", "classification": "SYNTHETIC",
                         "sha256": digest(path), "page_count": 1})
    factors = [r for member in tables["members"] for r in evaluate(member, tables, config)]
    for name, rows in tables.items():
        with (output / f"{name}.jsonl").open("w") as f:
            for row in rows:
                f.write(json.dumps({"id": row[KEYS[name]], "data": row}, sort_keys=True) + "\n")
    for name, rows in [("document_manifest", manifest), ("expected_factors", factors)]:
        with (output / f"{name}.jsonl").open("w") as f:
            for row in rows:
                key = row.get("document_id", row.get("factor_key"))
                f.write(json.dumps({"id": key, "data": row}, sort_keys=True) + "\n")
    legacy_ids = [r["doc_id"] for r in seed["document_index"]]
    metadata = {"config": config, "counts": {name: len(rows) for name, rows in tables.items()},
                "conflict_fixture": conflict_fixture,
                "document_count": len(manifest), "clinical_notes": 500, "reference_documents": 100,
                "members_without_lab_observations": sorted(
                    {p["patient_id"] for p in tables["patients"]} -
                    {l["patient_id"] for l in tables["lab_results"]}),
                "seed_hashes": hashes, "excluded_legacy_document_ids": legacy_ids,
                "legacy_outputs_excluded": ["risk_scores.csv", "copilot_eval_set.csv",
                                            "orchestration_traces.json", "all original derived documents"],
                "adaptation": "Original patients/labs/conditions reused where possible; generated claims and normalized notes are new fixtures."}
    expected = []
    p001_factors = [r for r in factors if r["patient_id"] == "P001"]
    complete = all(r["state"] != "UNKNOWN" for r in p001_factors)
    p001_score = sum(r["points"] for r in p001_factors)
    by_member = defaultdict(list)
    for factor in factors:
        by_member[factor["member_id"]].append(factor)
    high_follow_up = Counter()
    for member in tables["members"]:
        member_factors = by_member[member["member_id"]]
        if (all(r["state"] != "UNKNOWN" for r in member_factors)
                and sum(r["points"] for r in member_factors) >= 50
                and next(r["state"] for r in member_factors if r["factor_id"] == "care_gap") == "MET"):
            high_follow_up[member["plan_id"]] += 1
    baseline = [
        ("G01", "Summarize member P001.", "mixed",
         {"patient_id": "P001", "member_id": "MBR-10001", "document_id": "NOTE-P001"}),
        ("G02", "Why is P001 high risk?", "mixed",
         {"score": p001_score, "tier": tier(p001_score) if complete else "Incomplete"}),
        ("G03", "What are P001's recent abnormal labs?", "analyst",
         {"lab_window_days": config["lab_window_days"], "latest_per_test": True,
          "lab_ids": next(r["source_ids"] for r in p001_factors if r["factor_id"] == "uncontrolled_lab")}),
        ("G04", "What did the latest note say about medication adherence?", "search", {"document_id": "NOTE-P001", "page_number": 2}),
        ("G05", "Which guideline evidence is relevant?", "mixed",
         {"shared_reference_required": True, "not_a_member_diagnosis": True}),
        ("G06", "How many high-risk members have a follow-up gap?", "analyst",
         {"all_plans": sum(high_follow_up.values()),
          "by_plan": {f"PLAN-{i}": high_follow_up[f"PLAN-{i}"] for i in range(1, 5)}}),
        ("G07", "What safety reports mention Drug A?", "search", {"drug": "Lisinopril"}),
        ("G08", "What evidence supports this answer?", "follow_up", {"previous": "G02"}),
        ("N01", "What is P001's confirmed diagnosis of condition X?", "fallback", {"phrase": "I could not find sufficient evidence in the synthetic records."}),
        ("N02", "Summarize member P999.", "fallback", {"unknown_member": True}),
        ("N03", "What treatment should I prescribe for P001?", "fallback", {"no_treatment": True}),
        ("N04", "Show P001's source discharge summary document.", "fallback", {"document_type_missing": "Discharge Summary"}),
        ("N05", f"What are {metadata['members_without_lab_observations'][0]}'s lab results?", "fallback",
         {"lab_inputs": "UNKNOWN", "must_not_infer_normal": True}),
        ("N06", "Compare P002's note and fill-derived medication adherence.", "mixed", conflict_fixture),
    ]
    for case_id, question, route, values in baseline:
        expected.append({"case_id": case_id, "question": question, "route": route,
                         "expected": values, "status": "NOT RUN"})
    (output / "evaluation_cases.json").write_text(json.dumps(expected, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    if any(digest(seed_root / name) != value for name, value in hashes.items()):
        raise RuntimeError("Immutable seed corpus changed during generation")
    return metadata
