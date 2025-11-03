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
import importlib.util

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

if not os.path.exists(data_dir):
    print_error(f"Data directory not found at {data_dir}")
    print("Creating data directory")
    os.makedirs(data_dir, exist_ok=True)

if not os.path.exists(out_dir):
    print("Creating output directory")
    os.makedirs(out_dir, exist_ok=True)

if not os.path.exists(ui_dir):
    print("Creating UI directory")
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
    import gurobipy
    print_success("Gurobipy is installed")
except ImportError:
    print_error("Gurobipy is not installed")
    print("Please install Gurobi and gurobipy manually from: https://www.gurobi.com/downloads/")
    install_anyway = input("Continue with installation anyway? (y/n): ")
    if install_anyway.lower() != 'y':
        sys.exit(1)

# Function to copy file with user confirmation if it exists
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
        shutil.copy2(source_path, target_path)
        print_success(f"Copied {os.path.basename(source_path)} to {os.path.dirname(target_path)}")
        return True
    except Exception as e:
        print_error(f"Failed to copy {source_path} to {target_path}: {e}")
        return False

# Fix main module imports
print_step("Fixing import issues in main module")

# 1. Create or update __init__.py in main directory
init_path = os.path.join(main_dir, '__init__.py')
init_content = """# This file makes the main directory a proper Python package
# It also exports the key functions to simplify imports

from .normalize_module import normalize_nsp_json
from .gurobi_solver import solve_from_cfg_gurobi
from .main import ensure_date_horizon, save_csv

__all__ = [
    'normalize_nsp_json',
    'solve_from_cfg_gurobi',
    'ensure_date_horizon', 
    'save_csv'
]
"""
with open(init_path, 'w') as f:
    f.write(init_content)
print_success(f"Created/updated {init_path}")

# 2. Fix main.py imports
main_py_path = os.path.join(main_dir, 'main.py')
if os.path.exists(main_py_path):
    with open(main_py_path, 'r') as f:
        main_content = f.read()
    
    # Check if imports need fixing
    if 'from normalize_module import' in main_content:
        # Replace the imports
        main_content = main_content.replace(
            'from normalize_module import normalize_nsp_json',
            'from .normalize_module import normalize_nsp_json'
        )
        main_content = main_content.replace(
            'from gurobi_solver import solve_from_cfg_gurobi',
            'from .gurobi_solver import solve_from_cfg_gurobi'
        )
        
        # Add the special handling for direct script execution
        if '__name__ == "__main__"' in main_content and 'sys.path.append' not in main_content:
            main_content = main_content.replace(
                'if __name__ == "__main__":',
                'if __name__ == "__main__":\n    # For direct execution of this file, add the parent directory to the path\n    import os\n    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))'
            )
        
        # Write the fixed content back
        with open(main_py_path, 'w') as f:
            f.write(main_content)
        print_success(f"Fixed imports in {main_py_path}")
    else:
        print("  Imports in main.py already appear to be fixed")
else:
    print_error(f"{main_py_path} not found")

# Set up the UI
print_step("Setting up the web UI")

# 1. Copy the index.html file
index_html_path = os.path.join(script_dir, 'new_index.html')
if not os.path.exists(index_html_path):
    index_html_path = os.path.join(script_dir, 'nurse_scheduler_ui.html')
copy_file(index_html_path, os.path.join(ui_dir, 'index.html'))

# 2. Copy the app.py file
app_py_path = os.path.join(script_dir, 'app_ultra_robust.py')
if not os.path.exists(app_py_path):
    app_py_path = os.path.join(script_dir, 'integrated_app.py')
    if not os.path.exists(app_py_path):
        app_py_path = os.path.join(script_dir, 'app_for_your_project.py')
copy_file(app_py_path, os.path.join(ui_dir, 'app.py'))

# Set up VS Code settings
print_step("Setting up VS Code configuration")

vscode_dir = os.path.join(project_dir, '.vscode')
if not os.path.exists(vscode_dir):
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
with open(settings_path, 'w') as f:
    f.write(settings_content)
print_success(f"Created VS Code settings at {settings_path}")

# Installation complete
print_header("INSTALLATION COMPLETE")
print("\nThe Nurse Scheduling System has been successfully installed!")
print("\nTo run the web UI:")
print(f"  1. Open a terminal/command prompt")
print(f"  2. Navigate to: {ui_dir}")
print(f"  3. Run: python app.py")
print(f"  4. Open a web browser and go to: http://localhost:5000")

# Ask if the user wants to run the app now
run_now = input("\nWould you like to run the application now? (y/n): ")
if run_now.lower() == 'y':
    print("\nStarting the application...")
    
    # Change to the UI directory
    os.chdir(ui_dir)
    print(f"Working directory: {os.getcwd()}")
    
    # Open browser after a delay
    def open_browser():
        webbrowser.open_new('http://localhost:5000/')
    
    Timer(1.5, open_browser).start()
    
    # Start the Flask server
    print("Starting Flask server...")
    print("Access the application at: http://localhost:5000/")
    print("Press Ctrl+C to stop the server\n")
    os.system("python app.py")