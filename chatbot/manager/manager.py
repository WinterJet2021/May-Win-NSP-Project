# manager.py
# Only for temporary use
import json
import requests
from datetime import datetime
from pathlib import Path


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


if __name__ == "__main__":
    # Example configuration — edit these as needed
    WEBHOOK_URL = "https://rosalinda-asterismal-ollie.ngrok-free.dev/export_all"  # Flask must be running
    REFERENCE_FILE = Path("synthetic_schedule_2026-06_30nurses_allER.json")
    OUTPUT_FILE = Path(f"manager_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

    try:
        build_manager_output(WEBHOOK_URL, REFERENCE_FILE, OUTPUT_FILE)
    except Exception as e:
        print(f"[ERROR] {e}")
