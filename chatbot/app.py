import os
import json
import sqlite3
import re
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv, find_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# ---------------------------
# Environment Setup
# ---------------------------
env_path = find_dotenv()
print(f"Loading environment from: {env_path}")
load_dotenv(env_path)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
RASA_URL = os.getenv("RASA_URL", "http://localhost:5005/model/parse")
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "nurse.db"))

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

app = Flask(__name__)

# ---------------------------
# Database Setup
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Table: nurses (main profile)
    c.execute("""
    CREATE TABLE IF NOT EXISTS nurses (
        id TEXT PRIMARY KEY,
        name TEXT,
        level INTEGER,
        employment_type TEXT,
        unit TEXT,
        skills TEXT,
        shifts_per_month INTEGER
    )
    """)

    # Table: preferences (per-message extracted data)
    c.execute("""
    CREATE TABLE IF NOT EXISTS preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nurse_id TEXT,
        preference_type TEXT,
        data TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()
print(f"Database initialized at: {DB_PATH}")

# ---------------------------
# DB Helpers
# ---------------------------
def upsert_nurse(nurse_id, name=None, level=None, employment_type=None, unit=None, skills=None, shifts_per_month=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    exists = c.execute("SELECT 1 FROM nurses WHERE id = ?", (nurse_id,)).fetchone()

    if exists:
        updates, params = [], []
        if name: updates.append("name = ?"); params.append(name)
        if level: updates.append("level = ?"); params.append(level)
        if employment_type: updates.append("employment_type = ?"); params.append(employment_type)
        if unit: updates.append("unit = ?"); params.append(unit)
        if skills: updates.append("skills = ?"); params.append(json.dumps(skills))
        if shifts_per_month: updates.append("shifts_per_month = ?"); params.append(shifts_per_month)
        if updates:
            params.append(nurse_id)
            c.execute(f"UPDATE nurses SET {', '.join(updates)} WHERE id = ?", params)
    else:
        c.execute(
            "INSERT INTO nurses (id, name, level, employment_type, unit, skills, shifts_per_month) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nurse_id, name or "", level, employment_type or "", unit or "", json.dumps(skills or []), shifts_per_month)
        )

    conn.commit()
    conn.close()


def insert_preference(nurse_id, pref_type, data_dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO preferences (nurse_id, preference_type, data, created_at) VALUES (?, ?, ?, ?)",
        (nurse_id, pref_type, json.dumps(data_dict, ensure_ascii=False), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    print(f"Inserted pref for {nurse_id}: {pref_type} -> {data_dict}")

# ---------------------------
# Nurse Session Helpers
# ---------------------------
def upsert_nurse_profile(user_id, line_name):
    nurse_id = f"N_{re.sub(r'[^a-z0-9_]', '_', line_name.lower())}"
    upsert_nurse(nurse_id, name=line_name)
    return nurse_id

def update_nurse_details(nurse_id, level=None, unit=None, workload=None, skills=None):
    upsert_nurse(nurse_id, level=level, unit=unit, shifts_per_month=workload, skills=[skills] if skills else None)

def save_nurse_session(user_id, line_name):
    # Future placeholder for caching (no-op for now)
    pass

# ---------------------------
# Normalization Utilities
# ---------------------------
DAY_MAP = {
    "mon": "Mon", "monday": "Mon", "จันทร์": "Mon",
    "tue": "Tue", "tuesday": "Tue", "อังคาร": "Tue",
    "wed": "Wed", "wednesday": "Wed", "พุธ": "Wed",
    "thu": "Thu", "thursday": "Thu", "พฤหัส": "Thu", "พฤหัสบดี": "Thu",
    "fri": "Fri", "friday": "Fri", "ศุกร์": "Fri",
    "sat": "Sat", "saturday": "Sat", "เสาร์": "Sat",
    "sun": "Sun", "sunday": "Sun", "อาทิตย์": "Sun",
}

SHIFT_MAP = {
    "morning": "M", "เช้า": "M", "m": "M",
    "afternoon": "A", "บ่าย": "A", "a": "A",
    "night": "N", "กลางคืน": "N", "n": "N"
}

def normalize_day_list(raw_days):
    if not raw_days:
        return []
    if isinstance(raw_days, list):
        items = raw_days
    else:
        items = re.split(r"[,\s/]+", raw_days)
    normalized = [DAY_MAP.get(i.strip().lower(), i) for i in items if i.strip()]
    return list(dict.fromkeys(normalized))

# ---------------------------
# LINE Webhook Endpoint
# ---------------------------
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print("Received webhook event:", body[:200])

    try:
        handler.handle(body, signature)
    except Exception as e:
        print("Error handling event:", e)
        return str(e), 500
    return "OK"

# ---------------------------
# Message Handler
# ---------------------------
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    print("handle_message triggered")
    user_id = event.source.user_id
    user_message = event.message.text

    # Fetch LINE username
    try:
        profile = line_bot_api.get_profile(user_id)
        line_name = profile.display_name
    except Exception as e:
        print(f"Failed to fetch LINE profile: {e}")
        line_name = "Unknown"

    # Ensure nurse exists
    nurse_id = upsert_nurse_profile(user_id, line_name)
    save_nurse_session(user_id, line_name)

    # Send to Rasa
    try:
        rasa_resp = requests.post(RASA_URL, json={"text": user_message}, timeout=5)
        rasa_resp.raise_for_status()
        rasa_data = rasa_resp.json()
    except Exception as e:
        print(f"Error contacting Rasa: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="Sorry, I'm having trouble understanding right now. Please try again later.")
        )
        return

    intent = rasa_data.get("intent", {}).get("name")
    confidence = rasa_data.get("intent", {}).get("confidence", 0)
    entities = {e["entity"]: e["value"] for e in rasa_data.get("entities", [])}

    print(f"Rasa intent={intent}, confidence={confidence}, entities={entities}")

    # Fallback handling
    if not intent or intent == "nlu_fallback" or confidence < 0.5:
        insert_preference(nurse_id, "unrecognized", {"text": user_message})
        reply = f"Sorry {line_name}, I didn't quite get that. Could you please rephrase?"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return

    # Intent handling
    if intent == "provide_profile":
        update_nurse_details(nurse_id, level=entities.get("level"), unit=entities.get("unit"))
        reply = f"Thanks {line_name}! Profile updated (Level {entities.get('level')}, Unit: {entities.get('unit')})."

    elif intent == "add_skill":
        update_nurse_details(nurse_id, skills=entities.get("skill"))
        insert_preference(nurse_id, "skills", {"skill": entities.get("skill")})
        reply = f"Skill noted, {line_name}! ({entities.get('skill')})"

    elif intent == "set_workload":
        update_nurse_details(nurse_id, workload=entities.get("workload"))
        insert_preference(nurse_id, "workload", {"shifts_per_month": entities.get("workload")})
        reply = f"Got it, {line_name}! {entities.get('workload')} shifts per month recorded."

    elif intent == "add_shift_preference":
        shift = SHIFT_MAP.get(entities.get("shift", "").lower(), "M")
        days = normalize_day_list(entities.get("days", []))
        insert_preference(nurse_id, "preferred_shifts", {"shift": shift, "days": days})
        reply = f"Got it, {line_name}! Shift preference recorded."

    elif intent == "add_day_off":
        date = entities.get("date")
        rank = entities.get("rank", "2")
        insert_preference(nurse_id, "preferred_days_off", {"date": date, "rank": int(rank)})
        reply = f"Noted, {line_name}! Day off on {date} saved (priority {rank})."

    else:
        insert_preference(nurse_id, "general_message", {"text": user_message})
        reply = f"Thanks {line_name}, I’ve saved that."

    # Send LINE reply
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    print(f"Replied to {line_name}: {reply}")

# ---------------------------
# Admin Endpoints
# ---------------------------
@app.route("/view_prefs", methods=["GET"])
def view_prefs():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.cursor().execute("SELECT id, nurse_id, preference_type, data, created_at FROM preferences ORDER BY id DESC").fetchall()
    conn.close()
    results = [{"id": r[0], "nurse_id": r[1], "preference_type": r[2], "data": json.loads(r[3]), "created_at": r[4]} for r in rows]
    return jsonify(results)

@app.route("/export_profile/<nurse_id>", methods=["GET"])
def export_profile(nurse_id):
    conn = sqlite3.connect(DB_PATH)
    nurse = conn.cursor().execute("SELECT * FROM nurses WHERE id = ?", (nurse_id,)).fetchone()
    conn.close()
    return jsonify({"nurse_id": nurse[0], "name": nurse[1], "level": nurse[2], "unit": nurse[4]})

# ---------------------------
# Run (for local dev)
# ---------------------------
if __name__ == "__main__":
    print(f"Starting Flask app on port 8080 | DB: {DB_PATH}")
    app.run(port=8080, debug=True)