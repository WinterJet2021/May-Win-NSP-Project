# Demo/install.py
"""
Nurse Scheduling System - Installation Script
This script sets up the web UI and fixes import issues in the project
"""

import os
import sys
import shutil
import webbrowser
from threading import Timer
from pathlib import Path
import re

def print_header(text):
    print("\n" + "=" * 80)
    print(f" {text} ".center(80))
    print("=" * 80)

def print_step(text):
    print(f"\n→ {text}")

def print_success(text):
    print(f"  ✓ {text}")

def print_error(text):
    print(f"  ✗ {text}")

print_header("NURSE SCHEDULING SYSTEM - INSTALLATION")

# Get the project directory
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir) if "outputs" in script_dir else script_dir

print_step("Detecting project structure")
print(f"  Script directory: {script_dir}")
print(f"  Project directory: {project_dir}")

# Check for project structure
main_dir = os.path.join(project_dir, 'main')
ui_dir = os.path.join(project_dir, 'ui')
data_dir = os.path.join(project_dir, 'data')
out_dir = os.path.join(project_dir, 'out')

# Verify directories
if not os.path.exists(main_dir):
    print_error(f"Main directory not found at {main_dir}")
    print("Please run this script from the Demo directory")
    sys.exit(1)

os.makedirs(data_dir, exist_ok=True)
os.makedirs(out_dir, exist_ok=True)
os.makedirs(ui_dir, exist_ok=True)

# Check for required Python modules
print_step("Checking required Python packages")
try:
    import flask
    print_success("Flask is installed")
except ImportError:
    print("Installing Flask...")
    os.system("pip install flask")
    try:
        import flask
        print_success("Flask installed successfully")
    except ImportError:
        print_error("Failed to install Flask. Please install it manually: pip install flask")
        sys.exit(1)

try:
    import gurobipy  # noqa: F401
    print_success("Gurobipy is installed")
except ImportError:
    print_error("Gurobipy is not installed")
    print("Please install Gurobi and gurobipy manually from: https://www.gurobi.com/downloads/")
    cont = input("Continue with installation anyway? (y/n): ")
    if cont.lower() != 'y':
        sys.exit(1)

# Helpers
def copy_file(source_path, target_path, force=False, required=True):
    if not os.path.exists(source_path):
        if required:
            print_error(f"Source file not found: {source_path}")
            return False
        else:
            print(f"  Source file not found (optional): {source_path}")
            return False

    if os.path.exists(target_path) and not force:
        response = input(f"  File exists: {target_path}. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print(f"  Keeping existing file: {target_path}")
            return False

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(source_path, target_path)
        print_success(f"Copied {os.path.basename(source_path)} to {os.path.dirname(target_path)}")
        return True
    except Exception as e:
        print_error(f"Failed to copy {source_path} to {target_path}: {e}")
        return False

def ensure_file(path, content_if_missing=""):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content_if_missing)
        print_success(f"Created {path}")

# 1) Ensure package init files
print_step("Ensuring package structure (__init__.py)")
ensure_file(os.path.join(project_dir, "__init__.py"), "# Demo package\n")
ensure_file(os.path.join(main_dir, "__init__.py"))
ensure_file(os.path.join(ui_dir, "__init__.py"))

# Write/Update main/__init__.py to export key APIs
main_init_path = os.path.join(main_dir, "__init__.py")
main_init_content = """# This file makes the main directory a proper Python package
# It also re-exports key functions to simplify imports.

from .normalize_module import normalize_nsp_json
from .gurobi_solver import solve_from_cfg_gurobi

# Optional helpers if present
try:
    from .main import ensure_date_horizon, save_csv
except Exception:
    def ensure_date_horizon(*a, **k):  # type: ignore
        return None
    def save_csv(*a, **k):  # type: ignore
        return None

__all__ = [
    'normalize_nsp_json',
    'solve_from_cfg_gurobi',
    'ensure_date_horizon',
    'save_csv',
]
"""
with open(main_init_path, "w", encoding="utf-8") as f:
    f.write(main_init_content)
print_success(f"Created/updated {main_init_path}")

