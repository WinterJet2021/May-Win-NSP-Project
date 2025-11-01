# app.py  (FastAPI + OR-Tools CP-SAT, Pydantic v2)
from typing import Dict, List, Optional, Any
from fastapi import FastAPI
from pydantic import BaseModel, Field, model_validator
from ortools.sat.python import cp_model
from datetime import datetime


# ────────────────────────────────
#  DATA MODELS
# ────────────────────────────────
class Weights(BaseModel):
    # Base penalties (strict and relaxed)
    understaff_penalty: int = Field(50, description="Penalty per missing nurse on a shift")
    overtime_penalty: int = Field(10, description="Penalty per extra shift above max for a nurse")
    preference_penalty_multiplier: int = Field(1, description="Multiplier for preference penalties")

    # Extra penalties used by RELAXED pass
    night_morning_penalty: int = Field(100, description="Penalty per Night→Morning violation")
    weekly_night_over_penalty: int = Field(80, description="Penalty per extra night above weekly cap")
    weekly_overwork_penalty: int = Field(60, description="Penalty per extra shift above weekly cap (days off)")
    skill_shortage_penalty: int = Field(80, description="Penalty per missing required 'Senior' per shift")


class SolveRequest(BaseModel):
    nurses: List[str]
    days: List[str]
    shifts: List[str]
    demand: Dict[str, Dict[str, int]]

    # Per-nurse totals (optional)
    min_total_shifts_per_nurse: Optional[Dict[str, int]] = None
    max_total_shifts_per_nurse: Optional[Dict[str, int]] = None
    max_shifts_per_nurse: Optional[Dict[str, int]] = None  # legacy alias used as fallback for max_total_shifts

    # Optionals
    availability: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None  # 1/0 availability by nurse→day→shift
    preferences: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None   # penalty by nurse→day→shift
    nurse_skills: Optional[Dict[str, List[str]]] = None                   # e.g., {"N01":["Senior"], ...}
    required_skills: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None # e.g., {day:{shift:{"Senior":1}}}
    week_index_by_day: Optional[Dict[str, int]] = None                    # maps dates to week buckets (0..)
    weights: Optional[Weights] = None

    @model_validator(mode="after")
    def check_demand(self):
        for d in self.days:
            if d not in self.demand:
                raise ValueError(f"Demand missing for day '{d}'.")
            for s in self.shifts:
                if s not in self.demand[d]:
                    raise ValueError(f"Demand missing for day '{d}', shift '{s}'.")
        return self


class Assignment(BaseModel):
    day: str
    shift: str
    nurse: str


class UnderstaffItem(BaseModel):
    day: str
    shift: str
    missing: int


class NurseStats(BaseModel):
    nurse: str
    assigned_shifts: int
    overtime: int
    nights: int


class SolveResponse(BaseModel):
    status: str
    objective_value: Optional[int] = None
    assignments: List[Assignment] = []
    understaffed: List[UnderstaffItem] = []
    nurse_stats: List[NurseStats] = []
    details: Optional[Dict[str, Any]] = None


# ────────────────────────────────
#  FASTAPI APP
# ────────────────────────────────
app = FastAPI(
    title="Nurse Scheduling API",
    description="Schedules nurses with coverage, Senior requirement, night limits, and rest constraints.",
    version="2.0.0",
)


# ────────────────────────────────
#  HELPERS
# ────────────────────────────────
def get_pref_penalty(prefs, nurse, day, shift) -> int:
    if not prefs:
        return 0
    return int(prefs.get(nurse, {}).get(day, {}).get(shift, 0))


def is_available(avail, nurse, day, shift) -> bool:
    if not avail:
        return True
    return bool(avail.get(nurse, {}).get(day, {}).get(shift, 1))


def is_iso_date(s: str) -> bool:
    try:
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


