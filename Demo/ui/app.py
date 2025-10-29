# Demo/ui/app.py

from flask import Flask, request, jsonify, send_from_directory
import os
import json
import sys
import traceback
from datetime import datetime, timedelta
import tempfile
import threading
import time
from pathlib import Path

# Add the parent directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # Demo directory
sys.path.append(parent_dir)

# Try different import approaches until one works
try:
    # First try approach - direct import from modules
    from main.normalize_module import normalize_nsp_json
    from main.gurobi_solver import solve_from_cfg_gurobi
    # Import helper functions
    from main.main import ensure_date_horizon, save_csv
    print("Successfully imported using package imports")
except ImportError:
    try:
        # Second approach - using sys.path modification
        sys.path.insert(0, os.path.join(parent_dir, 'main'))
        from main.normalize_module import normalize_nsp_json
        from main.gurobi_solver import solve_from_cfg_gurobi
        from main import ensure_date_horizon, save_csv
        print("Successfully imported using sys.path modification")
    except ImportError:
        # Third approach - manual import
        sys.path.insert(0, os.path.join(parent_dir, 'main'))
        import importlib.util
        
        def import_module_from_path(module_name, file_path):
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        
        normalize_module = import_module_from_path("normalize_module", 
                                                os.path.join(parent_dir, 'main', 'normalize_module.py'))
        gurobi_solver = import_module_from_path("gurobi_solver", 
                                             os.path.join(parent_dir, 'main', 'gurobi_solver.py'))
        main_module = import_module_from_path("main", 
                                           os.path.join(parent_dir, 'main', 'main.py'))
        
        normalize_nsp_json = normalize_module.normalize_nsp_json
        solve_from_cfg_gurobi = gurobi_solver.solve_from_cfg_gurobi
        ensure_date_horizon = main_module.ensure_date_horizon
        save_csv = main_module.save_csv
        print("Successfully imported using direct file imports")

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit file uploads to 16MB

# Store the last solution in memory
last_solution = None
is_solving = False
solve_progress = {"status": "idle", "message": "", "percent": 0}

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_file(path):
    return send_from_directory('.', path)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.json'):
        return jsonify({"error": "Only JSON files are supported"}), 400
    
    try:
        # Read JSON data from file
        data = json.loads(file.read().decode('utf-8'))
        
        # Use the ensure_date_horizon function
        ensure_date_horizon(data)
        
        # Store the data in a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w+') as tmp:
            json.dump(data, tmp)
            tmp_path = tmp.name
        
        return jsonify({
            "message": "File uploaded successfully",
            "file_path": tmp_path,
            "nurses": len(data.get("nurses", [])),
            "coverage_requirements": len(data.get("coverage_requirements", []))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/solve', methods=['POST'])
def solve_schedule():
    global last_solution, is_solving, solve_progress
    
    if is_solving:
        return jsonify({"error": "Another optimization is already running"}), 409
    
    data = request.json
    if not data or "file_path" not in data:
        return jsonify({"error": "No file path provided"}), 400
    
    file_path = data["file_path"]
    time_limit = int(data.get("time_limit", 60))
    threads = int(data.get("threads", 8))
    
    try:
        with open(file_path, 'r') as f:
            cfg = json.load(f)
        
        # Start solving in a background thread
        is_solving = True
        solve_progress = {"status": "running", "message": "Starting optimization...", "percent": 0}
        
        thread = threading.Thread(target=run_solver, args=(cfg, time_limit, threads))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "message": "Optimization started",
            "status": "running"
        })
    except Exception as e:
        is_solving = False
        solve_progress = {"status": "error", "message": str(e), "percent": 0}
        return jsonify({"error": str(e)}), 500

def run_solver(cfg, time_limit, threads):
    global last_solution, is_solving, solve_progress
    
    try:
        solve_progress = {"status": "running", "message": "Normalizing data...", "percent": 10}
        time.sleep(0.5)  # Simulated delay
        
        solve_progress = {"status": "running", "message": "Setting up Gurobi model...", "percent": 20}
        time.sleep(0.5)  # Simulated delay
        
        solve_progress = {"status": "running", "message": "Running optimization...", "percent": 30}
        
        # Run the actual solver
        assignments, shortfall, obj_val = solve_from_cfg_gurobi(
            cfg, normalize_nsp_json, time_limit_sec=time_limit, threads=threads
        )
        
        solve_progress = {"status": "running", "message": "Processing results...", "percent": 90}
        
        # Save the results to CSV files in the out directory
        root = Path(parent_dir)
        out_dir = root / "out"
        
        # Save the CSV files
        save_csv(out_dir / "assignments.csv", assignments, ["date", "shift", "nurse_id"])
        save_csv(out_dir / "shortfalls.csv", shortfall, ["date", "shift", "unmet"])
        
        # Format dates for output
        dates = []
        start_date = datetime.strptime(cfg["date_horizon"]["start"], "%Y-%m-%d")
        end_date = datetime.strptime(cfg["date_horizon"]["end"], "%Y-%m-%d")
        num_days = (end_date - start_date).days + 1
        
        for i in range(num_days):
            dates.append((start_date + timedelta(days=i)).strftime("%Y-%m-%d"))
        
        # Prepare output
        last_solution = {
            "nurses": cfg["nurses"],
            "shifts": [s["code"] for s in cfg["shift_types"]],
            "dates": dates,
            "coverage": cfg["coverage_requirements"],
            "assignments": assignments,
            "shortfall": shortfall,
            "objective": obj_val
        }
        
        solve_progress = {"status": "completed", "message": "Optimization completed", "percent": 100}
        
        print(f"\n✓ Solve complete. Objective = {obj_val:.2f}")
        print(f"• Assignments: {len(assignments)}")
        days_with_shortfall = len({(r['date'], r['shift']) for r in shortfall})
        print(f"• Days with shortfall: {days_with_shortfall}\n")
        
        print(f"Files written to: {out_dir}/assignments.csv and shortfalls.csv")
        
    except Exception as e:
        solve_progress = {"status": "error", "message": str(e), "percent": 0}
        print("\n[ERROR] Exception during solve:")
        print(type(e).__name__, str(e))
        traceback.print_exc()
    finally:
        is_solving = False

@app.route('/api/status', methods=['GET'])
def get_status():
    global solve_progress
    return jsonify(solve_progress)

@app.route('/api/solution', methods=['GET'])
def get_solution():
    global last_solution
    
    if last_solution is None:
        return jsonify({"error": "No solution available"}), 404
    
    return jsonify(last_solution)

@app.route('/api/sample', methods=['GET'])
def get_sample():
    """Provides sample data from the nurse_scheduling_dataset.json file"""
    try:
        # Get path to the sample dataset
        root = Path(parent_dir)
        data_path = root / "data" / "nurse_scheduling_dataset.json"
        
        if not data_path.exists():
            return jsonify({"error": f"Sample data file not found: {data_path}"}), 404
        
        with data_path.open("r", encoding="utf-8") as f:
            sample_data = json.load(f)
        
        # Apply ensure_date_horizon as in main.py
        ensure_date_horizon(sample_data)
        
        # Store the data in a temporary file for consistent API
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w+') as tmp:
            json.dump(sample_data, tmp)
            tmp_path = tmp.name
        
        return jsonify({
            "message": "Sample data loaded",
            "file_path": tmp_path,
            "nurses": len(sample_data.get("nurses", [])),
            "coverage_requirements": len(sample_data.get("coverage_requirements", []))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server...")
    print(f"Python path: {sys.path}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Parent directory: {parent_dir}")
    app.run(debug=True, host='0.0.0.0', port=5000)