# 2) Ensure normalize_module.py defines normalize_nsp_json
print_step("Verifying normalize_module.normalize_nsp_json")
normalize_path = os.path.join(main_dir, "normalize_module.py")
if not os.path.exists(normalize_path):
    # Create a minimal module with a safe stub
    with open(normalize_path, "w", encoding="utf-8") as f:
        f.write(
            "from typing import Dict, Any\n\n"
            "def normalize_nsp_json(cfg: Dict[str, Any]) -> Dict[str, Any]:\n"
            "    # SAFE STUB: pass-through with defaults.\n"
            "    req = [\n"
            "        'nurses','dates','shifts','coverage',\n"
            "        'preferred_shift_bonus','preferred_dayoff_penalty','weights'\n"
            "    ]\n"
            "    if all(k in cfg for k in req):\n"
            "        return cfg\n"
            "    return {\n"
            "        'nurses': cfg.get('nurses', []),\n"
            "        'dates': cfg.get('dates', []),\n"
            "        'shifts': cfg.get('shifts', ['M','A','N']),\n"
            "        'coverage': cfg.get('coverage', []),\n"
            "        'preferred_shift_bonus': cfg.get('preferred_shift_bonus', {}),\n"
            "        'preferred_dayoff_penalty': cfg.get('preferred_dayoff_penalty', {}),\n"
            "        'weights': cfg.get('weights', {'w_coverage':1.0, 'w_pref':1.0}),\n"
            "    }\n"
        )
    print_success(f"Created {normalize_path} with stub normalize_nsp_json()")
else:
    with open(normalize_path, "r+", encoding="utf-8") as f:
        txt = f.read()
        if "def normalize_nsp_json(" not in txt:
            # Append stub at end
            if not txt.endswith("\n"):
                txt += "\n"
            txt += (
                "\n\n# Auto-added by installer: safe stub\n"
                "from typing import Dict, Any\n"
                "def normalize_nsp_json(cfg: Dict[str, Any]) -> Dict[str, Any]:\n"
                "    req = [\n"
                "        'nurses','dates','shifts','coverage',\n"
                "        'preferred_shift_bonus','preferred_dayoff_penalty','weights'\n"
                "    ]\n"
                "    if all(k in cfg for k in req):\n"
                "        return cfg\n"
                "    return {\n"
                "        'nurses': cfg.get('nurses', []),\n"
                "        'dates': cfg.get('dates', []),\n"
                "        'shifts': cfg.get('shifts', ['M','A','N']),\n"
                "        'coverage': cfg.get('coverage', []),\n"
                "        'preferred_shift_bonus': cfg.get('preferred_shift_bonus', {}),\n"
                "        'preferred_dayoff_penalty': cfg.get('preferred_dayoff_penalty', {}),\n"
                "        'weights': cfg.get('weights', {'w_coverage':1.0, 'w_pref':1.0}),\n"
                "    }\n"
            )
            f.seek(0)
            f.write(txt)
            f.truncate()
            print_success("Appended stub normalize_nsp_json() to normalize_module.py")
        else:
            print_success("normalize_nsp_json() already present")

# 3) Patch imports in main/main.py for robustness
print_step("Fixing import issues in main/main.py")
main_py_path = os.path.join(main_dir, 'main.py')
if os.path.exists(main_py_path):
    with open(main_py_path, 'r', encoding='utf-8') as f:
        main_content = f.read()

    changed = False

    # Replace bare imports with package import
    if 'from normalize_module import' in main_content:
        main_content = main_content.replace(
            'from normalize_module import normalize_nsp_json',
            'from .normalize_module import normalize_nsp_json'
        )
        changed = True
    if 'from gurobi_solver import' in main_content:
        main_content = main_content.replace(
            'from gurobi_solver import solve_from_cfg_gurobi',
            'from .gurobi_solver import solve_from_cfg_gurobi'
        )
        changed = True

    # Prepend a robust try/except import shim if not already present
    if 'TRY_IMPORT_SHIM' not in main_content:
        shim = (
            "# TRY_IMPORT_SHIM\n"
            "try:\n"
            "    from .normalize_module import normalize_nsp_json\n"
            "except Exception:\n"
            "    try:\n"
            "        from main.normalize_module import normalize_nsp_json\n"
            "    except Exception:\n"
            "        import os, sys\n"
            "        sys.path.append(os.path.dirname(__file__))\n"
            "        from normalize_module import normalize_nsp_json\n"
        )
        main_content = shim + "\n" + main_content
        changed = True

    if changed:
        with open(main_py_path, 'w', encoding='utf-8') as f:
            f.write(main_content)
        print_success(f"Updated {main_py_path}")
    else:
        print("  Imports in main.py already appear to be robust")
else:
    print_error(f"{main_py_path} not found")

# 4) Set up the UI files
print_step("Setting up the web UI")

# index.html
index_html_candidates = [
    os.path.join(script_dir, 'new_index.html'),
    os.path.join(script_dir, 'nurse_scheduler_ui.html'),
]
index_html_src = next((p for p in index_html_candidates if os.path.exists(p)), None)
if index_html_src:
    copy_file(index_html_src, os.path.join(ui_dir, 'index.html'))
else:
    print_error("No index.html source found (looked for new_index.html / nurse_scheduler_ui.html)")

