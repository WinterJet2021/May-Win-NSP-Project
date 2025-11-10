# Demo/main/gurobi_solver.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
import gurobipy as gp
from gurobipy import GRB


def solve_from_cfg_gurobi(
    cfg: Dict[str, Any],
    normalizer,
    time_limit_sec: int = 60,
    threads: int = 8,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[float], Dict[str, Any]]:
    """
    Build & solve the nurse scheduling model with SOFT coverage.

    Inputs
    ------
    cfg : dict
        UI / manager / chatbot JSON.
    normalizer : callable
        Function that converts `cfg` into the compact structure the solver expects:
          {
            "nurses": [{ "id": ... }, ...],
            "dates":  ["YYYY-MM-DD", ...],
            "shifts": ["M","A","N"],
            "coverage": [{"date","shift","req_total"}, ...],
            "preferred_shift_bonus": {(nid, shift, "Mon".."Sun"): weight, ...},
            "preferred_dayoff_penalty": {(nid, "YYYY-MM-DD"): rank, ...},
            "weights": {
              "pref_shift_weight": float,
              "pref_dayoff_weight": float,
              "shortfall_penalty": float,
              "overage_penalty": float
            },
            "no_consec_nights": bool
          }

    Returns
    -------
    assignments : List[dict]
        [{"date": str, "shift": "M|A|N", "nurse_id": str}, ...]
    shortfall : List[dict]
        [{"date": str, "shift": "M|A|N", "unmet": float}, ...]
    obj_val : float | None
        Objective value if available.
    diagnostics : dict
        Model status, counts, coverage metrics, etc.
    """
    data = normalizer(cfg)

    # Canonical shifts
    shifts: List[str] = [s for s in data.get("shifts", []) if s in ("M", "A", "N")]
    if not shifts:
        shifts = ["M", "A", "N"]

    nurses: List[str] = [n["id"] for n in data.get("nurses", []) if n.get("id")]
    dates:  List[str] = list(data.get("dates", []))

    # Coverage rows filtered to horizon & known shifts
    coverage_in: List[Dict[str, Any]] = list(data.get("coverage", []))
    coverage: List[Dict[str, Any]] = [
        c for c in coverage_in
        if c.get("date") in dates and c.get("shift") in shifts
    ]

    pref_shift_bonus = data.get("preferred_shift_bonus", {})        # (nid, shift, 'Mon'..'Sun') -> weight
    pref_dayoff_penalty = data.get("preferred_dayoff_penalty", {})  # (nid, 'YYYY-MM-DD') -> rank

    w = data.get("weights", {}) or {}
    pref_shift_weight  = float(w.get("pref_shift_weight", 1.0))
    pref_dayoff_weight = float(w.get("pref_dayoff_weight", 1.0))
    shortfall_pen      = float(w.get("shortfall_penalty", 1000.0))
    overage_pen        = float(w.get("overage_penalty",   1000.0))

    no_consec_nights = bool(data.get("no_consec_nights", True))

    priority_map = {"low": 1.0, "medium": 2.0, "high": 3.0}

    # ----------------
    # Model definition
    # ----------------
    m = gp.Model("nurse_scheduling_soft")
    m.Params.OutputFlag = 1
    m.Params.TimeLimit  = time_limit_sec
    m.Params.Threads    = threads

    # Decision variables
    # x[n, d, s] = 1 if nurse n works shift s on date d
    x = m.addVars(nurses, dates, shifts, vtype=GRB.BINARY, name="x")

    # Soft coverage slack variables:
    # u[d, s] = unmet (shortfall) >= 0
    # o[d, s] = overage (extra)   >= 0
    u = m.addVars(dates, shifts, vtype=GRB.CONTINUOUS, lb=0.0, name="u")
    o = m.addVars(dates, shifts, vtype=GRB.CONTINUOUS, lb=0.0, name="o")

    # Required counts per (date, shift)
    req_map = {(c["date"], c["shift"]): int(c.get("req_total", 0)) for c in coverage}

    # Soft coverage balance: sum_n x[n,d,s] - req = o - u
    for d in dates:
        for s in shifts:
            req = req_map.get((d, s), 0)
            m.addConstr(
                gp.quicksum(x[n, d, s] for n in nurses) - req == o[d, s] - u[d, s],
                name=f"soft_cover_{d}_{s}"
            )

    # At most one shift per nurse per day
    for n in nurses:
        for d in dates:
            m.addConstr(
                gp.quicksum(x[n, d, s] for s in shifts) <= 1,
                name=f"one_shift_per_day_{n}_{d}"
            )

    # No consecutive nights (optional)
    if no_consec_nights and "N" in shifts:
        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i + 1]
            for n in nurses:
                m.addConstr(
                    x[n, d1, "N"] + x[n, d2, "N"] <= 1,
                    name=f"no_consecutive_nights_{n}_{d1}"
                )

    # --------------------
    # Objective definition
    # --------------------
    expr = gp.LinExpr()

    # Preference satisfaction (shift/day-of-week)
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for n in nurses:
        for d in dates:
            try:
                weekday = datetime.strptime(d, "%Y-%m-%d").strftime("%a")
            except Exception:
                # Fallback if date is odd; keep deterministic mapping
                weekday = weekdays[dates.index(d) % 7]

            for s in shifts:
                # Preferred shifts (by weekday)
                key_ps = (n, s, weekday)
                if key_ps in pref_shift_bonus:
                    raw = pref_shift_bonus[key_ps]
                    if isinstance(raw, (int, float)):
                        bonus = float(raw)
                    else:
                        bonus = priority_map.get(str(raw).lower(), 1.0)
                    expr += pref_shift_weight * bonus * x[n, d, s]

                # Day-off penalties
                key_off = (n, d)
                if key_off in pref_dayoff_penalty:
                    try:
                        rank_val = float(pref_dayoff_penalty[key_off])
                    except Exception:
                        rank_val = 1.0
                    expr -= pref_dayoff_weight * rank_val * x[n, d, s]

    # Coverage penalties
    for d in dates:
        for s in shifts:
            expr -= shortfall_pen * u[d, s]
            expr -= overage_pen   * o[d, s]

    m.setObjective(expr, GRB.MAXIMIZE)
    m.optimize()

    # -------------
    # Collect output
    # -------------
    feasible_like = (m.status in (GRB.OPTIMAL, GRB.TIME_LIMIT)) and (getattr(m, "SolCount", 0) > 0)

    assignments: List[Dict[str, Any]] = []
    if feasible_like:
        for n in nurses:
            for d in dates:
                for s in shifts:
                    if x[n, d, s].X > 0.5:
                        assignments.append({"date": d, "shift": s, "nurse_id": n})

    # Shortfall list from u[d, s]
    shortfall: List[Dict[str, Any]] = []
    unmet_total = 0.0
    over_total = 0.0
    if feasible_like:
        for d in dates:
            for s in shifts:
                uval = float(u[d, s].X)
                oval = float(o[d, s].X)
                if uval > 1e-6:
                    shortfall.append({"date": d, "shift": s, "unmet": uval})
                    unmet_total += uval
                if oval > 1e-6:
                    over_total += oval

    obj_val: Optional[float] = None
    if feasible_like:
        try:
            obj_val = float(m.ObjVal)
        except Exception:
            obj_val = None

    demanded = float(sum(req_map.values()))
    diagnostics = {
        "status": int(m.status),
        "status_name": {
            GRB.OPTIMAL: "OPTIMAL",
            GRB.TIME_LIMIT: "TIME_LIMIT",
            GRB.INFEASIBLE: "INFEASIBLE",
            GRB.UNBOUNDED: "UNBOUNDED",
            GRB.CUTOFF: "CUTOFF",
            GRB.SUBOPTIMAL: "SUBOPTIMAL",
            GRB.INF_OR_UNBD: "INF_OR_UNBD",
        }.get(m.status, str(m.status)),
        "solcount": int(getattr(m, "SolCount", 0)),
        "objective": obj_val,
        "coverage_demand": demanded,
        "coverage_unmet": float(unmet_total),
        "coverage_overage": float(over_total),
        "coverage_met_pct": float(0.0 if demanded <= 0 else max(0.0, 100.0 * (1.0 - unmet_total / max(demanded, 1e-9)))),
        "n_nurses": len(nurses),
        "n_dates": len(dates),
        "n_shifts": len(shifts),
    }

    return assignments, shortfall, obj_val, diagnostics