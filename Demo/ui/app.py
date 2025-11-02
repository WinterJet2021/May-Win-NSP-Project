from __future__ import annotations
# UI_IMPORT_SHIM
import os, sys
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from main.normalize_module import normalize_nsp_json
except Exception:
    MAIN_DIR = os.path.join(PROJECT_ROOT, 'main')
    if MAIN_DIR not in sys.path:
        sys.path.insert(0, MAIN_DIR)
    from normalize_module import normalize_nsp_json


# =========================
# Path shims & safe imports
# =========================
import os, sys, json, traceback, tempfile, threading, time, re, urllib.request, urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))  # .../Demo
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# First try proper package imports: Demo/main is a package (has __init__.py)
try:
    from main.normalize_module import normalize_nsp_json
    from main.gurobi_solver import solve_from_cfg_gurobi
    from main.main import ensure_date_horizon, save_csv
    print("[ui] imports: package-style (main.**)")
except Exception:
    # Fallback: direct path injection to .../Demo/main
    MAIN_DIR = os.path.join(PROJECT_ROOT, "main")
    if MAIN_DIR not in sys.path:
        sys.path.insert(0, MAIN_DIR)
    try:
        from main.normalize_module import normalize_nsp_json
        from main.gurobi_solver import solve_from_cfg_gurobi
        from main import ensure_date_horizon, save_csv  # this is main/main.py
        print("[ui] imports: sys.path fallback into /main")
    except Exception:
        # Last-resort: load files explicitly
        import importlib.util

        def _load(name: str, path: str):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore[attr-defined]
            return mod

        nm = _load("normalize_module", os.path.join(MAIN_DIR, "normalize_module.py"))
        sm = _load("gurobi_solver",  os.path.join(MAIN_DIR, "gurobi_solver.py"))
        mm = _load("main",           os.path.join(MAIN_DIR, "main.py"))
        normalize_nsp_json = nm.normalize_nsp_json
        solve_from_cfg_gurobi = sm.solve_from_cfg_gurobi
        ensure_date_horizon = mm.ensure_date_horizon
        save_csv = mm.save_csv
        print("[ui] imports: file-loader fallback")

# ================
# Flask application
# ================
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB

# ---------------
# In-memory state
# ---------------
last_solution: Optional[Dict[str, Any]] = None
last_diagnostics: Optional[Dict[str, Any]] = None
is_solving: bool = False
solve_progress: Dict[str, Any] = {"status": "idle", "message": "", "percent": 0}

PARENT_DIR = PROJECT_ROOT               # .../Demo
OUT_DIR = Path(PARENT_DIR) / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===========================
# Helper: canonicalize shifts
# ===========================
def _canonicalize_shifts(cfg: Dict[str, Any]) -> None:
    """Force shift codes to M/A/N (accept D->M, E->A)."""
    code_map = {"D": "M", "E": "A", "M": "M", "A": "A", "N": "N"}
    # shift_types
    seen = set()
    new_types: List[Dict[str, str]] = []
    for s in cfg.get("shift_types", []):
        c = code_map.get(s.get("code"))
        if c and c not in seen:
            new_types.append({"code": c})
            seen.add(c)
    if not new_types:
        new_types = [{"code": "M"}, {"code": "A"}, {"code": "N"}]
    cfg["shift_types"] = new_types
    # coverage
    for c in cfg.get("coverage_requirements", []):
        if "shift" in c:
            c["shift"] = code_map.get(c["shift"], c["shift"])

def _dates_from_horizon(cfg: Dict[str, Any]) -> List[str]:
    start = datetime.strptime(cfg["date_horizon"]["start"], "%Y-%m-%d")
    end   = datetime.strptime(cfg["date_horizon"]["end"],   "%Y-%m-%d")
    days = (end - start).days + 1
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]

