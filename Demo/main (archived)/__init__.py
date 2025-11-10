# This file makes the main directory a proper Python package
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
