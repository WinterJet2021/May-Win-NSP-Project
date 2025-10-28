# Demo/main/normalize_module.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from datetime import datetime, date, timedelta

WEEKDAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
PRIORITY_TO_WEIGHT = {"high": 5, "medium": 3, "low": 1}
RANK_TO_WEIGHT      = {3: 8, 2: 5, 1: 3}   # positive = prefers OFF

def _to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _to_minutes(hhmm: str) -> int:
    # "08:00" -> 480
    h, m = hhmm.split(":")
    return int(h)*60 + int(m)

def normalize_nsp_json(cfg: Dict[str, Any]) -> Dict[str, Any]:
    # --- horizon & calendar ---
    start = _to_date(cfg["date_horizon"]["start"])
    end   = _to_date(cfg["date_horizon"]["end"])
    if end < start:
        raise ValueError("date_horizon.end < start")

    dates: List[str] = []
    calendar: List[Dict[str, str]] = []
    cur = start
    while cur <= end:
        iso = cur.isoformat()
        dates.append(iso)
        calendar.append({"date": iso, "weekday": WEEKDAYS[cur.weekday()]})
        cur += timedelta(days=1)
    dow_by_date = {c["date"]: c["weekday"] for c in calendar}

    # --- shift types (keep clock times in minutes) ---
    # e.g. {"M":{"start_min":480,"end_min":960}, "A":..., "N":...}
    shift_types: Dict[str, Dict[str, int]] = {}
    for s in cfg["shift_types"]:
        code = s["code"]
        shift_types[code] = {
            "start_min": _to_minutes(s["start"]),
            "end_min":   _to_minutes(s["end"]),
            "name": s.get("name", code),
            "start": s["start"],
            "end":   s["end"],
        }
    shifts = list(shift_types.keys())

    # --- coverage (dictionary and flat rows) ---
    coverage_map: Dict[Tuple[str,str], int] = {}
    coverage_rows: List[Dict[str,Any]] = []
    for row in cfg["coverage_requirements"]:
        d, s, req = row["date"], row["shift"], int(row["req_total"])
        if s not in shifts:              # skip out-of-horizon or unknown shift
            continue
        if d not in dow_by_date:
            continue
        key = (d, s)
        if key in coverage_map:
            raise ValueError(f"Duplicate coverage row for {d} {s}")
        coverage_map[key] = req
        coverage_rows.append({"date": d, "shift": s, "req_total": req})

    # --- nurses & preferences to sparse lookups ---
    nurses = cfg["nurses"]

    # preferred shift bonus: (nurse_id, date, shift) -> weight
    pref_shift_bonus: Dict[Tuple[str,str,str], int] = {}
    # preferred day-OFF: (nurse_id, date) -> weight (positive = wants OFF)
    pref_dayoff_weight: Dict[Tuple[str,str], int] = {}

    for n in nurses:
        nid = n["id"]
        prefs = n.get("preferences", {})

        for ps in prefs.get("preferred_shifts", []):
            sh  = ps["shift"]
            pr  = ps.get("priority", "medium")
            wt  = PRIORITY_TO_WEIGHT.get(pr, 3)
            dows = set(ps.get("days", []))
            if sh not in shifts:
                continue
            for d in dates:
                if dow_by_date[d] in dows:
                    pref_shift_bonus[(nid, d, sh)] = wt

        for off in prefs.get("preferred_days_off", []):
            d  = off["date"]
            rk = int(off.get("rank", 1))
            if d in dow_by_date:
                pref_dayoff_weight[(nid, d)] = max(pref_dayoff_weight.get((nid,d), 0),
                                                    RANK_TO_WEIGHT.get(rk, 3))

    # weights for objective
    w = cfg.get("policy_parameters", {}).get("weights", {}) or {}
    weights = {
        "workload_fairness": w.get("workload_fairness", 1.0),
        "pref_shift":        w.get("preferred_shift_satisfaction", 0.8),
        "pref_dayoff":       w.get("preferred_dayoff_satisfaction", 1.2),
        # penalties for slack (big to discourage)
        "understaff_pen":    1000.0,
        "overstaff_pen":     100.0,
    }

    min_rest = int(cfg.get("policy_parameters", {}).get("min_rest_hours_between_shifts", 11))
    no_consec_nights = bool(cfg.get("policy_parameters", {}).get("no_consecutive_nights", True))

    return {
        "nurses": nurses,
        "dates": dates,
        "calendar": calendar,
        "dow_by_date": dow_by_date,
        "shifts": shifts,
        "shift_types": shift_types,
        "coverage_rows": coverage_rows,
        "coverage": coverage_map,
        "pref_shift_bonus": pref_shift_bonus,
        "pref_dayoff_weight": pref_dayoff_weight,
        "weights": weights,
        "min_rest_hours": min_rest,
        "no_consec_nights": no_consec_nights,
    }