def _build_sample16_payload() -> Dict[str, Any]:
    """Deterministic 16-nurse config, 7-day horizon, M/A/N, minimal prefs."""
    start = datetime(2025, 11, 2).date()
    dates = [(start + timedelta(days=i)).isoformat() for i in range(7)]

    nurses = [{
        "id": f"N{idx:03}",
        "name": f"Nurse {idx}",
        "level": 1 + (idx % 3),
        "employment_type": "full_time",
        "unit": "ER",
        "preferences": {"preferred_shifts": [], "preferred_days_off": []},
    } for idx in range(1, 17)]

    coverage = []
    for d in dates:
        coverage += [
            {"date": d, "shift": "M", "req_total": 2},
            {"date": d, "shift": "A", "req_total": 2},
            {"date": d, "shift": "N", "req_total": 1},
        ]

    return {
        "nurses": nurses,
        "shift_types": [{"code": "M"}, {"code": "A"}, {"code": "N"}],
        "coverage_requirements": coverage,
        "date_horizon": {"start": dates[0], "end": dates[-1]},
        "policy_parameters": {
            "weights": {
                "pref_shift_weight": 1.0,
                "pref_dayoff_weight": 1.0,
                "shortfall_penalty": 1000,
                "overage_penalty": 1000,
            },
            "no_consecutive_nights": True,
            "WSMin": 0,
            "WSMax": 9999,
            "head_nurse_id": None,
        },
    }

# ==================
# Static & meta routes
# ==================
@app.route("/meta.json")
def meta():
    return jsonify({
        "name": "MayWin Nurse Scheduler",
        "version": "demo-ui-1.5",
        "server_time": datetime.utcnow().isoformat() + "Z",
    })

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def serve_file(path):
    return send_from_directory(".", path)

