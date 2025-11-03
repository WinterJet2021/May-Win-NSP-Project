# Demo/main/main.py
from __future__ import annotations
import json, sys, csv, traceback
from pathlib import Path
from typing import Dict, Any, List

# Fix imports to use relative imports
from .normalize_module import normalize_nsp_json
from .gurobi_solver import solve_from_cfg_gurobi

def ensure_date_horizon(cfg: Dict[str, Any]) -> None:
    if "date_horizon" in cfg:
        return
    dates = [row["date"] for row in cfg.get("coverage_requirements", [])]
    if not dates:
        raise ValueError("coverage_requirements is empty and date_horizon missing.")
    cfg["date_horizon"] = {"start": min(dates), "end": max(dates)}

def save_csv(path: Path, rows: List[Dict[str, Any]], header: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})

def main():
    try:
        root = Path(__file__).parents[1]
        in_json = root / "data" / "nurse_scheduling_dataset.json"
        out_dir = root / "out"

        if not in_json.exists():
            print(f"[!] Input JSON not found: {in_json}")
            sys.exit(1)

        with in_json.open("r", encoding="utf-8") as f:
            cfg = json.load(f)

        ensure_date_horizon(cfg)

        assignments, shortfall, obj = solve_from_cfg_gurobi(
            cfg, normalize_nsp_json, time_limit_sec=60, threads=8
        )

        print(f"\n✓ Solve complete. Objective = {obj:.2f}")
        print(f"• Assignments: {len(assignments)}")
        days_with_shortfall = len({(r['date'], r['shift']) for r in shortfall})
        print(f"• Days with shortfall: {days_with_shortfall}\n")

        print("Sample assignments (first 20):")
        for a in assignments[:20]:
            print(f"  {a['date']}  {a['shift']}  -> {a['nurse_id']}")

        save_csv(out_dir / "assignments.csv", assignments, ["date", "shift", "nurse_id"])
        save_csv(out_dir / "shortfalls.csv", shortfall, ["date", "shift", "unmet"])
        print(f"\nFiles written to: {out_dir}\\assignments.csv and shortfalls.csv")

    except Exception as e:
        print("\n[ERROR] Exception during solve:")
        print(type(e).__name__, str(e))
        traceback.print_exc()
        sys.exit(2)

if __name__ == "__main__":
    # For direct execution of this file, add the parent directory to the path
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()