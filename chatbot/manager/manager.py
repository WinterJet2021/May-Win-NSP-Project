# manager.py 
# Only for temporary use
import os
import json
import requests
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from collections import OrderedDict


def fetch_webhook_json(url: str):
    """Fetch nurse data from Flask webhook endpoint."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        print(f"[INFO] Successfully fetched data from {url}")
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch webhook data: {e}")


def load_reference_json(file_path: Path):
    """Load static reference JSON containing shift_types and policy rules."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================
# Added Section: Local SQLite mode for testing (no ngrok/LINE)
# ===========================================================
def fetch_sqlite_json(db_path: Path) -> dict:
    """Read nurses & preferences directly from SQLite and return the same shape as Flask /export_all."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        nurses_rows = conn.execute(
            "SELECT id, name, level, employment_type, unit FROM nurses"
        ).fetchall()
        prefs_rows = conn.execute(
            "SELECT nurse_id, preference_type, data FROM preferences"
        ).fetchall()

    nurse_dict = {}
    for n in nurses_rows:
        nid = n["id"]
        nurse_dict[nid] = OrderedDict([
            ("id", f"N{nid:03}"),
            ("name", n["name"] or ""),
            ("level", n["level"] if n["level"] is not None else 1),
            ("employment_type", n["employment_type"] or "full_time"),
            ("unit", n["unit"] or "ER"),
            ("preferences", {
                "preferred_shifts": [],
                "preferred_days_off": []
            })
        ])

    for row in prefs_rows:
        nurse_id = row["nurse_id"]
        ptype = row["preference_type"]
        try:
            pdata = json.loads(row["data"]) if row["data"] else {}
        except Exception:
            pdata = {}
        if nurse_id in nurse_dict and ptype in nurse_dict[nurse_id]["preferences"]:
            nurse_dict[nurse_id]["preferences"][ptype].append(pdata)

    sorted_nurses = [nurse_dict[k] for k in sorted(nurse_dict.keys())]
    return {"nurses": sorted_nurses}


def build_manager_output_from_sqlite(sqlite_db_path: Path, reference_json_path: Path, output_path: Path) -> dict:
    """Same output structure as build_manager_output(), but reads nurse data from local SQLite instead of HTTP."""
    base = fetch_sqlite_json(sqlite_db_path)
    ref = load_reference_json(reference_json_path)

    final_json = {
        "nurses": base.get("nurses", []),
        "shift_types": ref.get("shift_types", []),
        "coverage_requirements": ref.get("coverage_requirements", []),
        "policy_parameters": ref.get("policy_parameters", {}),
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"[✅] Manager output (sqlite) saved to {output_path}")
    return final_json
# ===========================================================


def build_manager_output(webhook_url: str, reference_json_path: Path, output_path: Path):
    """Merge webhook JSON with reference schedule template."""
    webhook_data = fetch_webhook_json(webhook_url)
    ref_data = load_reference_json(reference_json_path)

    final_json = {
        "nurses": webhook_data.get("nurses", []),
        "shift_types": ref_data.get("shift_types", []),
        "coverage_requirements": ref_data.get("coverage_requirements", []),
        "policy_parameters": ref_data.get("policy_parameters", {}),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"[✅] Manager output saved to {output_path}")
    return final_json


# ===========================================================
# Added Section: Combined mock + database demo mode + normalization
# ===========================================================
def build_manager_output_mock_with_db(sqlite_db_path: Path, reference_json_path: Path, output_path: Path) -> dict:
    """Generate 14 mock nurses + 1 real nurse from database with normalized format."""
    import random

    # Load 1 nurse from DB (if available)
    try:
        db_data = fetch_sqlite_json(sqlite_db_path)
        db_nurses = db_data.get("nurses", [])
        db_nurse = db_nurses[0] if db_nurses else None
        print(f"[INFO] Loaded {len(db_nurses)} nurses from database.")
    except Exception as e:
        print(f"[WARN] Could not read DB nurse: {e}")
        db_nurse = None

    # Generate 14 mock nurses
    mock_nurses = []
    for i in range(1, 15):
        mock_nurses.append({
            "id": f"N{i:03}",
            "name": f"Nurse {i}",
            "level": 1 if i <= 8 else 2,
            "employment_type": "full_time",
            "unit": "ER",
            "preferences": {
                "preferred_shifts": [
                    {
                        "shift": random.choice(["M", "A", "N"]),
                        "days": random.sample(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], k=random.randint(3, 5)),
                        "priority": random.choice(["low", "medium", "high"])
                    }
                ],
                "preferred_days_off": [
                    {"date": f"2025-11-{d:02}", "rank": random.randint(1, 3)}
                    for d in sorted(random.sample(range(1, 29), k=random.randint(3, 4)))
                ]
            }
        })

    # Merge DB nurse as last entry
    all_nurses = mock_nurses
    if db_nurse:
        db_nurse["id"] = "N015"
        all_nurses.append(db_nurse)
    else:
        all_nurses.append({
            "id": "N015",
            "name": "Nurse 15 (DB Placeholder)",
            "level": 2,
            "employment_type": "full_time",
            "unit": "ER",
            "preferences": {"preferred_shifts": [], "preferred_days_off": []}
        })

    # Generate default reference if missing
    if reference_json_path is None or not Path(reference_json_path).exists():
        print("[WARN] Reference file not found, using built-in defaults for shift_types and policy.")
        ref = {
            "shift_types": [
                {"code": "M", "name": "Morning", "start": "08:00", "end": "16:00"},
                {"code": "A", "name": "Afternoon", "start": "16:00", "end": "24:00"},
                {"code": "N", "name": "Night", "start": "00:00", "end": "08:00"}
            ],
            "policy_parameters": {
                "no_consecutive_nights": True,
                "min_rest_hours_between_shifts": 11,
                "weights": {
                    "workload_fairness": 1.0,
                    "preferred_shift_satisfaction": 0.8,
                    "preferred_dayoff_satisfaction": 1.2
                }
            }
        }
    else:
        ref = load_reference_json(reference_json_path)

    # === Auto-generate coverage requirements ===
    start_date = datetime(2025, 11, 1)
    num_days = 28
    shifts = ["M", "A", "N"]
    coverage_requirements = []
    for i in range(num_days):
        current_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        for s in shifts:
            coverage_requirements.append({
                "date": current_date,
                "shift": s,
                "req_total": 6 if s in ["M", "A"] else 2
            })

    final_json = {
        "nurses": all_nurses,
        "shift_types": ref.get("shift_types", []),
        "coverage_requirements": coverage_requirements,
        "policy_parameters": ref.get("policy_parameters", {}),
    }

    # Save final normalized output
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"[✅] Normalized manager output (mock + DB) saved to {output_path}")
    return final_json
# ===========================================================


if __name__ == "__main__":
    WEBHOOK_URL = "https://rosalinda-asterismal-ollie.ngrok-free.dev/export_all"
    REFERENCE_FILE = Path("synthetic_schedule_2026-06_30nurses_allER.json")
    if not REFERENCE_FILE.exists():
        print("[WARN] Reference file not found, will use built-in defaults.")
        REFERENCE_FILE = None

    OUTPUT_FILE = Path(f"manager_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    source = os.getenv("MANAGER_SOURCE", "sqlite").lower()
    sqlite_db = Path(os.getenv("MANAGER_DB", "nurse_prefs.db"))

    try:
        if source == "sqlite":
            build_manager_output_from_sqlite(sqlite_db, REFERENCE_FILE, OUTPUT_FILE)
        elif source in ("mock", "mock_db"):
            build_manager_output_mock_with_db(sqlite_db, REFERENCE_FILE, OUTPUT_FILE)
        else:
            build_manager_output(WEBHOOK_URL, REFERENCE_FILE, OUTPUT_FILE)
    except Exception as e:
        print(f"[ERROR] {e}")