# ===============
# Data I/O routes
# ===============
@app.route("/api/sample")
def get_sample():
    """Always return 16-nurse dataset."""
    try:
        cfg = _build_sample16_payload()
        ensure_date_horizon(cfg)       # fills if missing
        _canonicalize_shifts(cfg)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w+", encoding="utf-8") as tmp:
            json.dump(cfg, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        return jsonify({
            "ok": True,
            "message": "Sample data generated (16 nurses)",
            "file_path": tmp_path,
            "nurses": len(cfg["nurses"]),
            "coverage_requirements": len(cfg["coverage_requirements"]),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file part"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "No file selected"}), 400
    if not f.filename.endswith(".json"):
        return jsonify({"ok": False, "error": "Only JSON files are supported"}), 400
    try:
        cfg = json.loads(f.read().decode("utf-8"))
        ensure_date_horizon(cfg)
        _canonicalize_shifts(cfg)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w+", encoding="utf-8") as tmp:
            json.dump(cfg, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        return jsonify({
            "ok": True,
            "message": "File uploaded successfully",
            "file_path": tmp_path,
            "nurses": len(cfg.get("nurses", [])),
            "coverage_requirements": len(cfg.get("coverage_requirements", [])),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ===============
# Solver endpoints
# ===============
@app.route("/api/solve", methods=["POST"])
def solve_schedule():
    """
    Start solve. Accepts either:
      - {"file_path": "...", "time_limit": 60, "threads": 8}
      - {"cfg": { ...config json... }, "time_limit": 60, "threads": 8}
    """
    global is_solving, solve_progress
    if is_solving:
        return jsonify({"ok": False, "error": "Another optimization is already running"}), 409

    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")
    cfg = data.get("cfg")
    time_limit = int(data.get("time_limit", 60))
    threads    = int(data.get("threads", 8))

    try:
        if cfg is None:
            if not file_path:
                return jsonify({"ok": False, "error": "Provide either 'file_path' or 'cfg' in JSON body"}), 400
            with open(file_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

        # Normalize
        ensure_date_horizon(cfg)
        _canonicalize_shifts(cfg)

        # Launch thread
        is_solving = True
        solve_progress = {"status": "running", "message": "Normalizing data...", "percent": 10}
        t = threading.Thread(target=_run_solver_thread, args=(cfg, time_limit, threads), daemon=True)
        t.start()
        return jsonify({"ok": True, "message": "Optimization started", "status": "running"})
    except Exception as e:
        is_solving = False
        solve_progress = {"status": "error", "message": str(e), "percent": 0}
        return jsonify({"ok": False, "error": str(e)}), 500

def _run_solver_thread(cfg: Dict[str, Any], time_limit: int, threads: int):
    global last_solution, last_diagnostics, is_solving, solve_progress
    try:
        solve_progress = {"status": "running", "message": "Setting up Gurobi model...", "percent": 25}
        time.sleep(0.05)

        result = solve_from_cfg_gurobi(cfg, normalize_nsp_json, time_limit_sec=time_limit, threads=threads)

        # result can be (assignments, shortfall, obj) or (..., diagnostics)
        if not isinstance(result, tuple) or len(result) not in (3, 4):
            raise RuntimeError("Unexpected solver return signature")

        if len(result) == 3:
            assignments, shortfall, obj_val = result
            diagnostics = {}
        else:
            assignments, shortfall, obj_val, diagnostics = result or ({}, {}, None, {})

        # Finalize artifacts
        solve_progress = {"status": "running", "message": "Processing results...", "percent": 90}

        # Persist CSVs
        save_csv(OUT_DIR / "assignments.csv", assignments, ["date", "shift", "nurse_id"])
        save_csv(OUT_DIR / "shortfalls.csv", shortfall,     ["date", "shift", "unmet"])

        dates  = _dates_from_horizon(cfg)
        shifts = [s["code"] for s in cfg.get("shift_types", [])]

        last_diagnostics = diagnostics or {}
        last_solution = {
            "nurses": cfg.get("nurses", []),
            "shifts": shifts,
            "dates": dates,
            "coverage": cfg.get("coverage_requirements", []),
            "assignments": assignments,
            "shortfall": shortfall,
            "objective": obj_val,
            "diagnostics": last_diagnostics,
        }

        # If nothing assigned and no explicit status, make it obvious to the UI
        if not assignments:
            msg = last_diagnostics.get("status_name") or "No assignments produced. Check feasibility or time limit."
            solve_progress = {"status": "completed", "message": msg, "percent": 100}
        else:
            solve_progress = {"status": "completed", "message": "Optimization completed", "percent": 100}

    except Exception as e:
        solve_progress = {"status": "error", "message": str(e), "percent": 0}
        traceback.print_exc()
    finally:
        is_solving = False

@app.route("/api/status")
def get_status():
    payload = dict(solve_progress)
    if last_diagnostics and payload.get("status") == "completed":
        payload["diagnostics"] = last_diagnostics
    return jsonify(payload)

@app.route("/api/solution")
def get_solution():
    if last_solution is None:
        return jsonify({"ok": False, "error": "No solution available"}), 404
    return jsonify({"ok": True, **last_solution})

# ===========================
# Chatbot proxy (same-origin)
# ===========================
_DEF_CHATBOT_BASE = os.environ.get("CHATBOT_BASE", "http://localhost:8080").rstrip("/")

def _fetch_json(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    url = f"{_DEF_CHATBOT_BASE}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            payload = json.loads(resp.read().decode(charset))
            return payload, resp.getcode(), None
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"error": str(e)}
        return payload, e.code, str(e)
    except Exception as e:
        return {"error": str(e)}, 502, str(e)

# ---- Local demo store so preview updates even if chatbot is down ----
DEMO_DB_PATH = Path(THIS_DIR) / "demo_chatbot_db.json"

def _demo_db_load() -> dict:
    if not DEMO_DB_PATH.exists():
        return {"nurses": []}
    try:
        return json.loads(DEMO_DB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"nurses": []}

def _demo_db_save(db: dict) -> None:
    DEMO_DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def _ensure_nurse(nurses: List[dict], nid: str) -> dict:
    for n in nurses:
        if n.get("id") == nid:
            return n
    nurse = {
        "id": nid, "name": nid, "level": 1, "employment_type": "full_time", "unit": "ER",
        "preferences": {"preferred_shifts": [], "preferred_days_off": []}
    }
    nurses.append(nurse)
    return nurse

def _append_dayoff_local(nurses: list, nid: str, date_iso: str, rank: int):
    nurse = _ensure_nurse(nurses, nid)
    prefs = nurse.setdefault("preferences", {})
    days = prefs.setdefault("preferred_days_off", [])
    for d in days:
        if d.get("date") == date_iso:
            d["rank"] = rank
            return
    days.append({"date": date_iso, "rank": rank})

def _append_shiftpref_local(nurses: list, nid: str, shift: str, days_list: List[str], priority: str):
    nurse = _ensure_nurse(nurses, nid)
    prefs = nurse.setdefault("preferences", {})
    arr = prefs.setdefault("preferred_shifts", [])
    arr.append({"shift": shift, "days": days_list, "priority": priority})

def _extract_rank_and_dates(text: str) -> tuple[list[str], int]:
    text = (text or "").strip()
    # rank from “ระดับความสำคัญ 1” / “priority 2”
    m_rank = re.search(r"(ระดับความสำคัญ|priority|rank)\s*[:=]?\s*(\d+)", text, flags=re.IGNORECASE)
    rank = int(m_rank.group(2)) if m_rank else 2
    rank = max(1, min(3, rank))
    # dates: explicit YYYY-MM-DD or bare day number → current month/year
    dates = re.findall(r"(20\d{2}-\d{2}-\d{2})", text)
    if not dates:
        m_day = re.search(r"(\d{1,2})", text)
        if m_day:
            day = int(m_day.group(1))
            now = datetime.now()
            try:
                dates = [f"{now.year:04d}-{now.month:02d}-{day:02d}"]
            except Exception:
                dates = []
    return dates, rank

def _extract_shift_and_days(text: str) -> tuple[str, List[str], str]:
    low = (text or "").lower()
    shift = "M"
    if any(k in low for k in ["เช้า", "morning"]): shift = "M"
    elif any(k in low for k in ["บ่าย", "afternoon", "evening"]): shift = "A"
    elif any(k in low for k in ["กลางคืน", "ดึก", "night"]): shift = "N"
    day_vocab = ["จันทร์","อังคาร","พุธ","พฤหัส","ศุกร์","เสาร์","อาทิตย์",
                 "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
                 "mon","tue","wed","thu","fri","sat","sun"]
    found = [d for d in day_vocab if d in low]
    # normalize to Mon..Sun (keep order)
    day_map = {
        "monday":"Mon","tuesday":"Tue","wednesday":"Wed","thursday":"Thu","friday":"Fri","saturday":"Sat","sunday":"Sun",
        "mon":"Mon","tue":"Tue","wed":"Wed","thu":"Thu","fri":"Fri","sat":"Sat","sun":"Sun",
        "จันทร์":"Mon","อังคาร":"Tue","พุธ":"Wed","พฤหัส":"Thu","ศุกร์":"Fri","เสาร์":"Sat","อาทิตย์":"Sun"
    }
    days = []
    seen = set()
    for token in found:
        canon = day_map.get(token, token.title()[:3])
        if canon not in seen:
            seen.add(canon)
            days.append(canon)
    priority = "high" if "high" in low or "ด่วน" in low or "urgent" in low else "medium"
    return shift, days or ["Mon","Wed","Fri"], priority

# ---- Chatbot endpoints with robust fallbacks ----
@app.route("/api/chatbot/export_all", methods=["GET"])
def chatbot_export_all():
    # Try the real chatbot first
    payload, code, _ = _fetch_json("GET", "/export_all")
    if code == 404:
        payload, code, _ = _fetch_json("GET", "/api/export_all")

    # If reachable & has nurses, normalize to {ok, nurses}
    if 200 <= code < 300 and isinstance(payload, dict):
        nurses = payload.get("nurses")
        if not isinstance(nurses, list):
            nurses = (payload.get("data") or {}).get("nurses")
        if isinstance(nurses, list):
            return jsonify({"ok": True, "nurses": nurses}), 200

    # Fallback to a local tiny JSON store so preview still updates
    db = _demo_db_load()
    return jsonify({"ok": True, "nurses": db.get("nurses", [])}), 200

@app.route("/api/chatbot/dev/resetdb", methods=["POST"])
def chatbot_resetdb():
    for path in ["/dev/resetdb", "/resetdb", "/api/dev/resetdb", "/api/resetdb"]:
        payload, code, err = _fetch_json("POST", path)
        if code != 404:
            if 200 <= code < 300:
                return jsonify({"ok": True, **(payload if isinstance(payload, dict) else {"data": payload})}), code
            return jsonify({"ok": False, **(payload if isinstance(payload, dict) else {"error": err or "error"})}), code

    # Local fallback
    _demo_db_save({"nurses": []})
    return jsonify({"ok": True, "source": "local", "nurses": []}), 200

@app.route("/api/chatbot/dev/callback_test", methods=["POST"])
def chatbot_callback_test():
    body = request.get_json(force=True, silent=True) or {}
    # Try real chatbot first (for dev path and plain path)
    for path in ["/dev/callback_test", "/callback_test", "/api/dev/callback_test", "/api/callback_test"]:
        resp, code, err = _fetch_json("POST", path, body=body)
        if code != 404:
            ok = 200 <= code < 300
            return jsonify({"ok": ok, "endpoint": path, "status_code": code, "data": resp}), code

    # Local fallback: persist to demo_chatbot_db.json so UI preview updates
    text = (body.get("text") or "").strip()
    user_id = body.get("user_id") or "LOCAL_TEST_USER"
    nid = "N001"  # keep simple for local demo; can derive from user if needed

    db = _demo_db_load()
    nurses = db.setdefault("nurses", [])

    # Heuristic: if message mentions leave / day off keywords, treat as day-off; else shift preference
    low = text.lower()
    if any(k in low for k in ["ลางาน", "หยุด", "day off", "leave"]):
        dates, rank = _extract_rank_and_dates(text)
        if not dates:
            now = datetime.now()
            dates = [now.date().isoformat()]
        for d in dates:
            _append_dayoff_local(nurses, nid, d, rank)
        _demo_db_save(db)
        return jsonify({"ok": True, "endpoint": "local_fallback", "intent": "add_day_off",
                        "data": {"nurse_id": nid, "dates": dates, "rank": rank}}), 200
    else:
        shift, days, priority = _extract_shift_and_days(text)
        _append_shiftpref_local(nurses, nid, shift, days, priority)
        _demo_db_save(db)
        return jsonify({"ok": True, "endpoint": "local_fallback", "intent": "add_shift_preference",
                        "data": {"nurse_id": nid, "shift": shift, "days": days, "priority": priority}}), 200

@app.route("/api/chatbot/nlu_predict", methods=["POST"])
def chatbot_nlu_predict():
    """
    Body: { "text": "..." }
    Tries common NLU endpoints on your chatbot service.
    """
    body = request.get_json(force=True, silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Missing 'text'"}), 400

    # Try a set of likely endpoints
    candidates = [
        ("/nlu/predict", {"text": text}),
        ("/api/nlu/predict", {"text": text}),
        ("/nlu", {"text": text}),
        ("/api/nlu", {"text": text}),
    ]
    for path, payload in candidates:
        resp, code, err = _fetch_json("POST", path, body=payload)
        if code != 404:
            return jsonify({"ok": 200 <= code < 300, "endpoint": path, "status_code": code, "data": resp}), code

    return jsonify({"ok": False, "error": "NLU endpoints not found", "tried": [p for p, _ in candidates]}), 502

@app.route("/api/chatbot/simulate_input", methods=["POST"])
def chatbot_simulate_input():
    """
    Body: { "user_id": "U123", "text": "hi" }
    Tries multiple 'simulate input' / 'message' style endpoints; falls back to local persist.
    """
    body = request.get_json(force=True, silent=True) or {}
    user_id = body.get("user_id") or "LOCAL_TEST_USER"
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "Missing 'text'"}), 400

    payload = {"user_id": user_id, "text": text}
    candidates = [
        "/simulate_input", "/api/simulate_input",
        "/message", "/api/message",
        "/chat/say", "/api/chat/say",
    ]
    for path in candidates:
        resp, code, err = _fetch_json("POST", path, body=payload)
        if code != 404:
            return jsonify({"ok": 200 <= code < 300, "endpoint": path, "status_code": code, "data": resp}), code

    # Local fallback to keep the UI workflow useful
    nid = "N001"
    db = _demo_db_load()
    nurses = db.setdefault("nurses", [])
    if any(k in text.lower() for k in ["ลางาน", "หยุด", "day off", "leave"]):
        dates, rank = _extract_rank_and_dates(text)
        if not dates:
            dates = [datetime.now().date().isoformat()]
        for d in dates:
            _append_dayoff_local(nurses, nid, d, rank)
        _demo_db_save(db)
        return jsonify({"ok": True, "endpoint": "local_fallback_simulate", "intent": "add_day_off",
                        "data": {"nurse_id": nid, "dates": dates, "rank": rank}}), 200
    else:
        shift, days, priority = _extract_shift_and_days(text)
        _append_shiftpref_local(nurses, nid, shift, days, priority)
        _demo_db_save(db)
        return jsonify({"ok": True, "endpoint": "local_fallback_simulate", "intent": "add_shift_preference",
                        "data": {"nurse_id": nid, "shift": shift, "days": days, "priority": priority}}), 200

# ==========
# Entrypoint
# ==========
if __name__ == "__main__":
    print("[ui] Starting Flask server...")
    print(f"[ui] Python path[0]: {sys.path[:3]} ...")
    print(f"[ui] CWD: {os.getcwd()}")
    print(f"[ui] PROJECT_ROOT: {PROJECT_ROOT}")
    app.run(debug=True, host="0.0.0.0", port=5000)
