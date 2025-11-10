# Demo/main/normalize_module.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta

_PRIORITY_TO_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0}

def _weekday_name(iso_date: str) -> str:
    # Return Mon/Tue/.../Sun
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%a")

def _expand_dates(start_iso: str, end_iso: str) -> List[str]:
    s = datetime.strptime(start_iso, "%Y-%m-%d").date()
    e = datetime.strptime(end_iso, "%Y-%m-%d").date()
    out: List[str] = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out

def _extract_shifts(shift_types: List[Dict[str, Any]]) -> List[str]:
    # Accept codes, map D->M and E->A to be consistent with UI canonicalization
    mapped = []
    for s in shift_types or []:
        c = (s.get("code") or "").upper()
        if c == "D": c = "M"
        if c == "E": c = "A"
        if c in ("M","A","N") and c not in mapped:
            mapped.append(c)
    return mapped or ["M","A","N"]

def normalize_nsp_json(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts UI/chatbot/manager JSON into the compact structure the solver expects:
      - nurses: [{id,...}]
      - dates: [YYYY-MM-DD,...]
      - shifts: ['M','A','N']
      - coverage: [{'date','shift','req_total'}, ...]
      - preferred_shift_bonus: {(nid,shift,weekday)->weight}
      - preferred_dayoff_penalty: {(nid,date)->rank}
      - weights: {'pref_shift_weight','pref_dayoff_weight','shortfall_penalty','overage_penalty'}
      - no_consec_nights: bool
    """
    nurses = list(cfg.get("nurses", []))
    # horizon
    if "date_horizon" in cfg:
        start_iso = cfg["date_horizon"]["start"]
        end_iso   = cfg["date_horizon"]["end"]
    else:
        # fallback from coverage requirements
        dates_cov = [r.get("date") for r in cfg.get("coverage_requirements", []) if r.get("date")]
        if not dates_cov:
            raise ValueError("Missing date_horizon and coverage_requirements are empty.")
        start_iso, end_iso = min(dates_cov), max(dates_cov)
    dates = _expand_dates(start_iso, end_iso)

    # shifts
    shifts = _extract_shifts(cfg.get("shift_types", []))

    # coverage
    coverage_in = cfg.get("coverage_requirements", [])
    coverage: List[Dict[str, Any]] = []
    for r in coverage_in:
        d = r.get("date")
        s = (r.get("shift") or "").upper()
        if s == "D": s = "M"
        if s == "E": s = "A"
        if d in dates and s in ("M","A","N"):
            coverage.append({"date": d, "shift": s, "req_total": int(r.get("req_total", 0))})

    # preferences -> dense maps
    pref_shift_bonus: Dict[Tuple[str,str,str], float] = {}
    pref_dayoff_penalty: Dict[Tuple[str,str], float] = {}
    for n in nurses:
        nid = n.get("id")
        if not nid: continue
        prefs = n.get("preferences", {}) or {}
        # preferred shifts: (nid, shift, weekday)->weight
        for p in prefs.get("preferred_shifts", []) or []:
            shift = (p.get("shift") or "").upper()
            if shift == "D": shift = "M"
            if shift == "E": shift = "A"
            if shift not in ("M","A","N"): continue
            prio = str(p.get("priority", "low")).lower()
            w = _PRIORITY_TO_WEIGHT.get(prio, 1.0)
            day_names = p.get("days") or []
            # Normalize 3-letter names if needed
            norm_days = []
            for dn in day_names:
                d3 = (dn or "")[:3].title()
                if d3 in ("Mon","Tue","Wed","Thu","Fri","Sat","Sun"):
                    norm_days.append(d3)
            # If empty, assume all days
            if not norm_days:
                norm_days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
            for wd in norm_days:
                pref_shift_bonus[(nid, shift, wd)] = float(w)

        # preferred days off: (nid, date)->rank
        for p in prefs.get("preferred_days_off", []) or []:
            d = p.get("date")
            if d:
                try:
                    rank = float(p.get("rank", 1))
                except Exception:
                    rank = 1.0
                pref_dayoff_penalty[(nid, d)] = rank

    # weights
    pol = cfg.get("policy_parameters", {}) or {}
    w_in = (pol.get("weights") or {}) if isinstance(pol.get("weights"), dict) else {}
    weights = {
        "pref_shift_weight":  float(w_in.get("preferred_shift_satisfaction", w_in.get("pref_shift_weight", 1.0))),
        "pref_dayoff_weight": float(w_in.get("preferred_dayoff_satisfaction", w_in.get("pref_dayoff_weight", 1.0))),
        "shortfall_penalty":  float(w_in.get("shortfall_penalty", 1000.0)),
        "overage_penalty":    float(w_in.get("overage_penalty", 1000.0)),
    }

    return {
        "nurses": nurses,
        "dates": dates,
        "shifts": shifts,
        "coverage": coverage,
        "preferred_shift_bonus": pref_shift_bonus,
        "preferred_dayoff_penalty": pref_dayoff_penalty,
        "weights": weights,
        "no_consec_nights": bool(pol.get("no_consecutive_nights", True)),
    }