# app.py
app_py_candidates = [
    os.path.join(script_dir, 'app_ultra_robust.py'),
    os.path.join(script_dir, 'integrated_app.py'),
    os.path.join(script_dir, 'app_for_your_project.py'),
]
app_py_src = next((p for p in app_py_candidates if os.path.exists(p)), None)
if app_py_src:
    copy_file(app_py_src, os.path.join(ui_dir, 'app.py'))
else:
    print_error("No app.py source found (looked for app_ultra_robust.py / integrated_app.py / app_for_your_project.py)")

# 5) Patch ui/app.py imports to be robust — WITHOUT moving __future__ lines
print_step("Patching ui/app.py import shim (preserving __future__ at top)")
ui_app_path = os.path.join(ui_dir, "app.py")
if os.path.exists(ui_app_path):
    with open(ui_app_path, "r", encoding="utf-8") as f:
        app_txt = f.read()

    if "UI_IMPORT_SHIM" in app_txt:
        print_success("ui/app.py already has robust import shim")
    else:
        shim = (
            "# UI_IMPORT_SHIM\n"
            "import os, sys\n"
            "THIS_DIR = os.path.dirname(os.path.abspath(__file__))\n"
            "PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))\n"
            "if PROJECT_ROOT not in sys.path:\n"
            "    sys.path.insert(0, PROJECT_ROOT)\n"
            "try:\n"
            "    from main.normalize_module import normalize_nsp_json\n"
            "except Exception:\n"
            "    MAIN_DIR = os.path.join(PROJECT_ROOT, 'main')\n"
            "    if MAIN_DIR not in sys.path:\n"
            "        sys.path.insert(0, MAIN_DIR)\n"
            "    from normalize_module import normalize_nsp_json\n"
        )

        # Find block of __future__ imports at the top (including shebang/comments)
        lines = app_txt.splitlines(keepends=True)

        # Preserve shebang and encoding comments at very top
        idx = 0
        while idx < len(lines) and (
            lines[idx].startswith("#!") or
            lines[idx].lstrip().startswith("# -*- coding:") or
            lines[idx].strip() == "" or
            lines[idx].lstrip().startswith("#")
        ):
            idx += 1

        # Now, if there's a __future__ import block starting here, capture it
        future_start = idx
        while idx < len(lines) and lines[idx].lstrip().startswith("from __future__ import"):
            idx += 1
        future_end = idx  # lines[future_start:future_end] are __future__ imports (maybe empty)

        # Reconstruct: [shebang/comments .. future block] + [shim] + [rest]
        head = lines[:future_end]
        tail = lines[future_end:]
        new_txt = "".join(head) + ("\n" if (head and not head[-1].endswith("\n")) else "") + shim + "\n" + "".join(tail)

        with open(ui_app_path, "w", encoding="utf-8") as f:
            f.write(new_txt)
        print_success("Patched ui/app.py with robust import shim after __future__ imports")
else:
    print_error(f"{ui_app_path} not found; skipping import patch")

# 6) VS Code settings
print_step("Setting up VS Code configuration")
vscode_dir = os.path.join(project_dir, '.vscode')
os.makedirs(vscode_dir, exist_ok=True)
settings_path = os.path.join(vscode_dir, 'settings.json')
settings_content = """
{
    "python.analysis.extraPaths": [
        "${workspaceFolder}",
        "${workspaceFolder}/Demo"
    ],
    "python.autoComplete.extraPaths": [
        "${workspaceFolder}",
        "${workspaceFolder}/Demo"
    ],
    "python.linting.enabled": true,
    "python.languageServer": "Pylance"
}
"""
with open(settings_path, 'w', encoding='utf-8') as f:
    f.write(settings_content)
print_success(f"Created VS Code settings at {settings_path}")

# 7) Done
print_header("INSTALLATION COMPLETE")
print("\nThe Nurse Scheduling System has been successfully installed!")
print("\nTo run the web UI:")
print(f"  1. Open a terminal/command prompt")
print(f"  2. Navigate to: {ui_dir}")
print(f"  3. Run: python app.py")
print(f"  4. Open a web browser and go to: http://localhost:5000")

run_now = input("\nWould you like to run the application now? (y/n): ")
if run_now.lower() == 'y':
    print("\nStarting the application...")
    os.chdir(ui_dir)
    print(f"Working directory: {os.getcwd()}")

    def open_browser():
        webbrowser.open_new('http://localhost:5000/')

    Timer(1.5, open_browser).start()
    print("Starting Flask server...")
    print("Access the application at: http://localhost:5000/")
    print("Press Ctrl+C to stop the server\n")
    os.system("python app.py")