def get_week_index_map(days: List[str], explicit_map: Optional[Dict[str, int]]) -> Dict[str, int]:
    if explicit_map:
        return dict(explicit_map)
    if all(is_iso_date(d) for d in days):
        iso_weeks = [datetime.fromisoformat(d).isocalendar()[1] for d in days]
        uniq_sorted = {w: i for i, w in enumerate(dict.fromkeys(iso_weeks))}
        return {d: uniq_sorted[datetime.fromisoformat(d).isocalendar()[1]] for d in days}
    # fallback: every 7 days is a new week bucket
    return {d: i // 7 for i, d in enumerate(days)}


def shift_eq(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


# ────────────────────────────────
#  CORE SOLVER ENDPOINT
# ────────────────────────────────
@app.post("/solve", response_model=SolveResponse)
def solve(req: SolveRequest) -> SolveResponse:
    nurses, days, shifts = req.nurses, req.days, req.shifts
    demand = req.demand
    availability, preferences = req.availability or {}, req.preferences or {}
    nurse_skills, required_skills = req.nurse_skills or {}, req.required_skills or {}
    weights = req.weights or Weights()

    default_upper = len(days)
    per_nurse_min = {n: int((req.min_total_shifts_per_nurse or {}).get(n, 0)) for n in nurses}
    per_nurse_max = {
        n: int((req.max_total_shifts_per_nurse or {}).get(n,
               (req.max_shifts_per_nurse or {}).get(n, default_upper)))
        for n in nurses
    }

    week_idx = get_week_index_map(days, req.week_index_by_day)

    # ========== STRICT MODEL ==========
    model = cp_model.CpModel()
    x = {(n, d, s): model.NewBoolVar(f"x_{n}_{d}_{s}") for n in nurses for d in days for s in shifts}
    under = {(d, s): model.NewIntVar(0, len(nurses), f"under_{d}_{s}") for d in days for s in shifts}
    over = {n: model.NewIntVar(0, len(days) * len(shifts), f"over_{n}") for n in nurses}

    # 1) Coverage (with understaff slack)
    for d in days:
        for s in shifts:
            model.Add(sum(x[(n, d, s)] for n in nurses) + under[(d, s)] == demand[d][s])

    # 2) ≤ 1 shift/day per nurse
    for n in nurses:
        for d in days:
            model.Add(sum(x[(n, d, s)] for s in shifts) <= 1)

    # 3) Availability
    for n in nurses:
        for d in days:
            for s in shifts:
                if not is_available(availability, n, d, s):
                    model.Add(x[(n, d, s)] == 0)

    # 4) Monthly min/max w/ overtime slack
    for n in nurses:
        total = sum(x[(n, d, s)] for d in days for s in shifts)
        model.Add(total - over[n] <= per_nurse_max[n])
        model.Add(total >= per_nurse_min[n])

    # 5) No Night→Morning next day
    if any(shift_eq(s, "night") for s in shifts) and any(shift_eq(s, "morning") for s in shifts):
        night_name = next(s for s in shifts if shift_eq(s, "night"))
        morning_name = next(s for s in shifts if shift_eq(s, "morning"))
        for n in nurses:
            for i in range(len(days) - 1):
                model.Add(x[(n, days[i], night_name)] + x[(n, days[i + 1], morning_name)] <= 1)

    # 6) ≤ 2 Nights per week
    if any(shift_eq(s, "night") for s in shifts):
        night_name = next(s for s in shifts if shift_eq(s, "night"))
        weeks = {}
        for d in days:
            weeks.setdefault(week_idx[d], []).append(d)
        for n in nurses:
            for w, dlist in weeks.items():
                model.Add(sum(x[(n, d, night_name)] for d in dlist) <= 2)

    # 7) ≥ 2 days off per week
    weeks = {}
    for d in days:
        weeks.setdefault(week_idx[d], []).append(d)
    for n in nurses:
        for w, dlist in weeks.items():
            cap = max(0, len(dlist) - 2)  # at most 5 working days/week
            model.Add(sum(sum(x[(n, d, s)] for s in shifts) for d in dlist) <= cap)

    # 8) Senior requirement (hard in strict model)
    # Interpret required_skills as possibly including {"Senior": k}
    for d in days:
        for s in shifts:
            need_senior = int((required_skills.get(d, {}).get(s, {}) or {}).get("Senior", 0))
            if need_senior > 0:
                eligible = [n for n in nurses if "Senior" in (nurse_skills.get(n, []) or [])]
                model.Add(sum(x[(n, d, s)] for n in eligible) >= need_senior)

    # Objective
    terms = []
    for d in days:
        for s in shifts:
            terms.append(weights.understaff_penalty * under[(d, s)])
    for n in nurses:
        terms.append(weights.overtime_penalty * over[n])
    for n in nurses:
        for d in days:
            for s in shifts:
                pen = get_pref_penalty(preferences, n, d, s)
                if pen:
                    terms.append(weights.preference_penalty_multiplier * pen * x[(n, d, s)])
    model.Minimize(sum(terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    solver.parameters.num_search_workers = 8
    result = solver.Solve(model)

    def pack_strict(code):
        assignments, understaffed, stats = [], [], []
        for d in days:
            for s in shifts:
                for n in nurses:
                    if solver.Value(x[(n, d, s)]) == 1:
                        assignments.append(Assignment(day=d, shift=s, nurse=n))
        for d in days:
            for s in shifts:
                miss = solver.Value(under[(d, s)])
                if miss:
                    understaffed.append(UnderstaffItem(day=d, shift=s, missing=int(miss)))
        night_label = next((s for s in shifts if shift_eq(s, "night")), None)
        for n in nurses:
            total = sum(solver.Value(x[(n, d, s)]) for d in days for s in shifts)
            nights = sum(solver.Value(x[(n, d, night_label)]) for d in days) if night_label else 0
            stats.append(NurseStats(
                nurse=n,
                assigned_shifts=int(total),
                overtime=int(solver.Value(over[n])),
                nights=int(nights),
            ))
        return SolveResponse(
            status="OPTIMAL" if code == cp_model.OPTIMAL else "FEASIBLE",
            objective_value=int(solver.ObjectiveValue()),
            assignments=assignments,
            understaffed=understaffed,
            nurse_stats=stats,
            details={
                "best_bound": solver.BestObjectiveBound(),
                "wall_time_sec": solver.WallTime(),
                "conflicts": solver.NumConflicts(),
                "branches": solver.NumBranches(),
            },
        )

    if result in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return pack_strict(result)

    # ========== RELAXED MODEL ==========
    r_model = cp_model.CpModel()
    rx = {(n, d, s): r_model.NewBoolVar(f"rx_{n}_{d}_{s}") for n in nurses for d in days for s in shifts}
    r_under = {(d, s): r_model.NewIntVar(0, len(nurses), f"r_under_{d}_{s}") for d in days for s in shifts}
    r_over = {n: r_model.NewIntVar(0, len(days) * len(shifts), f"r_over_{n}") for n in nurses}

    # coverage (same)
    for d in days:
        for s in shifts:
            r_model.Add(sum(rx[(n, d, s)] for n in nurses) + r_under[(d, s)] == demand[d][s])

    # ≤1 shift/day and availability stay hard
    for n in nurses:
        for d in days:
            r_model.Add(sum(rx[(n, d, s)] for s in shifts) <= 1)
            for s in shifts:
                if not is_available(availability, n, d, s):
                    r_model.Add(rx[(n, d, s)] == 0)

    # monthly max soft via overtime
    for n in nurses:
        total = sum(rx[(n, d, s)] for d in days for s in shifts)
        r_model.Add(total - r_over[n] <= per_nurse_max[n])
        # drop min-total to avoid infeasibility; could be added as soft if needed

    # week buckets
    weeks = {}
    for d in days:
        weeks.setdefault(week_idx[d], []).append(d)

    nm_viol, wn_over, wd_over, skill_short = [], [], [], []

    # Soft Night→Morning
    if any(shift_eq(s, "night") for s in shifts) and any(shift_eq(s, "morning") for s in shifts):
        night_name = next(s for s in shifts if shift_eq(s, "night"))
        morning_name = next(s for s in shifts if shift_eq(s, "morning"))
        for n in nurses:
            for i in range(len(days) - 1):
                v = r_model.NewBoolVar(f"nmviol_{n}_{i}")
                # v == 1 if both night(i) and morning(i+1)
                # Big-M free encoding using implications:
                # v >= rx(n,i,night) + rx(n,i+1,morning) - 1
                r_model.Add(v >= rx[(n, days[i], night_name)] + rx[(n, days[i + 1], morning_name)] - 1)
                nm_viol.append(v)

    # Soft weekly night cap (≤2)
    if any(shift_eq(s, "night") for s in shifts):
        night_name = next(s for s in shifts if shift_eq(s, "night"))
        for n in nurses:
            for w, dlist in weeks.items():
                nights_this = sum(rx[(n, d, night_name)] for d in dlist)
                extra_nights = r_model.NewIntVar(0, len(dlist), f"wn_over_{n}_{w}")
                r_model.Add(nights_this - 2 <= extra_nights)
                wn_over.append(extra_nights)

    # Soft weekly 2-days-off rule
    for n in nurses:
        for w, dlist in weeks.items():
            cap = max(0, len(dlist) - 2)  # at most 5 working days/week
            shifts_this_week = sum(sum(rx[(n, d, s)] for s in shifts) for d in dlist)
            extra_work = r_model.NewIntVar(0, len(dlist), f"wd_over_{n}_{w}")
            r_model.Add(shifts_this_week - cap <= extra_work)
            wd_over.append(extra_work)

    # Soft Senior requirement: allow shortage with penalty
    for d in days:
        for s in shifts:
            need_senior = int((required_skills.get(d, {}).get(s, {}) or {}).get("Senior", 0))
            if need_senior > 0:
                eligible = [n for n in nurses if "Senior" in (nurse_skills.get(n, []) or [])]
                shortage = r_model.NewIntVar(0, need_senior, f"skill_short_{d}_{s}_Senior")
                r_model.Add(sum(rx[(n, d, s)] for n in eligible) + shortage >= need_senior)
                skill_short.append(shortage)

    # Objective (relaxed)
    r_terms = []
    for d in days:
        for s in shifts:
            r_terms.append(weights.understaff_penalty * r_under[(d, s)])
    for n in nurses:
        r_terms.append(weights.overtime_penalty * r_over[n])
    for n in nurses:
        for d in days:
            for s in shifts:
                pen = get_pref_penalty(preferences, n, d, s)
                if pen:
                    r_terms.append(weights.preference_penalty_multiplier * pen * rx[(n, d, s)])
    for v in nm_viol:
        r_terms.append(weights.night_morning_penalty * v)
    for v in wn_over:
        r_terms.append(weights.weekly_night_over_penalty * v)
    for v in wd_over:
        r_terms.append(weights.weekly_overwork_penalty * v)
    for v in skill_short:
        r_terms.append(weights.skill_shortage_penalty * v)

    r_model.Minimize(sum(r_terms))

    r_solver = cp_model.CpSolver()
    r_solver.parameters.max_time_in_seconds = 10.0
    r_solver.parameters.num_search_workers = 8
    r_res = r_solver.Solve(r_model)

    def pack_relaxed():
        assignments, understaffed, stats = [], [], []
        for d in days:
            for s in shifts:
                for n in nurses:
                    if r_solver.Value(rx[(n, d, s)]) == 1:
                        assignments.append(Assignment(day=d, shift=s, nurse=n))
        for d in days:
            for s in shifts:
                miss = r_solver.Value(r_under[(d, s)])
                if miss:
                    understaffed.append(UnderstaffItem(day=d, shift=s, missing=int(miss)))
        night_label = next((s for s in shifts if shift_eq(s, "night")), None)
        for n in nurses:
            total = sum(r_solver.Value(rx[(n, d, s)]) for d in days for s in shifts)
            nights = sum(r_solver.Value(rx[(n, d, night_label)]) for d in days) if night_label else 0
            stats.append(NurseStats(
                nurse=n,
                assigned_shifts=int(total),
                overtime=int(r_solver.Value(r_over[n])),
                nights=int(nights),
            ))
        status = "RELAXED_OPTIMAL" if r_res == cp_model.OPTIMAL else "RELAXED_FEASIBLE"
        return SolveResponse(
            status=status,
            objective_value=int(r_solver.ObjectiveValue()),
            assignments=assignments,
            understaffed=understaffed,
            nurse_stats=stats,
            details={
                "message": "Relaxations applied: soft Night→Morning, weekly limits, Senior requirement; min totals dropped",
                "best_bound": r_solver.BestObjectiveBound(),
                "wall_time_sec": r_solver.WallTime(),
                "conflicts": r_solver.NumConflicts(),
                "branches": r_solver.NumBranches(),
            },
        )

    if r_res in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return pack_relaxed()

    # ========== LAST-RESORT HEURISTIC (always return a table) ==========
    def has_skill(n, skill):
        return skill in (nurse_skills.get(n, []) or [])

    def is_avail(n, d, s):
        return bool((availability.get(n, {}) or {}).get(d, {}).get(s, 1))

    assignments = []
    used = {(n, d): False for n in nurses for d in days}

    for d in days:
        for s in shifts:
            req = demand[d][s]
            # Senior requirement if present
            senior_need = int((required_skills.get(d, {}).get(s, {}) or {}).get("Senior", 0))
            chosen: List[str] = []

            # 1) pick Seniors first
            if senior_need > 0:
                for n in nurses:
                    if len(chosen) >= senior_need:
                        break
                    if is_avail(n, d, s) and not used[(n, d)] and has_skill(n, "Senior"):
                        chosen.append(n)
                        used[(n, d)] = True

            # 2) fill remaining with anyone available
            for n in nurses:
                if len(chosen) >= req:
                    break
                if is_avail(n, d, s) and not used[(n, d)]:
                    chosen.append(n)
                    used[(n, d)] = True

            for n in chosen:
                assignments.append(Assignment(day=d, shift=s, nurse=n))

    # stats and understaffing
    stats_map = {n: {"assigned": 0, "nights": 0} for n in nurses}
    for a in assignments:
        stats_map[a.nurse]["assigned"] += 1
        if shift_eq(a.shift, "night"):
            stats_map[a.nurse]["nights"] += 1
    stats = [
        NurseStats(nurse=n, assigned_shifts=v["assigned"], overtime=0, nights=v["nights"])
        for n, v in stats_map.items()
    ]

    from collections import Counter
    count = Counter((a.day, a.shift) for a in assignments)
    understaffed = []
    for d in days:
        for s in shifts:
            miss = max(0, demand[d][s] - count.get((d, s), 0))
            if miss:
                understaffed.append(UnderstaffItem(day=d, shift=s, missing=miss))

    return SolveResponse(
        status="HEURISTIC",
        objective_value=None,
        assignments=assignments,
        understaffed=understaffed,
        nurse_stats=stats,
        details={"message": "CP-SAT failed even after relaxations; returned greedy heuristic schedule."},
    )