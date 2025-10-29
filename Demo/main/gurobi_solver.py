# Demo/main/gurobi_solver.py
from __future__ import annotations
import gurobipy as gp
from gurobipy import GRB
from typing import Dict, Any, List, Tuple
import math

def solve_from_cfg_gurobi(cfg, normalizer, time_limit_sec=60, threads=8):
    data = normalizer(cfg)
    nurses = [n["id"] for n in data["nurses"]]
    dates = data["dates"]
    shifts = data["shifts"]
    coverage = data["coverage"]

    pref_shift_bonus = data["preferred_shift_bonus"]
    pref_dayoff_penalty = data["preferred_dayoff_penalty"]
    weights = data["weights"]

    # Model setup
    m = gp.Model("nurse_scheduling")
    m.Params.OutputFlag = 1
    m.Params.TimeLimit = time_limit_sec
    m.Params.Threads = threads

    # Binary decision variables
    x = m.addVars(nurses, dates, shifts, vtype=GRB.BINARY, name="x")

    # Coverage requirement
    for cov in coverage:
        d, s, req = cov["date"], cov["shift"], cov["req_total"]
        m.addConstr(gp.quicksum(x[n, d, s] for n in nurses) >= req, f"coverage_{d}_{s}")

    # One shift per nurse per day
    for n in nurses:
        for d in dates:
            m.addConstr(gp.quicksum(x[n, d, s] for s in shifts) <= 1, f"oneshift_{n}_{d}")

    # No consecutive night shifts
    if data["no_consec_nights"]:
        for i in range(len(dates) - 1):
            d1, d2 = dates[i], dates[i + 1]
            for n in nurses:
                m.addConstr(x[n, d1, "N"] + x[n, d2, "N"] <= 1, f"noconsnights_{n}_{d1}")

    # Objective
    expr = gp.LinExpr()

    for n in nurses:
        for d in dates:
            for s in shifts:
                weekday = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][
                    (math.floor((dates.index(d)) % 7))
                ]
                if (n, s, weekday) in pref_shift_bonus:
                    expr += weights["pref_shift_weight"] * x[n, d, s]
                if (n, d) in pref_dayoff_penalty:
                    expr -= weights["pref_dayoff_weight"] * x[n, d, s]

    m.setObjective(expr, GRB.MAXIMIZE)
    m.optimize()

    assignments, shortfall = [], []
    if m.status == GRB.OPTIMAL or m.status == GRB.TIME_LIMIT:
        for n in nurses:
            for d in dates:
                for s in shifts:
                    if x[n, d, s].X > 0.5:
                        assignments.append({"date": d, "shift": s, "nurse_id": n})
        for cov in coverage:
            d, s, req = cov["date"], cov["shift"], cov["req_total"]
            actual = sum(x[n, d, s].X for n in nurses)
            if actual < req:
                shortfall.append({"date": d, "shift": s, "unmet": req - actual})

    return assignments, shortfall, m.objVal
