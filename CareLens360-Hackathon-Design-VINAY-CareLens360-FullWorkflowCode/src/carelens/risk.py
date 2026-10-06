"""Approved synthetic rules; source observations are not clinical recommendations."""

from datetime import date, timedelta
from typing import Any, Dict, List

WEIGHTS = {
    "uncontrolled_lab": 30,
    "recent_ed": 20,
    "adherence_concern": 15,
    "multiple_chronic_conditions": 15,
    "care_gap": 10,
    "recent_adverse_event": 10,
}


def tier(score: int) -> str:
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("Risk score must be an integer from 0 through 100")
    return "Low" if score < 25 else "Moderate" if score < 50 else "High" if score < 75 else "Critical"


def covered_days(fills: List[Dict[str, Any]], as_of: date, window: int) -> int:
    if window <= 0:
        raise ValueError("Adherence window must be positive")
    start = as_of - timedelta(days=window - 1)
    covered = set()
    for fill in fills:
        days = int(fill["days_supply"])
        if days <= 0:
            raise ValueError("Prescription days_supply must be positive")
        first = date.fromisoformat(fill["fill_date"])
        last = first + timedelta(days=days - 1)
        lo, hi = max(first, start), min(last, as_of)
        if lo <= hi:
            covered.update(lo + timedelta(days=i) for i in range((hi - lo).days + 1))
    return len(covered)


def evaluate(member: Dict[str, Any], tables: Dict[str, List[Dict[str, Any]]],
             config: Dict[str, Any]) -> List[Dict[str, Any]]:
    pid = member["patient_id"]
    as_of = date.fromisoformat(config["as_of_date"])

    def rows(name: str) -> List[Dict[str, Any]]:
        return [r for r in tables[name] if r["patient_id"] == pid]

    def recent(value: str, days: int) -> bool:
        return as_of - timedelta(days=days - 1) <= date.fromisoformat(value) <= as_of

    labs = [r for r in rows("lab_results")
            if recent(r["collected_date"], config["lab_window_days"])]
    latest = {}
    for lab in sorted(labs, key=lambda r: (r["collected_date"], r["lab_id"])):
        latest[lab["test"]] = lab
    abnormal = [r for r in latest.values() if r["flag"] in ("HIGH", "LOW", "ABNORMAL")]
    ed = [r for r in rows("encounters") if r["encounter_type"] == "ED"
          and recent(r["admit_date"], config["ed_window_days"])]
    meds = [r for r in rows("medications") if r["status"] == "active" and not r["is_prn"]]
    low = [r for r in meds if r["pdc"] is not None
           and r["pdc"] < config["adherence_threshold"]]
    conditions = [r for r in rows("conditions") if r["status"] == "active"]
    gaps = [r for r in rows("care_gaps") if r["measure"] == "TRC"
            and r["status"] in ("OPEN", "MISSED") and r["due_date"] <= as_of.isoformat()]
    ae = [r for r in rows("adverse_events")
          if recent(r["onset_date"], config["adverse_event_window_days"])]
    inputs = {
        "uncontrolled_lab": (bool(abnormal) if latest else None, [r["lab_id"] for r in abnormal]),
        "recent_ed": (bool(ed), [r["encounter_id"] for r in ed]),
        "adherence_concern": (
            True if low else None if not meds or any(r["pdc"] is None for r in meds) else False,
            [r["med_id"] for r in low]),
        "multiple_chronic_conditions": (
            len({r["condition_key"] for r in conditions}) >= config["chronic_condition_minimum"],
            [r["condition_id"] for r in conditions]),
        "care_gap": (bool(gaps), [r["gap_id"] for r in gaps]),
        "recent_adverse_event": (bool(ae), [r["ae_id"] for r in ae]),
    }
    return [
        {
            "factor_key": f"{member['member_id']}:{factor}",
            "member_id": member["member_id"],
            "patient_id": pid,
            "factor_id": factor,
            "state": "UNKNOWN" if met is None else "MET" if met else "NOT_MET",
            "points": weight if met else 0,
            "source_ids": sources,
            "rule_version": config["rule_version"],
            "as_of_date": config["as_of_date"],
        }
        for factor, weight in WEIGHTS.items()
        for met, sources in [inputs[factor]]
    ]
