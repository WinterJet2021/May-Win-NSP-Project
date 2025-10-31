# app.py — Auto-increment nurse ID version
import os
import json
import re
import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv, find_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from collections import OrderedDict

# ------------------------------------
# Setup & Config
# ------------------------------------
env_path = find_dotenv()
load_dotenv(env_path)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
RASA_URL = os.getenv("RASA_URL", "http://localhost:5005/model/parse")
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "nurse_prefs.db"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NurseBot")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
app = Flask(__name__)

# ------------------------------------
# Database Helpers
# ------------------------------------
@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB Error: {e}")
        raise
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS nurses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_user_id TEXT UNIQUE,
            name TEXT,
            level INTEGER,
            employment_type TEXT,
            unit TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nurse_id INTEGER,
            preference_type TEXT,
            data TEXT,
            created_at TEXT
        )
        """)
    logger.info(f"Database initialized at: {DB_PATH}")

init_db()

# ------------------------------------
# DB Operations
# ------------------------------------
def get_or_create_nurse(line_user_id, name=None):
    """Find nurse by LINE user ID or create new record."""
    with db_connection() as conn:
        c = conn.cursor()
        nurse = c.execute("SELECT id FROM nurses WHERE line_user_id = ?", (line_user_id,)).fetchone()

        if nurse:
            return nurse[0]

        c.execute("INSERT INTO nurses (line_user_id, name) VALUES (?, ?)", (line_user_id, name or "Unknown"))
        new_id = c.lastrowid
        logger.info(f"New nurse created: ID={new_id}, LINE_ID={line_user_id}")
        return new_id


def update_nurse_details(nurse_id, level=None, unit=None, employment_type=None):
    emp_type = normalize_employment_type(employment_type) if employment_type else None
    with db_connection() as conn:
        c = conn.cursor()
        updates, params = [], []
        if level is not None: updates.append("level = ?"); params.append(level)
        if emp_type: updates.append("employment_type = ?"); params.append(emp_type)
        if unit: updates.append("unit = ?"); params.append(unit)
        if updates:
            params.append(nurse_id)
            c.execute(f"UPDATE nurses SET {', '.join(updates)} WHERE id = ?", params)


def insert_preference(nurse_id, pref_type, data_dict):
    with db_connection() as conn:
        conn.execute("""
            INSERT INTO preferences (nurse_id, preference_type, data, created_at)
            VALUES (?, ?, ?, ?)
        """, (nurse_id, pref_type, json.dumps(data_dict, ensure_ascii=False), datetime.utcnow().isoformat()))
    logger.info(f"Preference saved for nurse_id={nurse_id}: {pref_type} -> {data_dict}")

# ------------------------------------
# Helper Utilities
# ------------------------------------
def normalize_employment_type(value):
    if not value:
        return None
    v = str(value).strip().lower()
    if v in ("full-time", "full time", "fulltime", "ft"):
        return "full_time"
    if v in ("part-time", "part time", "parttime", "pt"):
        return "part_time"
    if v in ("contract", "temp"):
        return "contract"
    return v


def normalize_day_list(raw_days):
    if not raw_days:
        return []
    if isinstance(raw_days, list):
        items = raw_days
    else:
        items = re.split(r"[,\s/]+", raw_days)

    normalized = []
    for i in items:
        token = i.strip().lower()
        if token in ["จันทร์"]: normalized.append("Mon")
        elif token in ["อังคาร"]: normalized.append("Tue")
        elif token in ["พุธ"]: normalized.append("Wed")
        elif token in ["พฤหัส", "พฤหัสบดี"]: normalized.append("Thu")
        elif token in ["ศุกร์"]: normalized.append("Fri")
        elif token in ["เสาร์"]: normalized.append("Sat")
        elif token in ["อาทิตย์"]: normalized.append("Sun")
        else:
            normalized.append(DAY_MAP.get(token, token))
    return list(dict.fromkeys(normalized))


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

# ------------------------------------
# LINE Webhook + Rasa Integration
# ------------------------------------
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.error(f"Error handling event: {e}")
        return str(e), 500
    return "OK"


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    try:
        profile = line_bot_api.get_profile(user_id)
        line_name = profile.display_name
    except Exception:
        line_name = "Unknown"

    nurse_id = get_or_create_nurse(user_id, line_name)

    try:
        rasa_resp = requests.post(RASA_URL, json={"text": user_message}, timeout=5)
        rasa_resp.raise_for_status()
        rasa_data = rasa_resp.json()
    except Exception as e:
        logger.error(f"Error contacting Rasa: {e}")
        safe_reply(event, "ขอโทษค่ะ ระบบไม่สามารถตอบกลับได้ในตอนนี้")
        return

    intent = rasa_data.get("intent", {}).get("name")
    confidence = rasa_data.get("intent", {}).get("confidence", 0)
    entities = {e.get("entity"): e.get("value") for e in rasa_data.get("entities", []) if "entity" in e}

    if not intent or confidence < 0.5 or intent == "nlu_fallback":
        insert_preference(nurse_id, "unrecognized", {"text": user_message})
        safe_reply(event, f"ขอโทษค่ะ {line_name} ฉันไม่เข้าใจข้อความของคุณ กรุณาลองใหม่อีกครั้งนะคะ")
        return

    reply = process_intent(intent, nurse_id, entities, line_name)
    safe_reply(event, reply)


def safe_reply(event, text):
    try:
        if not text or not str(text).strip():
            text = "ขอโทษค่ะ ระบบไม่สามารถตอบกลับได้ในตอนนี้"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=text))
    except Exception as e:
        logger.error(f"LINE reply failed: {e}")

# ------------------------------------
# Intent Handling
# ------------------------------------
def process_intent(intent, nurse_id, entities, line_name):
    if intent == "update_profile":
        level = entities.get("level")
        employment_type = entities.get("employment_type")
        unit = entities.get("unit")

        level_value = None
        if level:
            m = re.search(r"\d+", str(level))
            if m:
                level_value = int(m.group())

        update_nurse_details(nurse_id, level=level_value, employment_type=employment_type, unit=unit)
        return f"Got it, {line_name}! Profile updated (Level {level_value or 1}, {employment_type or 'full_time'}, Unit: {unit or 'ER'})."

    elif intent == "add_shift_preference":
        shift = SHIFT_MAP.get(entities.get("shift", "").lower(), "M")
        days = normalize_day_list(entities.get("days", []))
        priority = entities.get("priority", "medium")
        insert_preference(nurse_id, "preferred_shifts", {"shift": shift, "days": days, "priority": priority})
        return f"Preference saved, {line_name}: {priority} priority {shift} shift on {', '.join(days)}."

    elif intent == "add_day_off":
        raw_day = entities.get("date")
        rank = entities.get("rank", 2)

        date_iso = None
        if raw_day:
            try:
                day = int(re.sub(r"\D", "", raw_day))
                now = datetime.now()
                if day < now.day:
                    next_month = now.month + 1 if now.month < 12 else 1
                    year = now.year if next_month != 1 else now.year + 1
                    date_obj = datetime(year, next_month, day)
                else:
                    date_obj = datetime(now.year, now.month, day)
                date_iso = date_obj.date().isoformat()
            except ValueError:
                date_iso = None

        insert_preference(nurse_id, "preferred_days_off", {"date": date_iso, "rank": int(rank)})
        if date_iso:
            return f"Got it, {line_name}! Day off on {date_iso} saved (priority {rank})."
        return f"Sorry {line_name}, I couldn’t recognize the date you meant. Please try again."

# ------------------------------------
# Export All
# ------------------------------------
@app.route("/export_all", methods=["GET"])
def export_all():
    """
    Export all nurses and preferences in optimizer-ready JSON format.
    Fields are ordered consistently: id, name, level, employment_type, unit, preferences.
    """
    with db_connection() as conn:
        nurses = conn.execute("SELECT id, name, level, employment_type, unit FROM nurses").fetchall()
        prefs = conn.execute("SELECT nurse_id, preference_type, data FROM preferences").fetchall()

    nurse_dict = {}
    for n in nurses:
        nurse_id = n[0]
        # Construct in target field order using OrderedDict
        nurse_dict[nurse_id] = OrderedDict([
            ("id", f"N{nurse_id:03}"),
            ("name", n[1] or ""),
            ("level", n[2] or 1),
            ("employment_type", n[3] or "full_time"),
            ("unit", n[4] or "ER"),
            ("preferences", {
                "preferred_shifts": [],
                "preferred_days_off": []
            })
        ])

    for nurse_id, pref_type, data in prefs:
        try:
            parsed = json.loads(data)
            if pref_type in nurse_dict[nurse_id]["preferences"]:
                nurse_dict[nurse_id]["preferences"][pref_type].append(parsed)
        except Exception as e:
            logger.warning(f"Failed to parse preference for {nurse_id}: {e}")

    # Sort output by numeric ID and maintain ordered keys
    sorted_nurses = [nurse_dict[k] for k in sorted(nurse_dict.keys())]
    return app.response_class(
        response=json.dumps({"nurses": sorted_nurses}, ensure_ascii=False, indent=2),
        mimetype="application/json"
    )

# ------------------------------------
# Run App
# ------------------------------------
if __name__ == "__main__":
    logger.info(f"Starting NurseBot Flask app on port 8080 | DB: {DB_PATH}")
    app.run(port=8080, debug=True)
