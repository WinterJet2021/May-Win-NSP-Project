# Demo/main/gurobi_solver.py
from __future__ import annotations
import gurobipy as gp
from gurobipy import GRB
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta

def _rest_minutes_between(shift1: Dict[str,int], shift2: Dict[str,int]) -> int:
    """
    Rest between end of shift1 on day d and start of shift2 on day d+1.
    Handles overnight shifts where end < start (wrap to next day).
    Return rest minutes (>=0).
    """
    s1_start = shift1["start_min"]
    s1_end   = shift1["end_min"]
    s2_start = shift2["start_min"]

    # end datetime of shift1: if end <= start -> overnight, so +24h
    if s1_end <= s1_start:
        end1 = s1_end + 24*60
    else:
        end1 = s1_end

    # start of next day's shift2 is +24h offset from "today" reference
    start2 = s2_start + 24*60

    return start2 - end1  # minutes

def solve_from_cfg_gurobi(cfg, normalizer, time_limit_sec=60, threads=8):
    data = normalizer(cfg)

    nurses: List[str] = [n["id"] for n in data["nurses"]]
    dates:  List[str] = data["dates"]
    shifts: List[str] = data["shifts"]
    shift_types       = data["shift_types"]          # with start_min/end_min
    coverage_rows     = data["coverage_rows"]
    coverage_map      = data["coverage"]

    pref_shift_bonus  = data["pref_shift_bonus"]
    pref_dayoff_wt    = data["pref_dayoff_weight"]
    W                 = data["weights"]
    min_rest_h        = data["min_rest_hours"]
    min_rest_min      = int(min_rest_h * 60)
    no_consec_nights  = data["no_consec_nights"]

    m = gp.Model("nurse_scheduling")
    m.Params.OutputFlag = 1
    m.Params.TimeLimit  = time_limit_sec
    m.Params.Threads    = threads

    # Decision vars: assign nurse n on date d to shift s
    x = m.addVars(nurses, dates, shifts, vtype=GRB.BINARY, name="x")

    # Slack vars to allow equality while staying solvable (heavily penalized)
    u = m.addVars(dates, shifts, lb=0.0, name="under")  # unmet
    v = m.addVars(dates, shifts, lb=0.0, name="over")   # extra

    # Coverage equality with slack: sum_n x = req + u - v
    for d, sreq in coverage_map.keys():
        pass  # dummy to allow unpack below (we already have rows)

    for row in coverage_rows:
        d, s, req = row["date"], row["shift"], row["req_total"]
        m.addConstr(gp.quicksum(x[n, d, s] for n in nurses) + u[d, s] - v[d, s] == req,
                    name=f"cov_eq_{d}_{s}")

    # One shift per nurse per day
    for n in nurses:
        for d in dates:
            m.addConstr(gp.quicksum(x[n, d, s] for s in shifts) <= 1, name=f"oneshift_{n}_{d}")

    # No consecutive nights (optional hard rule)
    if no_consec_nights and "N" in shifts:
        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i+1]
            for n in nurses:
                m.addConstr(x[n, d1, "N"] + x[n, d2, "N"] <= 1, name=f"noconsN_{n}_{d1}")

    # Min rest across days: forbid pairs (s1 on d, s2 on d+1) if rest < threshold
    for i in range(len(dates) - 1):
        d1, d2 = dates[i], dates[i+1]
        for s1 in shifts:
            for s2 in shifts:
                rest = _rest_minutes_between(shift_types[s1], shift_types[s2])
                if rest < min_rest_min:
                    for n in nurses:
                        m.addConstr(x[n, d1, s1] + x[n, d2, s2] <= 1,
                                    name=f"rest_{n}_{d1}_{s1}_{s2}")

    # Objective: maximize preferences – penalties for slack (understaff heavy, overstaff strong)
    obj = gp.LinExpr()

    for n in nurses:
        for d in dates:
            for s in shifts:
                if (n, d, s) in pref_shift_bonus:
                    obj += W["pref_shift"] * x[n, d, s]
                if (n, d) in pref_dayoff_wt:
                    # dayoff weight discourages assigning on that date
                    obj -= W["pref_dayoff"] * pref_dayoff_wt[(n, d)] * x[n, d, s]

    # Penalties for slack
    for d in dates:
        for s in shifts:
            obj -= W["understaff_pen"] * u[d, s]
            obj -= W["overstaff_pen"]  * v[d, s]

    m.setObjective(obj, GRB.MAXIMIZE)
    m.optimize()

    # Extract solution
    assignments: List[Dict[str,Any]] = []
    shortfall:  List[Dict[str,Any]] = []

    if m.status in (GRB.OPTIMAL, GRB.TIME_LIMIT):
        for n in nurses:
            for d in dates:
                for s in shifts:
                    if x[n, d, s].X > 0.5:
                        assignments.append({"date": d, "shift": s, "nurse_id": n})
        for row in coverage_rows:
            d, s, req = row["date"], row["shift"], row["req_total"]
            uval = u[d, s].X
            vval = v[d, s].X
            if uval > 1e-6:
                shortfall.append({"date": d, "shift": s, "unmet": round(uval, 2)})
            # If you want a separate overstaff report, you can add it similarly.

    return assignments, shortfall, m.objVal
