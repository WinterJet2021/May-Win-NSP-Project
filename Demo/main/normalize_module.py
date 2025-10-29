# Demo/main/normalize_module.py
from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime, timedelta

def normalize_nsp_json(cfg: Dict[str, Any]) -> Dict[str, Any]:
    nurses = cfg["nurses"]
    shifts = [s["code"] for s in cfg["shift_types"]]
    coverage = cfg["coverage_requirements"]

    start = datetime.strptime(cfg["date_horizon"]["start"], "%Y-%m-%d")
    end = datetime.strptime(cfg["date_horizon"]["end"], "%Y-%m-%d")
    num_days = (end - start).days + 1
    dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]

    # Preference weights
    pref_shift_weight = cfg["policy_parameters"]["weights"].get("preferred_shift_satisfaction", 1.0)
    pref_dayoff_weight = cfg["policy_parameters"]["weights"].get("preferred_dayoff_satisfaction", 1.0)

    preferred_shift_bonus = {}
    for n in nurses:
        nid = n["id"]
        for pref in n["preferences"].get("preferred_shifts", []):
            for day in pref["days"]:
                preferred_shift_bonus[(nid, pref["shift"], day)] = pref["priority"]

    preferred_dayoff_penalty = {}
    for n in nurses:
        nid = n["id"]
        for pref in n["preferences"].get("preferred_days_off", []):
            preferred_dayoff_penalty[(nid, pref["date"])] = pref["rank"]

    return {
        "nurses": nurses,
        "shifts": shifts,
        "coverage": coverage,
        "dates": dates,
        "weights": {
            "pref_shift_weight": pref_shift_weight,
            "pref_dayoff_weight": pref_dayoff_weight,
        },
        "preferred_shift_bonus": preferred_shift_bonus,
        "preferred_dayoff_penalty": preferred_dayoff_penalty,
        "rest_hours": cfg["policy_parameters"].get("min_rest_hours_between_shifts", 11),
        "no_consec_nights": cfg["policy_parameters"].get("no_consecutive_nights", True),
    }
