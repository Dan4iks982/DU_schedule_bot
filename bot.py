import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import os
import re
import uuid
import json
import logging
import asyncio
import shutil
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters
)

import db
import teachers
import locales

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo("Europe/Riga")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
USERS_FILE = BASE_DIR / "users.json"
CHATS_FILE = DATA_DIR / "registered_chats.json"
LAST_SYNC_FILE = DATA_DIR / "last_sync.json"
BLOCKED_FILE = DATA_DIR / "blocked_users.json"
STATS_FILE = DATA_DIR / "stats.json"
CONFIG_FILE = DATA_DIR / "config.json"
OVERRIDES_FILE = DATA_DIR / "manual_overrides.json"
INBOX_FILE = DATA_DIR / "inbox_messages.json"
HISTORY_FILE = DATA_DIR / "message_history.json"
ADMINS_FILE = DATA_DIR / "admins.json"
DU_PROGRAMS_FILE = DATA_DIR / "du_programs.json"
COURSE_TEACHERS_FILE = DATA_DIR / "course_teachers.json"

COURSE_TEACHERS_MAP = {}
def load_course_teachers_catalog():
    global COURSE_TEACHERS_MAP
    if COURSE_TEACHERS_FILE.exists():
        try:
            with open(COURSE_TEACHERS_FILE, "r", encoding="utf-8") as f:
                COURSE_TEACHERS_MAP = json.load(f)
                logger.info(f"Loaded course_teachers.json with {len(COURSE_TEACHERS_MAP.get('by_subject', {}))} subjects.")
        except Exception as e:
            logger.error(f"Error loading course_teachers.json: {e}")

load_course_teachers_catalog()

def get_teacher_for_event(subj: str, lulekaprlink: str = "", raw: dict = None) -> str:
    if not COURSE_TEACHERS_MAP:
        return ""
    by_link = COURSE_TEACHERS_MAP.get("by_link", {})
    by_code = COURSE_TEACHERS_MAP.get("by_code", {})
    by_subject = COURSE_TEACHERS_MAP.get("by_subject", {})

    # 1. Match by lulekaprlink
    if lulekaprlink and lulekaprlink in by_link:
        teachers = by_link[lulekaprlink].get("teachers", [])
        if teachers:
            return teachers[0]

    # 2. Match by course code in link
    if lulekaprlink:
        m = re.search(r'/kursa_apraksts_pub/([A-Z0-9]+)/', lulekaprlink)
        if m:
            code = m.group(1).upper()
            if code in by_code and by_code[code]:
                return by_code[code][0]

    # 3. Match by exact subject name
    clean_subj = subj.strip()
    if clean_subj in by_subject and by_subject[clean_subj]:
        return by_subject[clean_subj][0]

    # 4. Match case-insensitively / substring
    for k, v in by_subject.items():
        if v and (clean_subj.lower() == k.lower() or clean_subj.lower() in k.lower() or k.lower() in clean_subj.lower()):
            return v[0]

    return ""

# Strictly Whitelisted Admin IDs for testing notifications / experimental features
TEST_ALERT_USER_IDS = [1441874567, 879446270]

# Telegram Support Group ID
SUPPORT_GROUP_ID = -5130304059

# Programs Catalog
PROGRAMS = {
    "D01B9": "Информационные технологии (PBSP D01B9)",
    "D1270": "Biznesa un finanšu procesi (PBSP D1270)",
    "D1240": "Psiholoģija (BSP D1240)",
    "D02DO": "Valodu un kultūras studijas (BSP D02DO)"
}
PROGRAM_SHORT = dict(PROGRAMS)
FACULTIES = []

def load_du_faculties_and_programs():
    global PROGRAMS, PROGRAM_SHORT, FACULTIES
    if DU_PROGRAMS_FILE.exists():
        try:
            with open(DU_PROGRAMS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                FACULTIES = d.get("faculties", [])
                for fak in FACULTIES:
                    for p in fak.get("programs", []):
                        code = p["code"]
                        deg = p.get("degree", "").strip()
                        deg_str = f"{deg} " if deg else ""
                        name_ru = p.get("name_ru", p["name"])
                        PROGRAMS[code] = f"{deg_str}{p['name']} ({code})"
                        PROGRAM_SHORT[code] = name_ru
        except Exception as e:
            logger.error(f"Error loading du_programs.json: {e}")

load_du_faculties_and_programs()

DEFAULT_PROGRAM = "D01B9"
DEFAULT_SEMESTER = 3
AVAILABLE_SEMESTERS = [1, 2, 3, 4, 5, 6, 7, 8]

# Mapping between study year/input and LUIS Autumn semester:
# 1 курс -> 1 сем, 2 курс -> 3 сем, 3 курс -> 5 сем, 4 курс -> 7 сем
SEMESTER_MAP = {1: 1, 2: 1, 3: 3, 4: 3, 5: 5, 6: 5, 7: 7, 8: 7}

def get_semester_label(sem_num: int) -> str:
    mapped = SEMESTER_MAP.get(sem_num, sem_num)
    course_num = (mapped + 1) // 2
    return f"{course_num} курс / {mapped} сем."

# Master Admin IDs (always authorized) and Secret Passcode
MASTER_ADMIN_IDS = [879446270, 1441874567]

def is_d02do_subgroup_enabled(user_id: Optional[int] = None) -> bool:
    """Check if D02DO academic group choice is enabled.
    Open for all students.
    """
    return True
ADMIN_ACCOUNTS = {
    "danik_root": {
        "password": "Dx9#mK7$vQ2",
        "name": "Даниил",
        "username": "Dan4iks982",
        "user_id": 879446270,
        "role": "Главный администратор"
    },
    "sinica_admin": {
        "password": "Sn8@pL4!zR9",
        "name": "Даник Синица",
        "username": "daniksinica",
        "user_id": 1441874567,
        "role": "Администратор"
    }
}
SECRET_ADMIN_PASSCODE = "LUIS777"
SECRET_ADMIN_KEY = "K7#v9!Q2xP"

VIP_ECON_USER_ID = 879446270
VIP_ECON_PROG = "D1270"
VIP_ECON_SEM = 3

# Sync rate limit (15 minutes in seconds)
SYNC_COOLDOWN_SECONDS = 900
USER_LAST_SYNC = {}  # {user_id: datetime}

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

WEEKDAY_RU = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье"
}

WEEKDAY_LAT_TO_NUM = {
    'Mon': 0, 'Tue': 1, 'Wed': 2, 'Thu': 3, 'Fri': 4, 'Sat': 5, 'Sun': 6
}

# --- Database / Persistence ---

def load_json(file_path, default=None):
    if default is None:
        default = {}
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(file_path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_user_admin(user_id: int) -> bool:
    if user_id in MASTER_ADMIN_IDS:
        return True
    admins = load_json(ADMINS_FILE, [])
    return user_id in admins or str(user_id) in admins

def add_admin(user_id: int):
    admins = load_json(ADMINS_FILE, [])
    if user_id not in admins and str(user_id) not in admins:
        admins.append(user_id)
        save_json(ADMINS_FILE, admins)

def get_user_lang(user_id: int) -> str:
    if not user_id:
        return "ru"
    return db.get_user_language(user_id)

def is_cancel_message(text: str) -> bool:
    if not text:
        return False
    clean = text.strip().lower()
    return clean in [
        "/cancel", "./cancel", ".cancel", "cancel",
        "/stop", "./stop", ".stop", "stop",
        "отмена", "/отмена", ".отмена", "./отмена",
        "atcelt", "/atcelt", ".atcelt", "atceltā", "beigt",
        "назад", "выход", "exit", "/exit", "back", "close"
    ] or clean.startswith(("/cancel", "./cancel", ".cancel", "/atcelt"))

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data["state"] = None
    lang = get_user_lang(user.id if user else None)
    msg = locales.get_t("action_cancelled", lang)
    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user.id if user else None, lang=lang)
    )

async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type not in ["group", "supergroup"]:
        return
    if chat.id == SUPPORT_GROUP_ID:
        return
    new_status = update.my_chat_member.new_chat_member.status
    if new_status in ["member", "administrator"]:
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="ℹ️ <b>DU Schedule Bot работает только в личных сообщениях.</b>",
                parse_mode="HTML"
            )
            await context.bot.leave_chat(chat.id)
        except Exception:
            pass

def is_maintenance_mode() -> bool:
    cfg = load_json(CONFIG_FILE, {})
    return bool(cfg.get("maintenance_mode", False))

def set_maintenance_mode(enabled: bool):
    cfg = load_json(CONFIG_FILE, {})
    cfg["maintenance_mode"] = enabled
    save_json(CONFIG_FILE, cfg)

def get_manual_overrides():
    return load_json(OVERRIDES_FILE, [])

def apply_overrides(parsed_events):
    overrides = get_manual_overrides()
    if not overrides:
        return parsed_events
    result = []
    for orig in parsed_events:
        ev = dict(orig)
        for ov in overrides:
            ov_date = (ov.get("date") or "").strip()
            ov_subj = (ov.get("subj") or "").strip().lower()
            ov_note = (ov.get("note") or "").strip()
            if ov_date and ev.get("date") and ev["date"].strftime("%Y-%m-%d") != ov_date:
                continue
            if ov_subj and ov_subj not in ev.get("subj", "").lower():
                continue
            ev["change"] = f"[РУЧНОЕ ИЗМЕНЕНИЕ] {ov_note}"
            if ov.get("new_room"):
                ev["room"] = ov["new_room"].strip()
            if ov.get("new_group"):
                ev["group_raw"] = ov["new_group"].strip()
        result.append(ev)
    return result

def record_incoming_message(chat_id: int, user_id: int, user_name: str, username: str, chat_type: str, text: str, is_freeform: bool = False):
    inbox = load_json(INBOX_FILE, [])
    now_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    buttons = [
        "📅 Сегодня", "⏭️ Завтра", "📆 Вся неделя",
        "⏰ След. пара", "⏰ Следующая пара", "🔍 Выбрать день",
        "🔍 Поиск / Выбор", "🔄 Обновить", "🔄 Обновить из LUIS", "⚙️ Настройки",
        "🆘 Поддержка", "💡 Предложить улучшение"
    ]
    is_btn = text in buttons
    is_cmd = text.startswith("/") or is_btn
    is_question = is_freeform and not is_cmd

    entry = {
        "id": str(uuid.uuid4())[:8],
        "time": now_str,
        "chat_id": chat_id,
        "user_id": user_id,
        "user_name": user_name or f"ID {user_id}",
        "username": username or "",
        "chat_type": chat_type,
        "text": text,
        "is_command": is_cmd,
        "is_question": is_question,
        "status": "unread" if is_question else "info"
    }
    inbox.append(entry)
    if len(inbox) > 1000:
        inbox = inbox[-1000:]
    save_json(INBOX_FILE, inbox)

def is_user_blocked(user_id: int) -> bool:
    if db.is_user_blocked(user_id):
        return True
    blocked = load_json(BLOCKED_FILE, [])
    return user_id in blocked or str(user_id) in blocked

def record_activity(chat_id: int, user_id: int, title: str, username: str, chat_type: str, command: str, details: str = ""):
    now_iso = datetime.now(TIMEZONE).isoformat()
    db.update_user_activity(user_id, username or "", title or "")
    db.record_activity_hit()
    det = details or command
    db.record_user_event(user_id, command, det, username or "", title or "")
    
    # Update registered chats
    chats = load_json(CHATS_FILE, {})
    cid_str = str(chat_id)
    if cid_str not in chats:
        chats[cid_str] = {
            "id": chat_id,
            "title": title or "Unknown",
            "username": username or "",
            "type": chat_type,
            "first_seen": now_iso,
            "last_active": now_iso,
            "request_count": 1,
            "is_blocked": is_user_blocked(user_id)
        }
    else:
        c = chats[cid_str]
        c["title"] = title or c.get("title", "Unknown")
        c["username"] = username or c.get("username", "")
        c["type"] = chat_type
        c["last_active"] = now_iso
        c["request_count"] = c.get("request_count", 0) + 1
        c["is_blocked"] = is_user_blocked(user_id)
    save_json(CHATS_FILE, chats)

    # Update stats
    stats = load_json(STATS_FILE, {
        "total_requests": 0,
        "commands": {},
        "last_activity": None
    })
    stats["total_requests"] = stats.get("total_requests", 0) + 1
    stats["last_activity"] = now_iso
    cmds = stats.setdefault("commands", {})
    cmds[command] = cmds.get(command, 0) + 1
    save_json(STATS_FILE, stats)

def get_user_settings(user_id: int):
    u = db.get_user(user_id)
    if u:
        prog = u.get("program_code", DEFAULT_PROGRAM)
        sem = int(u.get("semester", DEFAULT_SEMESTER))
    else:
        u_new = db.get_or_create_user(user_id)
        prog = u_new.get("program_code", DEFAULT_PROGRAM)
        sem = int(u_new.get("semester", DEFAULT_SEMESTER))
    if prog not in PROGRAMS:
        prog = DEFAULT_PROGRAM
    if sem not in AVAILABLE_SEMESTERS:
        sem = DEFAULT_SEMESTER
    return prog, sem

def set_user_program(user_id: int, prog_code: str):
    prog_name = PROGRAMS.get(prog_code, prog_code)
    db.set_user_program(user_id, prog_code, prog_name=prog_name)
    # Sync with users.json
    users = load_json(USERS_FILE, {})
    val = users.get(str(user_id))
    if isinstance(val, dict):
        val["program"] = prog_code
    else:
        val = {"program": prog_code, "semester": DEFAULT_SEMESTER}
    users[str(user_id)] = val
    save_json(USERS_FILE, users)

def set_user_semester(user_id: int, sem_num: int):
    db.set_user_semester(user_id, sem_num)
    # Sync with users.json
    users = load_json(USERS_FILE, {})
    val = users.get(str(user_id))
    if isinstance(val, dict):
        val["semester"] = sem_num
    else:
        val = {"program": DEFAULT_PROGRAM, "semester": sem_num}
    users[str(user_id)] = val
    save_json(USERS_FILE, users)

def get_system_telemetry():
    telemetry = {
        "mem_total_mb": 0,
        "mem_used_mb": 0,
        "mem_percent": 0,
        "cpu_load_1m": 0.0,
        "disk_total_gb": 0,
        "disk_free_gb": 0,
        "disk_percent": 0
    }
    try:
        meminfo = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = parts[1].strip().split()[0]
                    meminfo[k] = int(v)
        total = meminfo.get("MemTotal", 0) // 1024
        avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0)) // 1024
        used = total - avail
        pct = round((used / total) * 100, 1) if total > 0 else 0
        telemetry["mem_total_mb"] = total
        telemetry["mem_used_mb"] = used
        telemetry["mem_percent"] = pct
    except Exception:
        pass

    try:
        with open("/proc/loadavg") as f:
            loads = f.read().split()
            telemetry["cpu_load_1m"] = float(loads[0])
    except Exception:
        pass

    try:
        total_b, used_b, free_b = shutil.disk_usage("/")
        telemetry["disk_total_gb"] = round(total_b / (1024**3), 1)
        telemetry["disk_free_gb"] = round(free_b / (1024**3), 1)
        telemetry["disk_percent"] = round((used_b / total_b) * 100, 1) if total_b > 0 else 0
    except Exception:
        pass

    return telemetry

# --- Schedule Parsing & Cache ---

def extract_event_group(raw: dict, title_full: str = "") -> str:
    """Extracts group/audience information from raw event and title."""
    ltype = raw.get("lulecturetype", "").strip()
    piezimes = raw.get("piezimes", "").strip()

    # 1. Check piezimes for specific group mentions or notes
    if piezimes:
        p_low = piezimes.lower()
        if "kopā" in p_low and ("gr" in p_low or "grup" in p_low):
            return piezimes
        for g_pat in ["1.grupa", "1. grupa", "2.grupa", "2. grupa", "3.grupa", "3. grupa", "4.grupa", "4. grupa"]:
            if g_pat in p_low:
                return piezimes

    # 2. Extract lines from lulecturetype (after line 0)
    ltype_lines = [l.strip() for l in ltype.split("\n") if l.strip()]
    if len(ltype_lines) > 1:
        return " • ".join(ltype_lines[1:])

    # 3. Fallback: check title lines for group mentions
    t_lines = [l.strip() for l in title_full.split("\n") if l.strip()]
    for line in t_lines[1:]:
        if any(w in line.lower() for w in ["grup", "gr."]):
            return line

    return ""

def load_events_from_disk(prog_code: str, sem_num: int = 3):
    mapped_sem = SEMESTER_MAP.get(sem_num, sem_num)
    file_path = DATA_DIR / f"events_{prog_code}_sem{mapped_sem}.json"
    if not file_path.exists():
        file_path = DATA_DIR / f"events_{prog_code}_sem{sem_num}.json"
    if not file_path.exists():
        file_path = DATA_DIR / f"events_{prog_code}.json"
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception as e:
        logger.error(f"Error reading events file for {prog_code} sem {sem_num}: {e}")
        return []

    parsed_events = []
    for e in events:
        raw = e.get("raw", {})
        title_full = e.get("title", "").strip()
        parts = [p.strip() for p in title_full.split("\n") if p.strip()]
        subj = parts[0] if parts else "Занятие"

        group_raw = extract_event_group(raw, title_full)

        # Extract room cleanly without group text pollution
        room = ""
        for p in parts[1:]:
            p_clean = p.strip()
            if p_clean == group_raw or any(w in p_clean.lower() for w in ["grup", "gr.", "visām", "visam", "prog.", "valoda", "studijas"]):
                continue
            if not room:
                room = p_clean

        start_str = e.get("start", "")
        sp = start_str.split()
        if len(sp) >= 5:
            w_str = sp[0]
            mon_str = sp[1]
            day_num = int(sp[2])
            year_num = int(sp[3])
            mon_num = MONTH_MAP.get(mon_str, 9)
            ev_date = date(year_num, mon_num, day_num)
            time_str = sp[4][:5]
            wday = WEEKDAY_LAT_TO_NUM.get(w_str, ev_date.weekday())
        else:
            continue

        ltype = raw.get("lulecturetype", "").strip().replace("\n", " ")
        change = raw.get("changetext", "").strip()
        piezimes = raw.get("piezimes", "").strip()

        parc_tips = raw.get("parc_tips", "").strip()
        parc_uz = raw.get("parc_uz", "").strip()
        cnames = e.get("className", [])
        if isinstance(cnames, str):
            cnames = [cnames]
        cnames_set = set(cnames)

        # 1. Is this an obsolete slot moved away to another time?
        # In LUIS: parc_tips == "Pārcelta" or "tips-R" marks the obsolete slot that was moved away TO parc_uz!
        is_moved_away = (parc_tips == "Pārcelta" or "tips-R" in cnames_set)

        # 2. Is this the new active slot where the lesson was moved TO?
        # In LUIS: parc_uz == "Pārceltā" marks the active rescheduled lesson taking place here!
        is_rescheduled = (parc_uz == "Pārceltā")

        # 3. Is this class canceled?
        is_cancelled = (parc_tips == "Atcelta" or "tips-A" in cnames_set)

        # 4. Is this a calendar note (holiday or shortened day)?
        is_holiday = (subj == "Svētku diena" or "svētku diena" in subj.lower())
        is_shortened = (subj == "Saīsinātā diena" or "saīsinātā diena" in subj.lower())
        is_calendar_note = is_holiday or is_shortened or (time_str == "00:00")

        lulekaprlink = raw.get("lulekaprlink", "").strip()
        teacher = get_teacher_for_event(subj, lulekaprlink, raw)

        parsed_events.append({
            "id": e.get("id"),
            "prog_code": prog_code,
            "sem_num": sem_num,
            "date": ev_date,
            "weekday": wday,
            "time": time_str,
            "subj": subj,
            "room": room,
            "teacher": teacher,
            "type": ltype,
            "group_raw": group_raw,
            "change": change,
            "piezimes": piezimes,
            "parc_tips": parc_tips,
            "parc_uz": parc_uz,
            "is_moved_away": is_moved_away,
            "is_rescheduled": is_rescheduled,
            "rescheduled_from": "",
            "is_cancelled": is_cancelled,
            "is_holiday": is_holiday,
            "is_shortened": is_shortened,
            "is_calendar_note": is_calendar_note
        })

    # Pass 2: Link active rescheduled slots to original moved-away slots to extract original time
    for act in parsed_events:
        if act["is_rescheduled"]:
            act_date_str = act["date"].strftime("%d.%m.%Y")
            act_time_norm = act["time"].replace(":", ".")
            for old in parsed_events:
                if old["is_moved_away"] and (old["subj"].lower() in act["subj"].lower() or act["subj"].lower() in old["subj"].lower()):
                    old_target = old.get("parc_uz", "")
                    if act_time_norm in old_target or act["time"] in old_target or act_date_str in old_target:
                        old_d_str = old["date"].strftime("%d.%m.%Y")
                        if old_d_str != act_date_str:
                            act["rescheduled_from"] = f"перенесено с {old['time']}, {old_d_str[:5]}"
                        else:
                            act["rescheduled_from"] = f"перенесено с {old['time']}"
                        break
            if not act["rescheduled_from"]:
                act["rescheduled_from"] = "перенесенное занятие"

    has_mult = has_course_subgroups(prog_code, sem_num, events=parsed_events)
    for p in parsed_events:
        p["has_multiple_groups"] = has_mult

    return parsed_events

EVENTS_CACHE = {}
SUBGROUPS_CACHE = {}

def get_program_subgroups(prog_code: str, sem_num: int = 3, events: list = None) -> list[str]:
    """
    Return a list of available subgroup codes for a given program and semester.
    Examples:
      - D02DO: ['ANGST', 'RUSST', 'LATST']
      - D01B9 sem 1: ['1', '2', '3']
      - D01B9 sem 3: []
      - D0154 sem 3: ['1', '2']
      - D1240 sem 3: ['1', '2']
    """
    mapped_sem = SEMESTER_MAP.get(sem_num, sem_num)
    cache_key = f"{prog_code}_sem{mapped_sem}"
    if events is None and cache_key in SUBGROUPS_CACHE:
        return SUBGROUPS_CACHE[cache_key]

    if prog_code == "D02DO":
        res = ["ANGST", "RUSST", "LATST"]
        SUBGROUPS_CACHE[cache_key] = res
        return res

    evs = events if events is not None else get_events_for(prog_code, mapped_sem)
    if not evs:
        return []

    found_numbers = set()
    for e in evs:
        g = e.get("group_raw", "") or ""
        pz = e.get("piezimes", "") or ""
        tp = e.get("type", "") or ""
        combined = f"{g} {pz} {tp}"
        for m in re.finditer(r"\b([1-9])\s*\.?\s*gr(?:upa|\.|\b)", combined, re.IGNORECASE):
            found_numbers.add(m.group(1))

    if len(found_numbers) >= 2:
        res = sorted(list(found_numbers), key=lambda x: int(x))
    else:
        res = []

    if events is None:
        SUBGROUPS_CACHE[cache_key] = res
    return res

def has_course_subgroups(prog_code: str, sem_num: int = 3, events: list = None) -> bool:
    return len(get_program_subgroups(prog_code, sem_num, events=events)) > 1

def get_events_for(prog_code: str, sem_num: int = 3):
    mapped_sem = SEMESTER_MAP.get(sem_num, sem_num)
    key = f"{prog_code}_sem{mapped_sem}"
    if key not in EVENTS_CACHE:
        events = load_events_from_disk(prog_code, mapped_sem)
        EVENTS_CACHE[key] = events
        # If cache is empty, launch async scrape in background if loop is active
        if not events:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(run_live_sync(prog_code, mapped_sem))
            except RuntimeError:
                pass
    return EVENTS_CACHE[key]

def reload_cache(prog_code: str, sem_num: int = 3):
    mapped_sem = SEMESTER_MAP.get(sem_num, sem_num)
    key = f"{prog_code}_sem{mapped_sem}"
    SUBGROUPS_CACHE.pop(key, None)
    EVENTS_CACHE[key] = load_events_from_disk(prog_code, mapped_sem)

# --- Live Sync Service ---

async def run_live_sync(prog_code: str = "D01B9", sem_num: int = 3):
    logger.info(f"Running scraper.js for {prog_code} sem {sem_num}...")
    old_events = get_events_for(prog_code, sem_num)
    old_changes = {e["id"]: e["change"] for e in old_events if e.get("id") and e.get("change")}

    try:
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(BASE_DIR / "scraper.js"),
            prog_code,
            str(sem_num),
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=50)
        out_str = stdout.decode("utf-8", errors="ignore")
        logger.info(f"Scraper output: {out_str}")

        if proc.returncode == 0 and "success\":true" in out_str:
            reload_cache(prog_code, sem_num)
            new_events = get_events_for(prog_code, sem_num)
            
            fresh_diffs = []
            for ev in new_events:
                eid = ev.get("id")
                ch = ev.get("change")
                if ch and (eid not in old_changes or old_changes[eid] != ch):
                    fresh_diffs.append(ev)

            return True, len(new_events), fresh_diffs
        else:
            return False, f"Scraper error: {stderr.decode('utf-8', errors='ignore')}", []
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        return False, str(e), []

# --- Formatting ---

def get_main_keyboard(user_id: int = None, lang: str = None):
    if not lang:
        lang = get_user_lang(user_id) if user_id else "ru"
    b_today = locales.BUTTONS["today"].get(lang, "📅 Сегодня")
    b_tomorrow = locales.BUTTONS["tomorrow"].get(lang, "⏭️ Завтра")
    b_week = locales.BUTTONS["week"].get(lang, "📆 Вся неделя")
    b_next = locales.BUTTONS["next"].get(lang, "⏰ След. пара")
    b_teacher = locales.BUTTONS["teacher"].get(lang, "👨‍🏫 Поиск преподавателя")
    b_day = locales.BUTTONS["select_day"].get(lang, "🔍 Выбрать день")
    b_update = locales.BUTTONS["update"].get(lang, "🔄 Обновить")
    b_settings = locales.BUTTONS["settings"].get(lang, "⚙️ Настройки")
    b_help = locales.BUTTONS["help"].get(lang, "ℹ️ Справка / FAQ")
    
    rows = [
        [KeyboardButton(b_today), KeyboardButton(b_tomorrow)],
        [KeyboardButton(b_week), KeyboardButton(b_next)],
        [KeyboardButton(b_teacher), KeyboardButton(b_day)],
        [KeyboardButton(b_update), KeyboardButton(b_settings), KeyboardButton(b_help)]
    ]
    if user_id == VIP_ECON_USER_ID:
        b_vip = locales.BUTTONS["vip_econ"].get(lang, "💼 Экономисты 2 курс")
        rows.append([KeyboardButton(b_vip)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def get_clean_lesson_type(ltype_raw: str, lang: str = "ru") -> str:
    return locales.get_clean_lesson_type(ltype_raw, lang)

def format_event(ev, lang: str = "ru", show_all_groups: Optional[bool] = None):
    time_icon = "⏰"
    subj = ev["subj"]
    room = ev["room"]
    ltype = ev.get("type", "")
    group_raw = ev.get("group_raw", "")
    change = ev.get("change", "")
    is_rescheduled = ev.get("is_rescheduled", False)
    rescheduled_from = ev.get("rescheduled_from", "")
    is_cancelled = ev.get("is_cancelled", False)
    teacher = ev.get("teacher", "").strip()
    teacher_str = ""
    if teacher:
        t_label = locales.get_t("teacher_label", lang)
        teacher_str = f"\n   {t_label}: <b>{teacher}</b>"

    if show_all_groups is None:
        show_all_groups = ev.get("has_multiple_groups", False)

    group_str = ""
    if group_raw:
        g_fmt = locales.format_event_group(group_raw, lang, show_all_groups=show_all_groups)
        if g_fmt:
            group_str = f"\n   {g_fmt}"

    if is_cancelled:
        canc_msg = locales.get_t("cancelled_class", lang, time=ev['time'], subj=subj)
        if group_str:
            canc_msg += group_str
        if teacher_str:
            canc_msg += teacher_str
        return canc_msg

    if room and "online" not in room.lower() and "tiešsaistē" not in room.lower():
        room_str = locales.get_t("room_aud", lang, room=room)
    else:
        room_str = locales.get_t("room_online", lang)

    if "klātienes studijas" in ltype.lower() or "tiešsaistē" in ltype.lower():
        room_str = locales.get_t("room_online", lang)

    clean_type = get_clean_lesson_type(ltype, lang)
    type_str = f"🏷️ <i>{clean_type}</i>" if clean_type else ""

    text = f"{time_icon} <b>{ev['time']}</b> — <b>{subj}</b>\n   {room_str}"
    if type_str:
        text += f"\n   {type_str}"
    if group_str:
        text += group_str
    if teacher_str:
        text += teacher_str
    if is_rescheduled:
        resched_badge = locales.get_t("rescheduled_badge", lang)
        note = ""
        if rescheduled_from:
            if "перенесено с" in rescheduled_from:
                prefix = locales.get_t("rescheduled_from_prefix", lang)
                part = rescheduled_from.replace("перенесено с", prefix)
                note = f" <i>({part})</i>"
            elif rescheduled_from == "перенесенное занятие":
                note = f" <i>({locales.get_t('rescheduled_generic', lang)})</i>"
            else:
                note = f" <i>({rescheduled_from})</i>"
        text += f"\n   {resched_badge}{note}"
    elif change:
        ch_label = "ИЗМЕНЕНИЕ" if lang == "ru" else ("IZMAIŅAS" if lang == "lv" else "CHANGE")
        text += f"\n   ⚠️ <b>{ch_label}:</b> <i>{change}</i>"
    return text

def filter_d02do_events(events: list, subgroup: str) -> list:
    """Filter D02DO events by study stream/subgroup while keeping all shared 'Visām grupām' classes."""
    if not subgroup or str(subgroup).strip().upper() == "ALL":
        return events
    sg = str(subgroup).strip().upper()
    res = []
    for ev in events:
        # Holidays, shortened days and calendar notes are always preserved
        if ev.get("is_calendar_note") or ev.get("is_holiday") or ev.get("is_shortened"):
            res.append(ev)
            continue
        g = ev.get("group_raw", "") or ""
        t = ev.get("type", "") or ""
        if not g and not t:
            res.append(ev)
            continue

        g_upper = g.upper()
        t_upper = t.upper()
        g_lower = g.lower()
        t_lower = t.lower()

        # Pure 'Visām grupām' (shared across all streams)
        has_stream = any(s in g_upper or s in t_upper for s in ["ANGST", "RUSST", "LATST", "RUSISTIKAS", "LATVIEŠU VALODA KĀ OTRA"])
        if not has_stream and ("visām grupām" in g_lower or "visam grupam" in g_lower):
            res.append(ev)
            continue

        if sg == "ANGST":
            if "ANGST" in g_upper or "ANGST" in t_upper:
                res.append(ev)
        elif sg == "RUSST":
            if "RUSST" in g_upper or "RUSST" in t_upper or "rusistikas" in g_lower or "rusistikas" in t_lower:
                res.append(ev)
        elif sg == "LATST":
            if "LATST" in g_upper or "LATST" in t_upper or "latviešu valoda kā otra" in g_lower or "latviešu valoda kā otra" in t_lower:
                res.append(ev)
    return res

def filter_schedule_events(events: list, prog_code: str, sem_num: int, subgroup: str) -> list:
    """Filter schedule events by academic group or stream while keeping shared classes."""
    if not subgroup or str(subgroup).strip().upper() == "ALL":
        return events

    sg = str(subgroup).strip()
    if prog_code == "D02DO":
        return filter_d02do_events(events, sg)

    subgroups = get_program_subgroups(prog_code, sem_num)
    if len(subgroups) <= 1:
        return events

    res = []
    for ev in events:
        if ev.get("is_calendar_note") or ev.get("is_holiday") or ev.get("is_shortened"):
            res.append(ev)
            continue

        g_raw = ev.get("group_raw", "") or ""
        piezimes = ev.get("piezimes", "") or ""
        t_raw = ev.get("type", "") or ""
        combined = f"{g_raw} {piezimes} {t_raw}".lower()

        # Shared lectures across all groups
        if "visām grupām" in combined or "visam grupam" in combined:
            res.append(ev)
            continue

        # Combined group notes like '1. un 2. gr. kopā'
        if "kopā" in combined or "kopa" in combined:
            if "vis" in combined or re.search(rf"\b{re.escape(sg)}\s*\.?\s*gr", combined) or f"{sg}." in combined or f"{sg} " in combined:
                res.append(ev)
                continue

        # If class matches user's specific group number
        if re.search(rf"\b{re.escape(sg)}\s*\.?\s*gr", combined):
            res.append(ev)
            continue

        # If class specifies other groups on this course, filter out
        other_sgs = [o for o in subgroups if o != sg]
        mentions_other = any(re.search(rf"\b{re.escape(o)}\s*\.?\s*gr", combined) for o in other_sgs)
        if mentions_other:
            continue

        # Keep classes without specific group restriction
        res.append(ev)

    return res

def get_schedule_for_date(target_date: date, prog_code: str, sem_num: int = 3, lang: str = "ru", user_id: int = None) -> str:
    events = apply_overrides(get_events_for(prog_code, sem_num))
    subgroups = get_program_subgroups(prog_code, sem_num)
    has_mult = len(subgroups) > 1
    active_subgroup = ""
    if user_id and has_mult:
        stored_sg = db.get_user_subgroup(user_id)
        if stored_sg and stored_sg.upper() != "ALL" and (stored_sg in subgroups or (prog_code != "D02DO" and stored_sg.isdigit())):
            active_subgroup = stored_sg
            events = filter_schedule_events(events, prog_code, sem_num, active_subgroup)

    day_events = [e for e in events if e["date"] == target_date and not e.get("is_moved_away")]
    day_name = locales.get_weekday_name(target_date.weekday(), lang)
    date_str = target_date.strftime("%d.%m.%Y")
    prog_name = PROGRAM_SHORT.get(prog_code, PROGRAMS.get(prog_code, prog_code)) if lang == "ru" else PROGRAMS.get(prog_code, prog_code)

    sem_label = locales.get_semester_label(sem_num, lang)
    header = (
        f"📅 <b>{day_name}, {date_str}</b>\n"
        f"🎓 <i>{prog_name} ({sem_label})</i>\n"
    )
    if active_subgroup and active_subgroup.upper() != "ALL":
        sg_lbl = locales.get_subgroup_label(prog_code, active_subgroup, lang=lang, short=True)
        grp_word = {"ru": "Группа", "lv": "Grupa", "en": "Group"}.get(lang, "Группа")
        header += f"👥 <i>{grp_word}: {sg_lbl.replace('👥 ', '')}</i>\n"

    if not events:
        return f"{header}\n" + locales.get_t("no_schedule_loaded", lang)

    # Filter out calendar notes (holidays, shortened) from classes
    holidays = [e for e in day_events if e.get("is_holiday")]
    shortened = [e for e in day_events if e.get("is_shortened")]
    classes = [e for e in day_events if not e.get("is_calendar_note")]

    if holidays:
        return header + "\n" + locales.get_t("holiday_banner", lang)

    if not classes:
        return header + "\n" + locales.get_t("no_classes_day", lang)

    classes.sort(key=lambda x: x["time"])
    body_parts = []
    if shortened:
        body_parts.append(locales.get_t("shortened_day", lang))
    body_parts.append("\n\n".join(format_event(e, lang=lang, show_all_groups=has_mult) for e in classes))
    return header + "\n" + "".join(body_parts)

def get_schedule_for_weekday(wday: int, prog_code: str, sem_num: int = 3, lang: str = "ru", user_id: int = None) -> str:
    now = datetime.now(TIMEZONE)
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    target_date = monday + timedelta(days=wday)
    if target_date < today:
        target_date += timedelta(days=7)
    return get_schedule_for_date(target_date, prog_code, sem_num, lang=lang, user_id=user_id)

def is_smart_week_enabled(user_id: Optional[int] = None) -> bool:
    """Smart week switcher: auto-switch to next week on weekends / Friday night,
    with multi-week inline navigation buttons up to 4 weeks forward (~1 month).
    Open for all students.
    """
    return True

def should_default_to_next_week(prog_code: str, sem_num: int = 3, user_id: int = None) -> bool:
    """Determine whether to default to the upcoming week instead of the current week."""
    now = datetime.now(TIMEZONE)
    today = now.date()
    wday = today.weekday()  # 0=Mon, ..., 4=Fri, 5=Sat, 6=Sun

    # Weekends (Saturday and Sunday)
    if wday in (5, 6):
        return True

    # Friday evening (from 17:30 onwards)
    if wday == 4 and (now.hour >= 18 or (now.hour == 17 and now.minute >= 30)):
        return True

    # Friday daytime: check if all classes for the week have ended
    if wday == 4:
        events = apply_overrides(get_events_for(prog_code, sem_num))
        if prog_code == "D02DO" and is_d02do_subgroup_enabled(user_id):
            active_subgroup = db.get_user_subgroup(user_id) if user_id else ""
            if active_subgroup:
                events = filter_d02do_events(events, active_subgroup)
        today_events = [e for e in events if e["date"] == today and not e.get("is_moved_away") and not e.get("is_calendar_note") and not e.get("is_cancelled")]
        if today_events:
            last_event_time = max(e["time"] for e in today_events)
            try:
                lh, lm = map(int, last_event_time.split(":"))
                end_hour = lh + (lm + 95) // 60
                end_min = (lm + 95) % 60
                if (now.hour > end_hour) or (now.hour == end_hour and now.minute >= end_min):
                    return True
            except Exception:
                pass
        else:
            if now.hour >= 14:
                return True

    return False

MAX_WEEK_OFFSET = 4

def get_week_navigation_keyboard(lang: str = "ru", current_offset: int = 0) -> Optional[InlineKeyboardMarkup]:
    now = datetime.now(TIMEZONE)
    today = now.date()
    curr_monday = today - timedelta(days=today.weekday())
    curr_sunday = curr_monday + timedelta(days=6)

    rows = []
    nav_row = []

    # Left button (Previous week)
    if current_offset > 0:
        prev_offset = current_offset - 1
        prev_monday = curr_monday + timedelta(days=prev_offset * 7)
        prev_sunday = prev_monday + timedelta(days=6)
        btn_text = f"◀️ {prev_monday.strftime('%d.%m')} — {prev_sunday.strftime('%d.%m')}"
        nav_row.append(InlineKeyboardButton(btn_text, callback_data=f"week_show_{prev_offset}"))

    # Right button (Next week)
    if current_offset < MAX_WEEK_OFFSET:
        next_offset = current_offset + 1
        next_monday = curr_monday + timedelta(days=next_offset * 7)
        next_sunday = next_monday + timedelta(days=6)
        if current_offset == 0:
            btn_text = locales.get_t("btn_next_week", lang, start=next_monday.strftime('%d.%m'), end=next_sunday.strftime('%d.%m'))
        else:
            btn_text = f"{next_monday.strftime('%d.%m')} — {next_sunday.strftime('%d.%m')} ▶️"
        nav_row.append(InlineKeyboardButton(btn_text, callback_data=f"week_show_{next_offset}"))

    if nav_row:
        rows.append(nav_row)

    # Home button (jump straight back to current week if viewing 2+ weeks ahead)
    if current_offset >= 2:
        home_text = locales.get_t("btn_current_week_home", lang, start=curr_monday.strftime('%d.%m'), end=curr_sunday.strftime('%d.%m'))
        rows.append([InlineKeyboardButton(home_text, callback_data="week_show_0")])

    return InlineKeyboardMarkup(rows) if rows else None

def get_full_week_schedule(
    prog_code: str, 
    sem_num: int = 3, 
    lang: str = "ru", 
    user_id: int = None,
    week_offset: int = 0
) -> str:
    prog_name = PROGRAM_SHORT.get(prog_code, PROGRAMS.get(prog_code, prog_code)) if lang == "ru" else PROGRAMS.get(prog_code, prog_code)
    sem_label = locales.get_semester_label(sem_num, lang)
    
    now = datetime.now(TIMEZONE)
    today = now.date()
    monday = today - timedelta(days=today.weekday()) + timedelta(days=week_offset * 7)
    sunday = monday + timedelta(days=6)
    
    if week_offset == 1:
        header_title = locales.get_t("next_week_header", lang, start=monday.strftime('%d.%m'), end=sunday.strftime('%d.%m'))
    elif week_offset == 0 and is_smart_week_enabled(user_id):
        header_title = locales.get_t("current_week_header", lang, start=monday.strftime('%d.%m'), end=sunday.strftime('%d.%m'))
    else:
        header_title = locales.get_t("week_header", lang, start=monday.strftime('%d.%m'), end=sunday.strftime('%d.%m'))

    subgroups = get_program_subgroups(prog_code, sem_num)
    has_mult = len(subgroups) > 1
    active_subgroup = ""
    events = apply_overrides(get_events_for(prog_code, sem_num))
    if user_id and has_mult:
        stored_sg = db.get_user_subgroup(user_id)
        if stored_sg and stored_sg.upper() != "ALL" and (stored_sg in subgroups or (prog_code != "D02DO" and stored_sg.isdigit())):
            active_subgroup = stored_sg
            events = filter_schedule_events(events, prog_code, sem_num, active_subgroup)

    msg = (
        f"{header_title}\n"
        f"🎓 <i>{prog_name} ({sem_label})</i>\n"
    )
    if active_subgroup and active_subgroup.upper() != "ALL":
        sg_lbl = locales.get_subgroup_label(prog_code, active_subgroup, lang=lang, short=True)
        grp_word = {"ru": "Группа", "lv": "Grupa", "en": "Group"}.get(lang, "Группа")
        msg += f"👥 <i>{grp_word}: {sg_lbl.replace('👥 ', '')}</i>\n"
    msg += "\n"

    if not events:
        return f"{msg}" + locales.get_t("no_schedule_loaded", lang)

    day_blocks = []
    for day_offset in range(6):  # Monday to Saturday
        target_d = monday + timedelta(days=day_offset)
        day_events = [e for e in events if e["date"] == target_d and not e.get("is_moved_away")]
        day_name = locales.get_weekday_name(target_d.weekday(), lang)
        date_short = target_d.strftime("%d.%m")
        
        holidays = [e for e in day_events if e.get("is_holiday")]
        shortened = [e for e in day_events if e.get("is_shortened")]
        classes = [e for e in day_events if not e.get("is_calendar_note")]

        # Skip Saturday completely if no classes
        if day_offset == 5 and not classes and not holidays:
            continue

        if holidays:
            day_blocks.append(f"──────────────────────\n" + locales.get_t("week_holiday_day", lang, day=day_name, date=date_short))
            continue

        if not classes:
            # Maximally compact empty day: e.g. "📅 Среда (11.09) — занятий нет"
            day_blocks.append(f"──────────────────────\n" + locales.get_t("week_empty_day", lang, day=day_name, date=date_short))
            continue

        classes.sort(key=lambda x: x["time"])
        day_header = f"📅 <b>{day_name}, {target_d.strftime('%d.%m.%Y')}</b>"
        body_parts = []
        if shortened:
            body_parts.append(locales.get_t("shortened_day", lang))
        body_parts.append("\n\n".join(format_event(e, lang=lang, show_all_groups=has_mult) for e in classes))
        day_blocks.append(f"──────────────────────\n{day_header}\n" + "".join(body_parts))

    if not day_blocks:
        msg += locales.get_t("no_classes_week", lang)
    else:
        msg += "\n\n".join(day_blocks)
    return msg

def split_long_week_message(text: str, max_len: int = 4000) -> List[str]:
    """Split a weekly schedule message at day boundaries if it exceeds Telegram's limit."""
    if len(text) <= max_len:
        return [text]
    parts = []
    current = ""
    blocks = text.split("──────────────────────\n")
    for i, b in enumerate(blocks):
        candidate = (b if i == 0 else "──────────────────────\n" + b)
        if current and len(current) + len(candidate) > max_len:
            parts.append(current)
            current = candidate
        else:
            current += candidate
    if current:
        parts.append(current)
    return parts if parts else [text[:max_len], text[max_len:]]

def get_next_event(prog_code: str, sem_num: int = 3, lang: str = "ru", user_id: int = None):
    now = datetime.now(TIMEZONE)
    today = now.date()
    events = apply_overrides(get_events_for(prog_code, sem_num))
    subgroups = get_program_subgroups(prog_code, sem_num)
    if user_id and len(subgroups) > 1:
        subgroup = db.get_user_subgroup(user_id)
        if subgroup and subgroup.upper() != "ALL":
            events = filter_schedule_events(events, prog_code, sem_num, subgroup)
    
    today_events = [e for e in events if e["date"] == today and not e.get("is_moved_away") and not e.get("is_calendar_note") and not e.get("is_cancelled")]
    today_events.sort(key=lambda x: x["time"])

    current_time_str = now.strftime("%H:%M")
    for ev in today_events:
        if ev["time"] >= current_time_str:
            return ev, locales.get_t("when_today", lang)

    if not events:
        return None, "no_schedule"

    for day_offset in range(1, 8):
        next_d = today + timedelta(days=day_offset)
        nxt_events = [e for e in events if e["date"] == next_d and not e.get("is_moved_away") and not e.get("is_calendar_note") and not e.get("is_cancelled")]
        if nxt_events:
            nxt_events.sort(key=lambda x: x["time"])
            wname = locales.get_weekday_name(next_d.weekday(), lang)
            prefix = {"ru": "в ", "lv": "", "en": "on "}.get(lang, "")
            return nxt_events[0], f"{prefix}{wname}, {next_d.strftime('%d.%m')}"

    return None, None

def get_live_radar(prog_code: str = "D01B9", sem_num: int = 3, user_id: int = None):
    events = apply_overrides(get_events_for(prog_code, sem_num))
    subgroups = get_program_subgroups(prog_code, sem_num)
    if user_id and len(subgroups) > 1:
        subgroup = db.get_user_subgroup(user_id)
        if subgroup and subgroup.upper() != "ALL":
            events = filter_schedule_events(events, prog_code, sem_num, subgroup)
    now = datetime.now(TIMEZONE)
    today = now.date()
    current_time_str = now.strftime("%H:%M")

    today_events = [e for e in events if e["date"] == today and not e.get("is_moved_away") and not e.get("is_calendar_note")]
    today_events.sort(key=lambda x: x["time"])

    current_class = None
    next_class = None

    for ev in today_events:
        start_t = ev.get("time", "")
        end_t = ev.get("end_time", "")
        if not end_t:
            try:
                sh, sm = map(int, start_t.split(":"))
                em = sm + 95
                end_t = f"{sh + em // 60:02d}:{em % 60:02d}"
            except Exception:
                end_t = start_t

        if start_t <= current_time_str <= end_t:
            try:
                sh, sm = map(int, start_t.split(":"))
                eh, em = map(int, end_t.split(":"))
                st_dt = datetime.combine(today, time(sh, sm), tzinfo=TIMEZONE)
                end_dt = datetime.combine(today, time(eh, em), tzinfo=TIMEZONE)
                total_sec = max(1, int((end_dt - st_dt).total_seconds()))
                elapsed_sec = max(0, int((now - st_dt).total_seconds()))
                rem_sec = max(0, int((end_dt - now).total_seconds()))
                rem_min = rem_sec // 60
                pct = min(100, max(0, int((elapsed_sec / total_sec) * 100)))
            except Exception:
                rem_min = 0
                pct = 50

            current_class = {
                **ev,
                "end_time": end_t,
                "remaining_min": rem_min,
                "progress_pct": pct
            }
            break

    for ev in today_events:
        if ev.get("time", "") > current_time_str:
            try:
                sh, sm = map(int, ev["time"].split(":"))
                st_dt = datetime.combine(today, time(sh, sm), tzinfo=TIMEZONE)
                starts_in_min = max(0, int((st_dt - now).total_seconds() // 60))
            except Exception:
                starts_in_min = 0
            next_class = {
                **ev,
                "starts_in_min": starts_in_min,
                "when": "сегодня"
            }
            break

    if not next_class:
        for day_offset in range(1, 8):
            next_d = today + timedelta(days=day_offset)
            nxt_events = [e for e in events if e["date"] == next_d]
            if nxt_events:
                nxt_events.sort(key=lambda x: x["time"])
                wname = WEEKDAY_RU.get(next_d.weekday(), "")
                next_class = {
                    **nxt_events[0],
                    "when": f"в {wname}, {next_d.strftime('%d.%m')}"
                }
                break

    status = "free"
    if current_class:
        status = "in_class"
    elif next_class and next_class.get("when") == "сегодня":
        status = "break"
    elif next_class:
        status = "done_today"
    else:
        status = "none"

    return {
        "status": status,
        "current_class": current_class,
        "next_class": next_class,
        "today_classes_count": len(today_events),
        "now_time": current_time_str
    }

def format_radar_message(radar_data: dict, prog_name: str, lang: str = "ru") -> str:
    status = radar_data["status"]
    curr = radar_data.get("current_class")
    nxt = radar_data.get("next_class")
    now_t = radar_data.get("now_time", "")

    header = locales.get_t("radar_title", lang, time=now_t, prog=prog_name)

    if status == "in_class" and curr:
        pct = curr.get("progress_pct", 50)
        filled = min(10, max(0, int(pct / 10)))
        bar = "🟩" * filled + "⬜" * (10 - filled)
        rem = curr.get("remaining_min", 0)
        room_str = locales.get_t("room_aud", lang, room=curr['room']) if curr.get("room") else locales.get_t("room_online", lang)
        clean_type = get_clean_lesson_type(curr.get("type", ""), lang)
        type_str = f"🏷️ <i>{clean_type}</i>" if clean_type else ""

        body = (
            locales.get_t("radar_in_class", lang) + "\n"
            f"📚 <b>{curr['subj']}</b>\n"
            f"⏰ <b>{curr['time']} — {curr.get('end_time', '')}</b>\n"
            f"{room_str}\n"
        )
        if type_str:
            body += f"{type_str}\n"
        body += locales.get_t("radar_progress", lang, rem=rem, pct=pct, bar=bar)
        if curr.get("change"):
            ch_label = "ИЗМЕНЕНИЕ" if lang == "ru" else ("IZMAIŅAS" if lang == "lv" else "CHANGE")
            body += f"\n⚠️ <b>{ch_label}:</b> <i>{curr['change']}</i>\n"

        if nxt:
            nxt_room = nxt.get('room', '—')
            nxt_lbl = locales.get_t("radar_next_class", lang)
            body += f"\n{nxt_lbl} {nxt['time']} — <b>{nxt['subj']}</b> ({nxt_room})"
        return header + body

    elif status == "break" and nxt:
        starts_in = nxt.get("starts_in_min", 0)
        room_str = locales.get_t("room_aud", lang, room=nxt['room']) if nxt.get("room") else ""
        nxt_lbl = locales.get_t("radar_next_class", lang)
        return (
            header +
            locales.get_t("radar_break", lang) + "\n\n" +
            locales.get_t("radar_break_desc", lang, starts_in=starts_in) +
            f"{nxt_lbl}\n"
            f"📚 <b>{nxt['subj']}</b>\n" +
            locales.get_t("radar_starts_at", lang, time=nxt['time']) +
            f"{room_str}\n"
        )

    elif status == "done_today":
        msg = f"{header}" + locales.get_t("radar_done_today", lang) + "\n"
        if nxt:
            nxt_room = nxt.get('room', '—')
            when_val = nxt.get('when', '')
            msg += "\n" + locales.get_t("radar_closest_class", lang, when=when_val, time=nxt['time'], subj=nxt['subj'], room=nxt_room)
        return msg

    else:
        return f"{header}" + locales.get_t("radar_no_classes_today", lang)

def search_schedule(query: str, prog_code: str = "D01B9", sem_num: int = 3, lang: str = "ru", user_id: int = None):
    if not query or len(query.strip()) < 2:
        return locales.get_t("find_min_len", lang)

    q = query.strip().lower()
    events = apply_overrides(get_events_for(prog_code, sem_num))
    subgroups = get_program_subgroups(prog_code, sem_num)
    if user_id and len(subgroups) > 1:
        subgroup = db.get_user_subgroup(user_id)
        if subgroup and subgroup.upper() != "ALL":
            events = filter_schedule_events(events, prog_code, sem_num, subgroup)
    matched = []

    for ev in events:
        s = ev.get("subj", "").lower()
        r = ev.get("room", "").lower()
        t = ev.get("type", "").lower()
        if q in s or q in r or q in t:
            matched.append(ev)

    if not matched:
        return locales.get_t("find_not_found", lang, q=query)

    matched.sort(key=lambda x: (x["date"], x["time"]))
    now_d = datetime.now(TIMEZONE).date()
    upcoming = [e for e in matched if e["date"] >= now_d]
    res_list = upcoming[:6] if upcoming else matched[:6]

    res = locales.get_t("find_results_title", lang, q=query, count=len(matched))
    for ev in res_list:
        date_str = ev["date"].strftime("%d.%m.%Y")
        wname = locales.get_weekday_name(ev["weekday"], lang)
        room_str = f" • {ev['room']}" if ev.get("room") else ""
        res += f"📌 <b>{date_str} ({wname})</b> {ev['time']}{room_str}\n   <b>{ev['subj']}</b>\n"
        if ev.get("change"):
            ch_label = "ИЗМЕНЕНИЕ" if lang == "ru" else ("IZMAIŅAS" if lang == "lv" else "CHANGE")
            res += f"   ⚠️ <b>{ch_label}:</b> <i>{ev['change']}</i>\n"
        res += "\n"

    if len(matched) > 6:
        res += locales.get_t("find_more", lang, count=len(matched) - 6)
    return res

# --- Keyboards: Settings, Faculties, Programs ---

def get_subgroup_selection_keyboard(prog_code: str, sem_num: int, current_subgroup: str = "", lang: str = "ru") -> InlineKeyboardMarkup:
    subgroups = get_program_subgroups(prog_code, sem_num)
    cur = (current_subgroup or "ALL").strip().upper()
    buttons = []
    for code in subgroups:
        mark = "✅ " if cur == code.upper() else ""
        lbl = mark + locales.get_subgroup_label(prog_code, code, lang=lang, short=False)
        buttons.append([InlineKeyboardButton(lbl, callback_data=f"setsubgrp_{code}")])
    mark_all = "✅ " if cur == "ALL" or not cur else ""
    all_lbl = mark_all + locales.get_subgroup_label(prog_code, "ALL", lang=lang, short=False)
    buttons.append([InlineKeyboardButton(all_lbl, callback_data="setsubgrp_ALL")])
    back_lbl = {"ru": "⚙️ Открыть настройки", "lv": "⚙️ Iestatījumi", "en": "⚙️ Settings"}.get(lang, "⚙️ Настройки")
    buttons.append([InlineKeyboardButton(back_lbl, callback_data="cfg_back")])
    return InlineKeyboardMarkup(buttons)

def get_d02do_subgroup_keyboard(current_subgroup: str = "", lang: str = "ru") -> InlineKeyboardMarkup:
    return get_subgroup_selection_keyboard("D02DO", 3, current_subgroup=current_subgroup, lang=lang)

def get_settings_keyboard(current_prog: str, current_sem: int, lang: str = "ru", user_id: int = None) -> InlineKeyboardMarkup:
    mapped_cur = SEMESTER_MAP.get(current_sem, 3)
    c1 = f"{'✅ ' if mapped_cur == 1 else ''}{locales.get_semester_label(1, lang)}"
    c2 = f"{'✅ ' if mapped_cur == 3 else ''}{locales.get_semester_label(3, lang)}"
    c3 = f"{'✅ ' if mapped_cur == 5 else ''}{locales.get_semester_label(5, lang)}"
    c4 = f"{'✅ ' if mapped_cur == 7 else ''}{locales.get_semester_label(7, lang)}"
    
    btn_fac = locales.get_t("btn_choose_faculty", lang)
    lang_name = locales.LANG_NAMES.get(lang, "🇷🇺 Русский")
    btn_lang = f"🌐 {locales.get_t('btn_change_language', lang)} ({lang_name})"

    btn_sug = locales.BUTTONS["suggest"].get(lang, "💡 Предложить улучшение")
    btn_sup = locales.BUTTONS["support"].get(lang, "🆘 Поддержка")

    rows = [
        [
            InlineKeyboardButton(btn_fac, callback_data="cfg_faculties")
        ],
        [
            InlineKeyboardButton(btn_lang, callback_data="cfg_lang")
        ]
    ]

    subgroups = get_program_subgroups(current_prog, mapped_cur)
    if len(subgroups) > 1:
        subgroup = db.get_user_subgroup(user_id) if user_id else ""
        if subgroup and subgroup.upper() != "ALL" and subgroup not in subgroups:
            subgroup = "ALL"
        sg_short = locales.get_subgroup_label(current_prog, subgroup, lang=lang, short=True)
        grp_word = {"ru": "Группа", "lv": "Grupa", "en": "Group"}.get(lang, "Группа")
        lbl_sg = f"👥 {grp_word}: {sg_short.replace('👥 ', '')}"
        rows.append([
            InlineKeyboardButton(lbl_sg, callback_data="cfg_subgroup")
        ])
    else:
        lbl_single = locales.get_t("subgroup_btn_single", lang)
        rows.append([
            InlineKeyboardButton(lbl_single, callback_data="cfg_subgroup_single")
        ])

    rows.extend([
        [
            InlineKeyboardButton(c1, callback_data="setsem_1"),
            InlineKeyboardButton(c2, callback_data="setsem_3")
        ],
        [
            InlineKeyboardButton(c3, callback_data="setsem_5"),
            InlineKeyboardButton(c4, callback_data="setsem_7")
        ],
        [
            InlineKeyboardButton(btn_sug, callback_data="btn_suggest"),
            InlineKeyboardButton(btn_sup, callback_data="btn_support")
        ]
    ])

    return InlineKeyboardMarkup(rows)

def get_language_keyboard(current_lang: str = "ru") -> InlineKeyboardMarkup:
    back_lbl = {"ru": "Назад в настройки", "lv": "Atpakaļ uz iestatījumiem", "en": "Back to Settings"}.get(current_lang, "Назад")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'✅ ' if current_lang == 'ru' else ''}🇷🇺 Русский", callback_data="setlang_ru"),
            InlineKeyboardButton(f"{'✅ ' if current_lang == 'lv' else ''}🇱🇻 Latviešu", callback_data="setlang_lv")
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if current_lang == 'en' else ''}🇬🇧 English", callback_data="setlang_en")
        ],
        [
            InlineKeyboardButton(f"🔙 {back_lbl}", callback_data="cfg_back")
        ]
    ])

def get_faculties_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    rows = []
    for f in FACULTIES:
        fid = f.get("id", "")
        name = f.get("name_ru", f.get("name", "")) if lang == "ru" else f.get("name", "")
        rows.append([InlineKeyboardButton(name, callback_data=f"fak_{fid}_0")])
    back_lbl = {"ru": "🔙 Назад в настройки", "lv": "🔙 Atpakaļ uz iestatījumiem", "en": "🔙 Back to Settings"}.get(lang, "🔙 Назад в настройки")
    rows.append([InlineKeyboardButton(back_lbl, callback_data="cfg_back")])
    return InlineKeyboardMarkup(rows)

def get_programs_keyboard(faculty_id: str, page: int = 0, lang: str = "ru") -> InlineKeyboardMarkup:
    fak = next((f for f in FACULTIES if f.get("id") == faculty_id), None)
    if not fak:
        return get_faculties_keyboard(lang)
    
    progs = fak.get("programs", [])
    page_size = 7
    total_pages = max(1, (len(progs) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start_idx = page * page_size
    current_page_progs = progs[start_idx:start_idx + page_size]
    
    rows = []
    for p in current_page_progs:
        code = p["code"]
        deg = p.get("degree", "").strip()
        deg_str = f"{deg} " if deg else ""
        if lang == "ru":
            name = p.get("name_ru", f"{deg_str}{p['name']} ({code})")
        else:
            name = f"{deg_str}{p['name']} ({code})"
        rows.append([InlineKeyboardButton(name, callback_data=f"setprog_{code}")])
    
    nav_row = []
    btn_prev = {"ru": "⬅️ Назад", "lv": "⬅️ Atpakaļ", "en": "⬅️ Back"}.get(lang, "⬅️ Назад")
    btn_next = {"ru": "Вперед ➡️", "lv": "Tālāk ➡️", "en": "Next ➡️"}.get(lang, "Вперед ➡️")
    if page > 0:
        nav_row.append(InlineKeyboardButton(btn_prev, callback_data=f"fak_{faculty_id}_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(btn_next, callback_data=f"fak_{faculty_id}_{page + 1}"))
    rows.append(nav_row)
    
    back_fac = {"ru": "🔙 К списку факультетов", "lv": "🔙 Atpakaļ pie fakultātēm", "en": "🔙 Back to faculties"}.get(lang, "🔙 К списку факультетов")
    rows.append([InlineKeyboardButton(back_fac, callback_data="cfg_faculties")])
    return InlineKeyboardMarkup(rows)


def get_admin_dashboard_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    maint = is_maintenance_mode()
    maint_btn_text = "🟢 Техобслуживание: ВЫКЛ" if not maint else "🔴 Техобслуживание: ВКЛ"
    rows = [
        [
            InlineKeyboardButton("🟢 Студенты онлайн", callback_data="adm_online_users"),
            InlineKeyboardButton("📊 Топ фич / Аналитика", callback_data="adm_feature_stats")
        ],
        [
            InlineKeyboardButton("📢 Быстрая рассылка", callback_data="adm_quick_broadcast"),
            InlineKeyboardButton("📬 Тикеты поддержки", callback_data="adm_inbox")
        ],
        [
            InlineKeyboardButton("📢 Последний релиз / Охват", callback_data="adm_patchnotes"),
            InlineKeyboardButton("🛠️ Активные правки", callback_data="adm_overrides")
        ],
        [
            InlineKeyboardButton(maint_btn_text, callback_data="adm_toggle_maint"),
            InlineKeyboardButton("⚡ Обновить LUIS", callback_data="adm_forcesync")
        ]
    ]
    if user_id == VIP_ECON_USER_ID:
        rows.append([InlineKeyboardButton("💼 Расписание Экономистов (2 курс)", callback_data="adm_vip_econ")])
    rows.append([InlineKeyboardButton("❌ Закрыть панель", callback_data="adm_close")])
    return InlineKeyboardMarkup(rows)

# --- Telegram Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # Detect user language or fetch from DB
    db_user = db.get_user(user.id)
    if not db_user or not db_user.get("language"):
        tg_lang = (user.language_code or "").lower()
        if tg_lang.startswith("lv"):
            user_lang = "lv"
        elif tg_lang.startswith("en"):
            user_lang = "en"
        else:
            user_lang = "ru"
    else:
        user_lang = db_user.get("language", "ru")

    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "/start")
    if not db_user or not db_user.get("language"):
        db.set_user_language(user.id, user_lang)

    prog, sem = get_user_settings(user.id)
    prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
    sem_label = locales.get_semester_label(sem, user_lang)
    lang_name = locales.LANG_NAMES.get(user_lang, user_lang)

    welcome_text = locales.get_t(
        "start_welcome",
        user_lang,
        name=user.first_name or "",
        prog=prog_name,
        sem=sem_label,
        lang_name=lang_name
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user.id, lang=user_lang)
    )

async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "today")
    prog, sem = get_user_settings(user.id)
    now = datetime.now(TIMEZONE)
    msg = get_schedule_for_date(now.date(), prog, sem, lang=user_lang, user_id=user.id)
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "tomorrow")
    prog, sem = get_user_settings(user.id)
    now = datetime.now(TIMEZONE)
    tomorrow = now.date() + timedelta(days=1)
    msg = get_schedule_for_date(tomorrow, prog, sem, lang=user_lang, user_id=user.id)
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "week")
    prog, sem = get_user_settings(user.id)

    if is_smart_week_enabled(user.id):
        offset = 1 if should_default_to_next_week(prog, sem, user.id) else 0
        msg = get_full_week_schedule(prog, sem, lang=user_lang, user_id=user.id, week_offset=offset)
        kb = get_week_navigation_keyboard(lang=user_lang, current_offset=offset)
        if len(msg) <= 4000:
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
        else:
            parts = split_long_week_message(msg)
            for i, part in enumerate(parts):
                markup = kb if i == len(parts) - 1 else None
                await update.message.reply_text(part, parse_mode="HTML", reply_markup=markup)
    else:
        msg = get_full_week_schedule(prog, sem, lang=user_lang, user_id=user.id, week_offset=0)
        if len(msg) <= 4000:
            await update.message.reply_text(msg, parse_mode="HTML")
        else:
            parts = split_long_week_message(msg)
            for part in parts:
                await update.message.reply_text(part, parse_mode="HTML")

async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "next")
    prog, sem = get_user_settings(user.id)
    ev, when = get_next_event(prog, sem, lang=user_lang, user_id=user.id)
    if ev:
        header_txt = locales.get_t("radar_next_class", user_lang)
        has_mult = has_course_subgroups(prog, sem)
        ans = f"{header_txt} ({when}):\n\n" + format_event(ev, lang=user_lang, show_all_groups=has_mult)
    elif when == "no_schedule":
        ans = locales.get_t("no_schedule_loaded", user_lang)
    else:
        ans = locales.get_t("no_classes_week", user_lang)
    await update.message.reply_text(ans, parse_mode="HTML")

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    # 15-minute rate limit for regular users
    is_admin = is_user_admin(user.id)
    now_dt = datetime.now()
    last_sync = USER_LAST_SYNC.get(user.id)
    if not is_admin and last_sync:
        elapsed = (now_dt - last_sync).total_seconds()
        if elapsed < SYNC_COOLDOWN_SECONDS:
            rem = int(SYNC_COOLDOWN_SECONDS - elapsed)
            rem_m = rem // 60
            rem_s = rem % 60
            await update.message.reply_text(
                locales.get_t("sync_cooldown", user_lang, min=rem_m, sec=rem_s),
                parse_mode="HTML"
            )
            return

    USER_LAST_SYNC[user.id] = now_dt
    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "sync")
    
    status_msg = await update.message.reply_text(
        locales.get_t("sync_in_progress", user_lang),
        parse_mode="HTML"
    )

    prog, sem = get_user_settings(user.id)
    ok, count_or_err, diffs = await run_live_sync(prog, sem)

    if ok:
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
        sem_label = locales.get_semester_label(sem, user_lang)
        res_text = locales.get_t(
            "sync_success",
            user_lang,
            prog=prog_name,
            course=sem_label,
            count=count_or_err
        )
        if diffs:
            res_text += locales.get_t("sync_diffs_title", user_lang, count=len(diffs))
            for d in diffs[:3]:
                res_text += f"• {d['date'].strftime('%d.%m')} {d['subj']} ({d['change']})\n"
        await status_msg.edit_text(res_text, parse_mode="HTML")
    else:
        await status_msg.edit_text(
            locales.get_t("sync_error", user_lang, err=count_or_err),
            parse_mode="HTML"
        )

async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "now")
    prog, sem = get_user_settings(user.id)
    prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
    radar_data = get_live_radar(prog, sem, user_id=user.id)
    msg = format_radar_message(radar_data, prog_name, lang=user_lang)
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_find(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return
    q = " ".join(context.args).strip() if context.args else ""
    if not q:
        await update.message.reply_text(
            locales.get_t("find_usage", user_lang),
            parse_mode="HTML"
        )
        return
    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, f"find_{q[:15]}")
    prog, sem = get_user_settings(user.id)
    res = search_schedule(q, prog, sem, lang=user_lang, user_id=user.id)
    await update.message.reply_text(res, parse_mode="HTML")

def is_dan4iks(user) -> bool:
    if not user:
        return False
    uname = (getattr(user, "username", "") or "").lower().lstrip("@")
    uid = getattr(user, "id", 0)
    return uname == "dan4iks982" or uid in MASTER_ADMIN_IDS or uid == 879446270

def get_teacher_catalog_keyboard(page: int = 0, page_size: int = 8, lang: str = "ru"):
    all_t = sorted(teachers.get_all_teachers(), key=lambda x: x.get("name", ""))
    total = len(all_t)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    
    start_idx = page * page_size
    current_teachers = all_t[start_idx : start_idx + page_size]
    
    rows = []
    for t in current_teachers:
        rows.append([InlineKeyboardButton(f"👨‍🏫 {t['name']}", callback_data=f"tch_view_{t['id']}")])
    
    nav_row = []
    btn_prev = {"ru": "⬅️ Назад", "lv": "⬅️ Atpakaļ", "en": "⬅️ Back"}.get(lang, "⬅️ Назад")
    btn_next = {"ru": "Вперед ➡️", "lv": "Tālāk ➡️", "en": "Next ➡️"}.get(lang, "Вперед ➡️")
    if page > 0:
        nav_row.append(InlineKeyboardButton(btn_prev, callback_data=f"tch_catalog_{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(btn_next, callback_data=f"tch_catalog_{page + 1}"))
    rows.append(nav_row)
    
    btn_close = {"ru": "❌ Закрыть каталог", "lv": "❌ Aizvērt katalogu", "en": "❌ Close directory"}.get(lang, "❌ Закрыть каталог")
    rows.append([InlineKeyboardButton(btn_close, callback_data="tch_cancel")])
    return InlineKeyboardMarkup(rows), page, total_pages, total

async def send_teacher_catalog(target, context: ContextTypes.DEFAULT_TYPE, page: int = 0, is_edit: bool = False, lang: str = None):
    if not lang:
        user_id = target.from_user.id if hasattr(target, "from_user") else (target.effective_user.id if hasattr(target, "effective_user") else None)
        lang = get_user_lang(user_id) if user_id else "ru"
    kb, curr_page, total_pages, total = get_teacher_catalog_keyboard(page=page, page_size=8, lang=lang)
    text = (
        f"{locales.get_t('teacher_catalog_title', lang, total=total)}\n\n"
        f"<i>{locales.get_t('teacher_catalog_select', lang, page=curr_page + 1, total=total_pages)}</i>"
    )
    if is_edit and hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await target.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    elif hasattr(target, "message"):
        await target.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def cmd_find_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    user_lang = get_user_lang(user.id)
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return
    db.record_activity_hit()
    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "teacher_search")
    
    q = " ".join(context.args).strip() if context.args else ""
    if q.lower() == "all":
        await send_teacher_catalog(update, context, page=0, lang=user_lang)
        return

    if q:
        await process_teacher_search(update, context, q)
    else:
        context.user_data["state"] = "awaiting_teacher"
        msg_text = locales.get_t("teacher_search_title", user_lang)
        btn_cat_txt = locales.get_t("teacher_catalog_btn", user_lang)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_cat_txt, callback_data="tch_catalog_0")]
        ])
        await update.message.reply_text(msg_text, parse_mode="HTML", reply_markup=reply_kb)

async def process_teacher_search(update: Update, context: ContextTypes.DEFAULT_TYPE, q: str):
    user = update.effective_user
    user_lang = get_user_lang(user.id)
    if q.strip().lower() == "all":
        context.user_data["state"] = None
        await send_teacher_catalog(update, context, page=0, lang=user_lang)
        return

    matches = teachers.find_teachers(q)
    if not matches:
        not_found_msg = locales.get_t("teacher_not_found", user_lang, q=q)
        await update.message.reply_text(
            not_found_msg,
            parse_mode="HTML"
        )
        return
    
    context.user_data["state"] = None
    if len(matches) == 1:
        tch = matches[0]
        await send_teacher_schedule(update, context, str(tch["id"]), tch["name"], lang=user_lang)
    else:
        buttons = []
        for t in matches[:8]:
            buttons.append([InlineKeyboardButton(f"👨‍🏫 {t['name']}", callback_data=f"tch_view_{t['id']}")])
        cancel_lbl = locales.BUTTONS["cancel"].get(user_lang, "❌ Отмена")
        buttons.append([InlineKeyboardButton(cancel_lbl, callback_data="tch_cancel")])
        found_txt = locales.get_t("teacher_multiple_found", user_lang, count=len(matches))
        await update.message.reply_text(
            found_txt,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

async def send_teacher_schedule(target, context: ContextTypes.DEFAULT_TYPE, teacher_id: str, teacher_name: str = "", is_edit: bool = False, lang: str = None):
    if not lang:
        user_id = target.from_user.id if hasattr(target, "from_user") else (target.effective_user.id if hasattr(target, "effective_user") else None)
        lang = get_user_lang(user_id) if user_id else "ru"
    if not teacher_name:
        for t in teachers.get_all_teachers():
            if str(t.get("id")) == str(teacher_id):
                teacher_name = t.get("name", "")
                break
    if not teacher_name:
        default_name = {"ru": "Преподаватель", "lv": "Pasniedzējs", "en": "Faculty member"}.get(lang, "Преподаватель")
        teacher_name = f"{default_name} #{teacher_id}"

    loading_txt = locales.get_t("teacher_loading", lang, name=teacher_name)
    status_msg = None
    if is_edit and hasattr(target, "edit_message_text"):
        try:
            await target.edit_message_text(loading_txt, parse_mode="HTML")
            status_msg = target.message
        except Exception:
            status_msg = await target.message.reply_text(loading_txt, parse_mode="HTML")
    elif hasattr(target, "message"):
        status_msg = await target.message.reply_text(loading_txt, parse_mode="HTML")
    else:
        status_msg = await target.reply_text(loading_txt, parse_mode="HTML")

    raw_events = await teachers.scrape_teacher_schedule(teacher_id, teacher_name)
    parsed = teachers.parse_teacher_events(raw_events)
    card_html = teachers.get_teacher_status_card(teacher_name, parsed, lang=lang)

    btn_refresh = locales.BUTTONS["update"].get(lang, "🔄 Обновить")
    btn_other = {"ru": "🔍 Другой препод", "lv": "🔍 Cits pasniedzējs", "en": "🔍 Other faculty"}.get(lang, "🔍 Другой препод")
    btn_cat = locales.get_t("teacher_catalog_btn", lang)

    btn_rows = [
        [
            InlineKeyboardButton(btn_refresh, callback_data=f"tch_refresh_{teacher_id}"),
            InlineKeyboardButton(btn_other, callback_data="tch_search_again")
        ],
        [InlineKeyboardButton(btn_cat, callback_data="tch_catalog_0")]
    ]
    kb = InlineKeyboardMarkup(btn_rows)

    if status_msg:
        try:
            await status_msg.edit_text(card_html, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await status_msg.reply_text(card_html, parse_mode="HTML", reply_markup=kb)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "settings")
    prog, sem = get_user_settings(user.id)
    user_lang = get_user_lang(user.id)
    prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
    sem_label = locales.get_semester_label(sem, user_lang)
    lang_name = locales.LANG_NAMES.get(user_lang, user_lang)
    
    text = locales.get_t("settings_title", user_lang, prog=prog_name, course=sem_label, lang_name=lang_name)
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=get_settings_keyboard(prog, sem, lang=user_lang, user_id=user.id)
    )




# --- VIP Economists Feature (Exclusively for Danik @dan4iks982 / ID 879446270) ---

async def cmd_vip_econ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != VIP_ECON_USER_ID:
        return
    
    db.record_user_event(user.id, "vip_econ", "Просмотр расписания Экономистов", user.username, user.first_name)
    
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="vip_econ_today"),
            InlineKeyboardButton("🌅 Завтра", callback_data="vip_econ_tomorrow")
        ],
        [
            InlineKeyboardButton("📆 Вся неделя", callback_data="vip_econ_week"),
            InlineKeyboardButton("⏰ След. пара", callback_data="vip_econ_radar")
        ],
        [
            InlineKeyboardButton("🔄 Обновить из LUIS", callback_data="vip_econ_sync")
        ]
    ])
    
    text = (
        "💼 <b>Biznesa un finanšu procesi (2 курс / 3 сем.)</b>\n"
        "🎓 <i>Персональный режим для Даниила (@Dan4iks982)</i>\n\n"
        "Ваш основной профиль (ИТ) сохранён без изменений.\n"
        "Выберите, какое расписание экономистов показать:"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

async def handle_vip_econ_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if user.id != VIP_ECON_USER_ID:
        await query.answer("⛔ Доступ только для Даниила.", show_alert=True)
        return
    
    data = query.data
    await query.answer()
    
    now = datetime.now(TIMEZONE)
    if data == "vip_econ_today":
        msg = get_schedule_for_date(now.date(), VIP_ECON_PROG, VIP_ECON_SEM)
        await query.message.reply_text(f"💼 <b>[Экономисты 2 курс]</b>\n{msg}", parse_mode="HTML")
    elif data == "vip_econ_tomorrow":
        tomorrow = now.date() + timedelta(days=1)
        msg = get_schedule_for_date(tomorrow, VIP_ECON_PROG, VIP_ECON_SEM)
        await query.message.reply_text(f"💼 <b>[Экономисты 2 курс — Завтра]</b>\n{msg}", parse_mode="HTML")
    elif data == "vip_econ_week":
        msg = get_full_week_schedule(VIP_ECON_PROG, VIP_ECON_SEM)
        await query.message.reply_text(f"💼 <b>[Экономисты 2 курс — Неделя]</b>\n{msg}", parse_mode="HTML")
    elif data == "vip_econ_radar":
        radar_data = get_live_radar(VIP_ECON_PROG, VIP_ECON_SEM)
        msg = format_radar_message(radar_data, "Biznesa un finanšu procesi (2 курс)")
        await query.message.reply_text(f"💼 <b>[Экономисты 2 курс — Радар]</b>\n{msg}", parse_mode="HTML")
    elif data == "vip_econ_sync":
        await query.message.reply_text("⏳ <i>Запускаю синхронизацию расписания D1270 из LUIS...</i>", parse_mode="HTML")
        ok, cnt, diffs = await run_live_sync(VIP_ECON_PROG, VIP_ECON_SEM)
        if ok:
            await query.message.reply_text(f"✅ Расписание экономистов успешно обновлено! Загружено <b>{cnt}</b> занятий.", parse_mode="HTML")
        else:
            await query.message.reply_text(f"❌ Ошибка обновления: {cnt}", parse_mode="HTML")


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    args = [a.strip() for a in context.args] if context.args else []
    admin_profile = None
    
    if args:
        login_input = args[0]
        pass_input = args[1] if len(args) > 1 else ""
        
        # Check login & password
        for lk, acc in ADMIN_ACCOUNTS.items():
            if lk.lower() == login_input.lower() and acc["password"] == pass_input:
                admin_profile = acc
                break
                
        if admin_profile:
            add_admin(user.id)
            await update.message.reply_text(
                f"🎉 <b>Добро пожаловать, {admin_profile['name']}!</b>\n"
                f"Вы успешно авторизованы как <b>{admin_profile['role']}</b> под логином <code>{login_input}</code>.",
                parse_mode="HTML"
            )
        elif (len(args) >= 2 and args[0].upper() == SECRET_ADMIN_PASSCODE and args[1] == SECRET_ADMIN_KEY) or \
             (len(args) == 1 and args[0] in [SECRET_ADMIN_KEY, f"{SECRET_ADMIN_PASSCODE}:{SECRET_ADMIN_KEY}"]):
            add_admin(user.id)
            await update.message.reply_text("🎉 <b>Секретный код и пароль приняты!</b> Доступ предоставлен.", parse_mode="HTML")
        else:
            await update.message.reply_text(
                "🔒 <b>Неверный логин или пароль администратора!</b>\n"
                "Использование: <code>/admin &lt;логин&gt; &lt;пароль&gt;</code>",
                parse_mode="HTML"
            )
            return
            
    if not is_user_admin(user.id):
        await update.message.reply_text(
            "🔒 <b>Панель управления администратора</b>\n\n"
            "Доступ ограничен. Для авторизации введите ваш логин и пароль:\n"
            "<code>/admin &lt;логин&gt; &lt;пароль&gt;</code>",
            parse_mode="HTML"
        )
        return

    # Update admin presence without logging into student commands statistics
    db.update_user_activity(user.id, user.username or "", chat.title or user.first_name or "")
    
    # Identify admin info
    for acc in ADMIN_ACCOUNTS.values():
        if acc["user_id"] == user.id:
            admin_profile = acc
            break
            
    adm_name = admin_profile["name"] if admin_profile else (user.first_name or "Администратор")
    adm_role = admin_profile["role"] if admin_profile else "Администратор"

    telem = get_system_telemetry()
    p_analytics = db.get_product_analytics()
    inbox = load_json(INBOX_FILE, [])
    unread = len([m for m in inbox if m.get("status") == "unread"])
    maint = is_maintenance_mode()
    
    hot_f = p_analytics.get("hot_feature", {}).get("name", "Завтра")
    hot_pct = p_analytics.get("hot_feature", {}).get("percentage", 0)

    admin_text = (
        f"👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ (PRO)</b>\n"
        f"Здравствуйте, <b>{adm_name}</b> ({adm_role})!\n"
        f"──────────────────────\n"
        f"🟢 <b>Студентов онлайн:</b> <b>{p_analytics['online_now']}</b> чел (за 10 мин)\n"
        f"📅 <b>Активно сегодня (DAU):</b> <b>{p_analytics['dau_today']}</b> чел\n"
        f"👥 <b>Всего студентов в БД:</b> <b>{p_analytics['total_users']}</b> чел\n"
        f"📊 <b>Всего событий:</b> <b>{p_analytics['total_events']}</b>\n"
        f"🔥 <b>Топ-фича:</b> {hot_f} ({hot_pct}%)\n"
        f"📬 <b>Тикетов в очереди:</b> <b>{unread}</b> новых\n\n"
        f"🖥️ <b>Сервер:</b> RAM <b>{telem['mem_used_mb']}/{telem['mem_total_mb']} MB</b> ({telem['mem_percent']}%) | CPU <b>{telem['cpu_load_1m']}</b>\n"
        f"🛠️ <b>Режим обслуживания:</b> {'🔴 <b>ВКЛЮЧЕН</b>' if maint else '🟢 <b>ВЫКЛЮЧЕН</b>'}\n"
        f"──────────────────────\n"
        f"<i>Выберите нужный раздел на кнопках ниже:</i>"
    )
    await update.message.reply_text(
        admin_text,
        parse_mode="HTML",
        reply_markup=get_admin_dashboard_keyboard(user.id)
    )

async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_admin(user.id):
        await update.message.reply_text("⛔ Доступ только для администраторов.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Формат:</b> <code>/reply &lt;user_id&gt; &lt;текст сообщения&gt;</code>\n"
            "Пример: <code>/reply 123456789 Завтра первая пара в 408 аудитории.</code>",
            parse_mode="HTML"
        )
        return

    target_id_str = context.args[0]
    reply_text = " ".join(context.args[1:])

    try:
        target_id = int(target_id_str)
    except ValueError:
        await update.message.reply_text("❌ ID пользователя должен быть числом.")
        return

    admin_name = user.first_name or "Администратор"
    target_user_lang = get_user_lang(target_id)
    formatted = locales.format_direct_message(sender=admin_name, text=reply_text, lang=target_user_lang)
    try:
        await context.bot.send_message(chat_id=target_id, text=formatted, parse_mode="HTML")
        db.record_message(admin_name, str(target_id), f"Студент {target_id}", reply_text, "ok", "outgoing")
        await update.message.reply_text(f"✅ Сообщение успешно отправлено пользователю <code>{target_id}</code> (Язык: <b>{target_user_lang.upper()}</b>)!", parse_mode="HTML")
    except Exception as e:
        err_msg = str(e).lower()
        if "blocked" in err_msg or "forbidden" in err_msg or "deactivated" in err_msg:
            db.mark_user_blocked_bot(target_id, True)
            await update.message.reply_text(f"❌ Студент <code>{target_id}</code> заблокировал бота!", parse_mode="HTML")
        else:
            await update.message.reply_text(f"❌ Ошибка отправки: {e}")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_admin(user.id):
        await update.message.reply_text("⛔ Доступ только для администраторов.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Укажите текст: <code>/broadcast &lt;текст&gt;</code>", parse_mode="HTML")
        return

    text = " ".join(context.args)
    admin_name = user.first_name or "Даниил"
    chats = load_json(CHATS_FILE, {})
    blocked = set(str(x) for x in load_json(BLOCKED_FILE, []))

    sent = 0
    for cid in chats.keys():
        if cid in blocked:
            continue
        try:
            user_lang = get_user_lang(int(cid))
            formatted = locales.get_t("broadcast_header", user_lang, sender=admin_name, text=text)
            await context.bot.send_message(chat_id=int(cid), text=formatted, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            err_msg = str(e).lower()
            if "blocked" in err_msg or "forbidden" in err_msg or "deactivated" in err_msg:
                db.mark_user_blocked_bot(int(cid), True)

    db.record_message(admin_name, "Рассылка", f"{sent} чатов", text, "ok", "outgoing")
    await update.message.reply_text(f"✅ Рассылка завершена! Доставлено в {sent} чатов.")

async def cmd_broadcast_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_admin(user.id):
        await update.message.reply_text("⛔ Доступ только для администраторов.")
        return

    full = " ".join(context.args)
    if "|" not in full:
        await update.message.reply_text("⚠️ Формат: <code>/broadcast_from Автор | Текст</code>", parse_mode="HTML")
        return

    sender_part, text_part = full.split("|", 1)
    sender = sender_part.strip()
    text = text_part.strip()

    chats = load_json(CHATS_FILE, {})
    blocked = set(str(x) for x in load_json(BLOCKED_FILE, []))

    sent = 0
    for cid in chats.keys():
        if cid in blocked:
            continue
        try:
            user_lang = get_user_lang(int(cid))
            formatted = locales.get_t("broadcast_header", user_lang, sender=sender, text=text)
            await context.bot.send_message(chat_id=int(cid), text=formatted, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            err_msg = str(e).lower()
            if "blocked" in err_msg or "forbidden" in err_msg or "deactivated" in err_msg:
                db.mark_user_blocked_bot(int(cid), True)

    db.record_message(sender, "Рассылка", f"{sent} чатов", text, "ok", "outgoing")
    await update.message.reply_text(f"✅ Рассылка от имени «{sender}» завершена! Доставлено в {sent} чатов.")

async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_admin(user.id):
        await update.message.reply_text("⛔ Доступ только для администраторов.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Формат: <code>/block &lt;user_id&gt;</code>", parse_mode="HTML")
        return
    try:
        target_id = int(context.args[0])
        db.block_user(target_id)
        blocked = load_json(BLOCKED_FILE, [])
        if target_id not in blocked and str(target_id) not in blocked:
            blocked.append(target_id)
            save_json(BLOCKED_FILE, blocked)
        await update.message.reply_text(f"⛔ Пользователь <code>{target_id}</code> заблокирован.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_user_admin(user.id):
        await update.message.reply_text("⛔ Доступ только для администраторов.")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Формат: <code>/unblock &lt;user_id&gt;</code>", parse_mode="HTML")
        return
    try:
        target_id = int(context.args[0])
        db.unblock_user(target_id)
        blocked = load_json(BLOCKED_FILE, [])
        blocked = [x for x in blocked if x != target_id and str(x) != str(target_id)]
        save_json(BLOCKED_FILE, blocked)
        await update.message.reply_text(f"✅ Пользователь <code>{target_id}</code> разблокирован.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "help")
    user_lang = get_user_lang(user.id)
    help_text = locales.get_t("help_faq", user_lang)
    await update.message.reply_text(help_text, parse_mode="HTML")

# --- Text Handler (Menu, Support states, Group Reply bridge) ---

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text.strip() if update.message and update.message.text else ""
    if not text:
        return

    # Group protection: do not allow bot in non-support groups
    if chat.type in ["group", "supergroup"] and chat.id != SUPPORT_GROUP_ID:
        try:
            await update.effective_message.reply_text(
                "ℹ️ <b>DU Schedule Bot работает только в личных сообщениях.</b>\n"
                "Пожалуйста, используйте бота в личной переписке.",
                parse_mode="HTML"
            )
            await context.bot.leave_chat(chat.id)
        except Exception:
            pass
        return

    user_lang = get_user_lang(user.id)

    # Universal Cancel Handler (catches /cancel, ./cancel, отмена, atcelt, cancel in ANY state)
    if is_cancel_message(text):
        context.user_data["state"] = None
        await update.message.reply_text(
            locales.get_t("action_cancelled", user_lang),
            parse_mode="HTML",
            reply_markup=get_main_keyboard(user.id, lang=user_lang)
        )
        return

    # If user presses any recognized action button while awaiting input, automatically clear state!
    action = locales.NAV_BUTTON_TO_ACTION.get(text)
    if action:
        context.user_data["state"] = None

    # 1. Check if message was sent in the Support Group
    if chat.id == SUPPORT_GROUP_ID:
        if update.message.reply_to_message:
            rep = update.message.reply_to_message
            if rep.from_user and rep.from_user.id == context.bot.id:
                ticket = db.get_ticket_by_group_msg(rep.message_id)
                target_user_id = None
                ticket_id = None
                if ticket:
                    target_user_id = ticket.get("user_id")
                    ticket_id = ticket.get("id")
                else:
                    m = re.search(r'ID студента:\s*<code>(\d+)</code>', rep.text_html or rep.text or "")
                    if not m:
                        m = re.search(r'<code>(\d+)</code>', rep.text_html or "")
                    if m:
                        target_user_id = int(m.group(1))

                if target_user_id:
                    admin_name = update.effective_user.first_name or "Поддержка"
                    target_user_lang = get_user_lang(target_user_id)
                    orig_text = ""
                    t_type = "support"
                    if ticket:
                        orig_text = ticket.get("message_text", "").strip()
                        t_type = ticket.get("ticket_type", "support")
                    else:
                        m_msg = re.search(r'💬 <b>Сообщение:</b>\n(.*)', rep.text_html or rep.text or "", re.DOTALL)
                        if m_msg:
                            orig_text = m_msg.group(1).strip()

                    student_text = locales.format_ticket_reply(
                        sender=admin_name,
                        ticket_id=ticket_id,
                        ticket_type=t_type,
                        orig_text=orig_text,
                        reply_text=text,
                        lang=target_user_lang
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=target_user_id,
                            text=student_text,
                            parse_mode="HTML"
                        )
                        if ticket_id:
                            db.reply_to_ticket(ticket_id, text, update.effective_user.id)
                        db.record_message(admin_name, str(target_user_id), f"Студент {target_user_id}", text, "ok", "outgoing")
                        await update.message.reply_text(f"✅ Ответ успешно доставлен студенту (ID: <code>{target_user_id}</code>, Язык: <b>{target_user_lang.upper()}</b>)!", parse_mode="HTML")
                    except Exception as e:
                        await update.message.reply_text(f"❌ Не удалось отправить ответ студенту: {e}")
                    return
        return

    # Check blocked
    if is_user_blocked(user.id):
        await update.message.reply_text(locales.get_t("user_blocked", user_lang))
        return

    # Update presence and hit count without logging a premature duplicate "text" event
    db.update_user_activity(user.id, user.username or "", chat.title or user.first_name or "")
    db.record_activity_hit()

    # Maintenance check
    if is_maintenance_mode() and not is_user_admin(user.id):
        cfg = load_json(CONFIG_FILE, {})
        msg = cfg.get("maintenance_msg") or locales.get_t("maintenance_msg", user_lang)
        await update.message.reply_text(msg)
        return

    # 2. Check if user is in awaiting state (Support / Suggestion / Teacher / Admin Broadcast / Admin Ticket Reply)
    user_state = context.user_data.get("state")
    if user_state == "awaiting_broadcast_custom_text":
        if is_cancel_message(text):
            context.user_data["state"] = None
            await update.message.reply_text("❌ Ввод текста рассылки отменен.", parse_mode="HTML", reply_markup=get_admin_dashboard_keyboard(user.id))
            return
        context.user_data["pending_broadcast_text"] = text
        context.user_data["state"] = None
        tgt = context.user_data.get("brd_target", "all")
        kb_confirm = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Подтвердить и отправить", callback_data="brd_do_send")],
            [InlineKeyboardButton("❌ Отмена", callback_data="adm_back")]
        ])
        await update.message.reply_text(
            f"📢 <b>Подтверждение рассылки:</b>\n\n"
            f"🎯 Аудитория: <b>{tgt.upper()}</b>\n"
            f"🔕 Режим: <b>Без звука (тихий push)</b>\n\n"
            f"💬 <b>Текст:</b>\n«{text}»\n\n"
            f"Нажмите кнопку для отправки:",
            parse_mode="HTML",
            reply_markup=kb_confirm
        )
        return

    if user_state and user_state.startswith("adm_reply_ticket_"):
        if is_cancel_message(text):
            context.user_data["state"] = None
            await update.message.reply_text("❌ Ответ на тикет отменен.", parse_mode="HTML", reply_markup=get_admin_dashboard_keyboard(user.id))
            return
        tid = int(user_state.split("_")[3])
        ticket = db.get_ticket(tid)
        if not ticket:
            context.user_data["state"] = None
            await update.message.reply_text("❌ Тикет не найден.", parse_mode="HTML", reply_markup=get_admin_dashboard_keyboard(user.id))
            return
        target_uid = ticket["user_id"]
        target_lang = get_user_lang(target_uid)
        admin_name = user.first_name or "Даниил"
        orig_text = ticket.get("message_text", "").strip()
        t_type = ticket.get("ticket_type", "support")
        student_text = locales.format_ticket_reply(
            sender=admin_name,
            ticket_id=tid,
            ticket_type=t_type,
            orig_text=orig_text,
            reply_text=text,
            lang=target_lang
        )
        try:
            await context.bot.send_message(chat_id=target_uid, text=student_text, parse_mode="HTML")
            db.reply_to_ticket(tid, text, user.id)
            db.record_message(admin_name, str(target_uid), f"Студент {target_uid}", text, "ok", "outgoing")
            context.user_data["state"] = None
            await update.message.reply_text(
                f"✅ Ответ успешно отправлен студенту <code>{target_uid}</code> по тикету #{tid}!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В тикеты", callback_data="adm_inbox")]])
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка отправки ответа: {e}")
        return

    if user_state == "awaiting_teacher":
        if is_cancel_message(text):
            context.user_data["state"] = None
            await update.message.reply_text(locales.get_t("action_cancelled", user_lang), reply_markup=get_main_keyboard(user.id, lang=user_lang))
            return
        await process_teacher_search(update, context, text)
        return

    if user_state in ["awaiting_support", "awaiting_suggestion"]:
        if is_cancel_message(text):
            context.user_data["state"] = None
            await update.message.reply_text(locales.get_t("action_cancelled", user_lang), reply_markup=get_main_keyboard(user.id, lang=user_lang))
            return

        warnings = db.get_user_warnings(user.id)
        if warnings >= 3:
            context.user_data["state"] = None
            await update.message.reply_text("⛔ Вы заблокированы и не можете отправлять сообщения.")
            return

        ticket_type = "support" if user_state == "awaiting_support" else "suggestion"
        ticket_id = db.create_ticket(user.id, ticket_type, text)
        prog, sem = get_user_settings(user.id)
        prog_name = PROGRAM_SHORT.get(prog, prog)
        sem_label = locales.get_semester_label(sem, user_lang)

        type_header = "🆘 <b>#ОБРАЩЕНИЕ_В_ПОДДЕРЖКУ</b>" if ticket_type == "support" else "💡 <b>#ПРЕДЛОЖЕНИЕ_ПО_УЛУЧШЕНИЮ</b>"
        group_card = (
            f"{type_header} <b>(Тикет #{ticket_id})</b>\n\n"
            f"👤 <b>От:</b> {user.first_name} {f'(@{user.username})' if user.username else ''}\n"
            f"🆔 <b>ID студента:</b> <code>{user.id}</code>\n"
            f"🎓 <b>Программа:</b> {prog_name} ({sem_label})\n"
            f"🌐 <b>Язык:</b> {user_lang.upper()}\n"
            f"⚠️ <b>Предупреждений:</b> {warnings}/3\n\n"
            f"💬 <b>Сообщение:</b>\n{text}"
        )

        btn_row2 = [InlineKeyboardButton(f"⚠️ Предупреждение ({warnings+1}/3)", callback_data=f"grp_warn_{user.id}_{ticket_id}")]
        if warnings > 0:
            btn_row2.append(InlineKeyboardButton(f"♻️ Снять страйк ({max(0, warnings-1)}/3)", callback_data=f"grp_unwarn_{user.id}_{ticket_id}"))
        btn_row2.append(InlineKeyboardButton("🚫 Заблокировать", callback_data=f"grp_block_{user.id}_{ticket_id}"))

        kb_group = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💬 Ответить", callback_data=f"grp_reply_{ticket_id}_{user.id}")
            ],
            btn_row2
        ])

        try:
            grp_msg = await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                text=group_card,
                parse_mode="HTML",
                reply_markup=kb_group
            )
            db.update_ticket_group_msg(ticket_id, grp_msg.message_id)
        except Exception as e:
            logger.error(f"Error forwarding ticket to support group: {e}")

        # Record in message history
        db.record_message(user.first_name, "Поддержка", "Поддержка бота", text, "ok", "incoming")

        context.user_data["state"] = None
        thanks_text = locales.get_t("ticket_sent", user_lang, id=ticket_id)
        await update.message.reply_text(thanks_text, parse_mode="HTML", reply_markup=get_main_keyboard(user.id, lang=user_lang))
        return

    # 3. Action Dispatcher via locales.NAV_BUTTON_TO_ACTION
    if action == "vip_econ":
        if user.id == VIP_ECON_USER_ID:
            await cmd_vip_econ(update, context)
            return
    elif action == "teacher":
        await cmd_find_teacher(update, context)
        return
    elif action == "today":
        await cmd_today(update, context)
        return
    elif action == "tomorrow":
        await cmd_tomorrow(update, context)
        return
    elif action == "week":
        await cmd_week(update, context)
        return
    elif action == "next":
        await cmd_next(update, context)
        return
    elif action == "update":
        await cmd_sync(update, context)
        return
    elif action == "select_day":
        record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "select_day")
        days_s = locales.WEEKDAYS_SHORT.get(user_lang, locales.WEEKDAYS_SHORT["ru"])
        keyboard = [
            [
                InlineKeyboardButton(days_s[0], callback_data="day_0"),
                InlineKeyboardButton(days_s[1], callback_data="day_1"),
                InlineKeyboardButton(days_s[2], callback_data="day_2")
            ],
            [
                InlineKeyboardButton(days_s[3], callback_data="day_3"),
                InlineKeyboardButton(days_s[4], callback_data="day_4"),
                InlineKeyboardButton(days_s[5], callback_data="day_5")
            ]
        ]
        await update.message.reply_text(
            locales.get_t("select_day_prompt", user_lang),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    elif action == "settings":
        await cmd_settings(update, context)
        return
    elif action == "help":
        await cmd_help(update, context)
        return
    elif action == "support":
        record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "ticket", details="Открытие поддержки")
        context.user_data["state"] = "awaiting_support"
        await update.message.reply_text(
            locales.get_t("support_prompt", user_lang),
            parse_mode="HTML"
        )
        return
    elif action == "suggest":
        record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "suggest", details="Открытие предложений")
        context.user_data["state"] = "awaiting_suggestion"
        await update.message.reply_text(
            locales.get_t("suggest_prompt", user_lang),
            parse_mode="HTML"
        )
        return
    else:
        record_activity(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, "text", details=text[:50])
        record_incoming_message(chat.id, user.id, chat.title or user.first_name, user.username, chat.type, text, is_freeform=True)
        if chat.type == "private":
            if user_lang == "lv":
                free_msg = (
                    "📩 <b>Ziņojums saņemts!</b>\n\n"
                    "Ja vēlaties uzdot jautājumu bota izstrādātājiem vai ieteikt ideju, izmantojiet izvēlni <b>⚙️ Iestatījumi -> 🆘 Atbalsts</b>.\n\n"
                    "<i>Nodarbību saraksta apskatei izmantojiet izvēlnes pogas zemāk 👇</i>"
                )
            elif user_lang == "en":
                free_msg = (
                    "📩 <b>Message received!</b>\n\n"
                    "If you would like to ask a question or propose an idea, use <b>⚙️ Settings -> 🆘 Support</b>.\n\n"
                    "<i>To view the schedule, please use the menu buttons below 👇</i>"
                )
            else:
                free_msg = (
                    "📩 <b>Сообщение получено!</b>\n\n"
                    "Если вы хотите задать вопрос создателям бота или предложить идею, нажмите <b>🆘 Поддержка</b> в меню настроек.\n\n"
                    "<i>Для просмотра расписания используйте кнопки меню 👇</i>"
                )
            await update.message.reply_text(
                free_msg,
                parse_mode="HTML",
                reply_markup=get_main_keyboard(user.id, lang=user_lang)
            )


# --- Callbacks Handler ---

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if is_user_blocked(user_id):
        await query.message.reply_text("⛔ Доступ к боту ограничен администратором.")
        return

    # No-op
    if data == "noop":
        return

    # Day selection
    if data.startswith("day_"):
        wday = int(data.split("_")[1])
        prog, sem = get_user_settings(user_id)
        user_lang = get_user_lang(user_id)
        msg = get_schedule_for_weekday(wday, prog, sem, lang=user_lang, user_id=user_id)
        await query.message.reply_text(msg, parse_mode="HTML")

    # Smart Week Switcher (Multi-week navigation up to MAX_WEEK_OFFSET)
    elif data.startswith("week_show_"):
        try:
            target_offset = int(data.split("_")[2])
        except (IndexError, ValueError):
            target_offset = 0
        target_offset = max(0, min(MAX_WEEK_OFFSET, target_offset))
        prog, sem = get_user_settings(user_id)
        user_lang = get_user_lang(user_id)
        msg = get_full_week_schedule(prog, sem, lang=user_lang, user_id=user_id, week_offset=target_offset)
        kb = get_week_navigation_keyboard(lang=user_lang, current_offset=target_offset)
        if len(msg) <= 4000:
            try:
                await query.edit_message_text(msg, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                logger.debug(f"Failed to edit week schedule message: {e}")
        else:
            parts = split_long_week_message(msg)
            try:
                await query.edit_message_text(parts[0], parse_mode="HTML")
                for i, part in enumerate(parts[1:], 1):
                    markup = kb if i == len(parts) - 1 else None
                    await query.message.reply_text(part, parse_mode="HTML", reply_markup=markup)
            except Exception as e:
                logger.debug(f"Failed to edit/send long week schedule message: {e}")

    # Patchnote acknowledgment
    elif data.startswith("pn_ack_"):
        try:
            patchnote_id = int(data.split("_")[2])
        except (IndexError, ValueError):
            patchnote_id = 0
        user_lang = get_user_lang(user_id)
        if patchnote_id:
            db.record_patchnote_view(patchnote_id, user_id)
        toast = {"ru": "✅ Спасибо! Приятного пользования ботом 🎓", "lv": "✅ Paldies! Veiksmīgu bota lietošanu 🎓", "en": "✅ Thank you! Enjoy using the bot 🎓"}.get(user_lang, "✅ Спасибо! Приятного пользования ботом 🎓")
        await query.answer(toast, show_alert=False)
        ack_btn_text = {"ru": "✅ Вы ознакомились", "lv": "✅ Esat iepazinies", "en": "✅ Acknowledged"}.get(user_lang, "✅ Вы ознакомились")
        ack_kb = InlineKeyboardMarkup([[InlineKeyboardButton(ack_btn_text, callback_data="noop")]])
        try:
            await query.edit_message_reply_markup(reply_markup=ack_kb)
        except Exception:
            pass

    # Faculty & Program Navigation
    elif data == "cfg_back" or data == "cfg_main":
        user_lang = get_user_lang(user_id)
        prog, sem = get_user_settings(user_id)
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
        sem_label = locales.get_semester_label(sem, user_lang)
        lang_name = locales.LANG_NAMES.get(user_lang, user_lang)
        text = locales.get_t("settings_title", user_lang, prog=prog_name, course=sem_label, lang_name=lang_name)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard(prog, sem, lang=user_lang, user_id=user_id))

    elif data == "toggle_notif":
        user_lang = get_user_lang(user_id)
        new_state = db.toggle_user_notifications(user_id)
        prog, sem = get_user_settings(user_id)
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
        sem_label = locales.get_semester_label(sem, user_lang)
        lang_name = locales.LANG_NAMES.get(user_lang, user_lang)
        status_str = locales.get_t("notifications_status_on", user_lang) if new_state else locales.get_t("notifications_status_off", user_lang)
        toast = locales.get_t("notifications_toggled_msg", user_lang, status=status_str).replace("<b>", "").replace("</b>", "")
        await query.answer(toast, show_alert=True)
        text = locales.get_t("settings_title", user_lang, prog=prog_name, course=sem_label, lang_name=lang_name)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard(prog, sem, lang=user_lang, user_id=user_id))

    elif data == "cfg_lang":
        user_lang = get_user_lang(user_id)
        text = locales.get_t("choose_language_prompt", user_lang)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_language_keyboard(user_lang))

    elif data.startswith("setlang_"):
        new_lang = data.split("_")[1]
        if new_lang not in ["ru", "lv", "en"]:
            new_lang = "ru"
        db.set_user_language(user_id, new_lang)
        prog, sem = get_user_settings(user_id)
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if new_lang == "ru" else PROGRAMS.get(prog, prog)
        sem_label = locales.get_semester_label(sem, new_lang)
        lang_name = locales.LANG_NAMES.get(new_lang, new_lang)

        # Notify user with updated main keyboard in selected language
        confirm_text = locales.get_t("language_changed", new_lang)
        await query.message.reply_text(
            confirm_text,
            parse_mode="HTML",
            reply_markup=get_main_keyboard(user_id, lang=new_lang)
        )

        # Refresh settings message
        text = locales.get_t("settings_title", new_lang, prog=prog_name, course=sem_label, lang_name=lang_name)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard(prog, sem, lang=new_lang, user_id=user_id))

    elif data == "cfg_faculties":
        user_lang = get_user_lang(user_id)
        text = {"ru": "🏛️ <b>Выберите ваш факультет в Даугавпилсском университете:</b>", "lv": "🏛️ <b>Izvēlieties savu fakultāti Daugavpils Universitātē:</b>", "en": "🏛️ <b>Choose your faculty at Daugavpils University:</b>"}.get(user_lang, "🏛️ <b>Выберите ваш факультет:</b>")
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_faculties_keyboard(user_lang))

    elif data.startswith("fak_"):
        parts = data.split("_")
        faculty_id = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0
        user_lang = get_user_lang(user_id)
        fak = next((f for f in FACULTIES if f.get("id") == faculty_id), None)
        fak_name = (fak.get("name_ru", fak.get("name", "")) if user_lang == "ru" else fak.get("name", "")) if fak else "Факультет"
        title_fak = {"ru": f"📚 <b>{fak_name}</b>\n\nВыберите вашу программу обучения:", "lv": f"📚 <b>{fak_name}</b>\n\nIzvēlieties savu studiju programmu:", "en": f"📚 <b>{fak_name}</b>\n\nChoose your study program:"}.get(user_lang, f"📚 <b>{fak_name}</b>\n\nВыберите программу:")
        await query.edit_message_text(title_fak, parse_mode="HTML", reply_markup=get_programs_keyboard(faculty_id, page, lang=user_lang))

    # Program selection
    elif data.startswith("setprog_"):
        prog_code = data.split("_")[1]
        set_user_program(user_id, prog_code)
        db.set_user_subgroup(user_id, "")
        prog, sem = get_user_settings(user_id)
        user_lang = get_user_lang(user_id)
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
        mapped_cur = SEMESTER_MAP.get(sem, 3)

        c1 = f"{'✅ ' if mapped_cur == 1 else ''}{locales.get_semester_label(1, user_lang)}"
        c2 = f"{'✅ ' if mapped_cur == 3 else ''}{locales.get_semester_label(3, user_lang)}"
        c3 = f"{'✅ ' if mapped_cur == 5 else ''}{locales.get_semester_label(5, user_lang)}"
        c4 = f"{'✅ ' if mapped_cur == 7 else ''}{locales.get_semester_label(7, user_lang)}"
        back_lbl = {"ru": "⚙️ Открыть все настройки", "lv": "⚙️ Visi iestatījumi", "en": "⚙️ All Settings"}.get(user_lang, "⚙️ Настройки")

        title_sel = {
            "ru": f"🎉 <b>Программа успешно выбрана!</b>\n🎓 <b>{prog_name}</b>\n\nТеперь выберите ваш курс и семестр:",
            "lv": f"🎉 <b>Programma veiksmīgi izvēlēta!</b>\n🎓 <b>{prog_name}</b>\n\nTagad izvēlieties savu kursu un semestri:",
            "en": f"🎉 <b>Program successfully selected!</b>\n🎓 <b>{prog_name}</b>\n\nNow select your study year and semester:"
        }.get(user_lang, f"🎉 <b>Программа успешно выбрана!</b>\n🎓 <b>{prog_name}</b>\n\nТеперь выберите ваш курс:")

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(c1, callback_data="setsem_1"),
                InlineKeyboardButton(c2, callback_data="setsem_3")
            ],
            [
                InlineKeyboardButton(c3, callback_data="setsem_5"),
                InlineKeyboardButton(c4, callback_data="setsem_7")
            ],
            [
                InlineKeyboardButton(back_lbl, callback_data="cfg_back")
            ]
        ])
        await query.edit_message_text(title_sel, parse_mode="HTML", reply_markup=kb)

    # Semester selection
    elif data.startswith("setsem_"):
        sem_num = int(data.split("_")[1])
        set_user_semester(user_id, sem_num)
        prog, sem = get_user_settings(user_id)
        user_lang = get_user_lang(user_id)
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
        sem_label = locales.get_semester_label(sem, user_lang)
        lang_name = locales.LANG_NAMES.get(user_lang, user_lang)

        # If this program & semester has multiple groups and user doesn't have a valid subgroup set, prompt to choose
        subgroups = get_program_subgroups(prog, sem)
        if len(subgroups) > 1:
            subgroup = db.get_user_subgroup(user_id)
            if not subgroup or (subgroup.upper() != "ALL" and subgroup not in subgroups):
                text = locales.get_t("subgroup_prompt_generic", user_lang, prog=prog_name, course=sem_label)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_subgroup_selection_keyboard(prog, sem, current_subgroup="", lang=user_lang))
                return

        text = locales.get_t("settings_title", user_lang, prog=prog_name, course=sem_label, lang_name=lang_name)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_settings_keyboard(prog, sem, lang=user_lang, user_id=user_id))

    # Subgroup / Stream selection
    elif data == "cfg_subgroup":
        user_lang = get_user_lang(user_id)
        prog, sem = get_user_settings(user_id)
        subgroups = get_program_subgroups(prog, sem)
        if len(subgroups) > 1:
            subgroup = db.get_user_subgroup(user_id)
            prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
            sem_label = locales.get_semester_label(sem, user_lang)
            text = locales.get_t("subgroup_prompt_generic", user_lang, prog=prog_name, course=sem_label)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_subgroup_selection_keyboard(prog, sem, current_subgroup=subgroup, lang=user_lang))
        else:
            await query.answer(locales.get_t("subgroup_single_info", user_lang), show_alert=True)

    elif data == "cfg_subgroup_single":
        user_lang = get_user_lang(user_id)
        await query.answer(locales.get_t("subgroup_single_info", user_lang), show_alert=True)

    elif data.startswith("setsubgrp_"):
        code = data.split("_", 1)[1]
        db.set_user_subgroup(user_id, code)
        prog, sem = get_user_settings(user_id)
        user_lang = get_user_lang(user_id)
        prog_name = PROGRAM_SHORT.get(prog, PROGRAMS.get(prog, prog)) if user_lang == "ru" else PROGRAMS.get(prog, prog)
        sem_label = locales.get_semester_label(sem, user_lang)
        lang_name = locales.LANG_NAMES.get(user_lang, user_lang)

        sg_full = locales.get_subgroup_label(prog, code, lang=user_lang, short=False)
        conf_msg = locales.get_t("subgroup_saved", user_lang, subgroup=sg_full)
        base_title = locales.get_t("settings_title", user_lang, prog=prog_name, course=sem_label, lang_name=lang_name)
        full_text = f"{conf_msg}\n\n{base_title}"
        await query.edit_message_text(full_text, parse_mode="HTML", reply_markup=get_settings_keyboard(prog, sem, lang=user_lang, user_id=user_id))


    # Support / Suggestion triggers
    elif data in ["btn_support", "cfg_support"]:
        user_lang = get_user_lang(user_id)
        context.user_data["state"] = "awaiting_support"
        await query.message.reply_text(
            locales.get_t("support_prompt", user_lang),
            parse_mode="HTML"
        )

    elif data in ["btn_suggest", "cfg_suggest"]:
        user_lang = get_user_lang(user_id)
        context.user_data["state"] = "awaiting_suggestion"
        await query.message.reply_text(
            locales.get_t("suggest_prompt", user_lang),
            parse_mode="HTML"
        )


    # Group Moderation Actions
    elif data.startswith("grp_reply_"):
        await query.answer("💡 Чтобы ответить студенту, просто используйте функцию Reply (Ответить) в Telegram на сообщение с тикетом выше!", show_alert=True)

    elif data.startswith("grp_warn_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        ticket_id = int(parts[3])
        target_lang = get_user_lang(target_uid)
        current_warn, is_banned = db.add_warning(target_uid, admin_id=user_id, reason="Предупреждение модератора в группе поддержки")
        
        if is_banned:
            blocked = load_json(BLOCKED_FILE, [])
            if target_uid not in blocked and str(target_uid) not in blocked:
                blocked.append(target_uid)
                save_json(BLOCKED_FILE, blocked)
            try:
                await context.bot.send_message(
                    chat_id=target_uid,
                    text=locales.get_t("user_banned_3warns_msg", target_lang),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await query.answer("Пользователь заблокирован (3/3)!", show_alert=True)
            await query.message.reply_text(f"🚫 Пользователю <code>{target_uid}</code> выдано 3-е предупреждение. Он <b>АВТОМАТИЧЕСКИ ЗАБЛОКИРОВАН</b> в боте!", parse_mode="HTML")
        else:
            try:
                await context.bot.send_message(
                    chat_id=target_uid,
                    text=locales.get_t("user_warned_msg", target_lang, warn=current_warn),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            await query.answer(f"Выдано предупреждение {current_warn}/3!", show_alert=False)
            await query.message.reply_text(f"⚠️ Пользователю <code>{target_uid}</code> выдано предупреждение <b>{current_warn}/3</b>.", parse_mode="HTML")

    elif data.startswith("grp_unwarn_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        ticket_id = int(parts[3])
        target_lang = get_user_lang(target_uid)
        new_warn, was_unbanned = db.remove_warning(target_uid, admin_id=user_id)
        if was_unbanned:
            blocked = load_json(BLOCKED_FILE, [])
            blocked = [x for x in blocked if str(x) != str(target_uid)]
            save_json(BLOCKED_FILE, blocked)
            chats = load_json(CHATS_FILE, {})
            if str(target_uid) in chats:
                chats[str(target_uid)]["is_blocked"] = False
                save_json(CHATS_FILE, chats)
        try:
            notif_text = locales.get_t("user_unwarned_msg", target_lang, warn=new_warn)
            if was_unbanned:
                notif_text += locales.get_t("user_unblocked_note", target_lang)
            await context.bot.send_message(
                chat_id=target_uid,
                text=notif_text,
                parse_mode="HTML"
            )
        except Exception:
            pass
        await query.answer(f"Снято 1 предупреждение! Осталось: {new_warn}/3", show_alert=False)
        await query.message.reply_text(f"♻️ Пользователю <code>{target_uid}</code> <b>снято 1 предупреждение</b> (теперь <b>{new_warn}/3</b>).", parse_mode="HTML")

    elif data.startswith("grp_block_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        target_lang = get_user_lang(target_uid)
        db.block_user(target_uid)
        blocked = load_json(BLOCKED_FILE, [])
        if target_uid not in blocked and str(target_uid) not in blocked:
            blocked.append(target_uid)
            save_json(BLOCKED_FILE, blocked)
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text=locales.get_t("user_manually_blocked_msg", target_lang),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await query.answer("Пользователь заблокирован!", show_alert=True)
        await query.message.reply_text(f"🚫 Пользователь <code>{target_uid}</code> заблокирован вручную администратором.", parse_mode="HTML")

    # Teacher Search Callbacks
    elif data.startswith("tch_catalog_"):
        page = int(data.split("_")[2])
        user_lang = get_user_lang(user_id)
        await send_teacher_catalog(query, context, page=page, is_edit=True, lang=user_lang)
        return

    elif data.startswith("tch_view_"):
        teacher_id = data.split("_")[2]
        user_lang = get_user_lang(user_id)
        await send_teacher_schedule(query, context, teacher_id=teacher_id, is_edit=True, lang=user_lang)
        return

    elif data.startswith("tch_refresh_"):
        teacher_id = data.split("_")[2]
        user_lang = get_user_lang(user_id)
        await send_teacher_schedule(query, context, teacher_id=teacher_id, is_edit=True, lang=user_lang)
        return

    elif data == "tch_search_again":
        user_lang = get_user_lang(user_id)
        context.user_data["state"] = "awaiting_teacher"
        msg_text = locales.get_t("teacher_search_title", user_lang)
        btn_cat_txt = locales.get_t("teacher_catalog_btn", user_lang)
        reply_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_cat_txt, callback_data="tch_catalog_0")]
        ])
        try:
            await query.edit_message_text(msg_text, parse_mode="HTML", reply_markup=reply_kb)
        except Exception:
            await query.message.reply_text(msg_text, parse_mode="HTML", reply_markup=reply_kb)
        return


    elif data == "tch_cancel":
        try:
            await query.message.delete()
        except Exception:
            user_lang = get_user_lang(user_id)
            lbl = {"ru": "Поиск преподавателя закрыт.", "lv": "Pasniedzēja meklēšana ir aizvērta.", "en": "Faculty search closed."}.get(user_lang, "Поиск преподавателя закрыт.")
            await query.edit_message_text(lbl)
        return

    # VIP Economists Callbacks
    elif data.startswith("vip_econ_"):
        await handle_vip_econ_callback(update, context)
        return

    # Admin Panel Callbacks
    elif data == "adm_online_users":
        if not is_user_admin(user_id):
            return
        online = db.get_online_users_list(minutes=30)
        if not online:
            await query.message.reply_text("🟢 Сейчас нет активных студентов за последние 30 минут.", parse_mode="HTML")
            return
        text = f"🟢 <b>Студенты онлайн / недавняя активность ({len(online)} чел):</b>\n\n"
        for u in online[:15]:
            badge = "🟢 В сети" if u.get("is_online") else f"🟡 {u.get('last_active_human')}"
            action_desc = f" ({u.get('last_action')})" if u.get('last_action') else ""
            uname = f"@{u['username']}" if u.get("username") else f"ID {u['user_id']}"
            course = u.get("course", 2)
            prog = u.get("program_code", "D01B9")
            text += f"• <b>{u.get('first_name') or 'Студент'}</b> ({uname}) — <b>{course} курс</b> ({prog})\n  └ {badge}{action_desc}\n"
        await query.message.reply_text(text, parse_mode="HTML")

    elif data == "adm_feature_stats" or data == "adm_stats":
        if not is_user_admin(user_id):
            return
        pa = db.get_product_analytics()
        f_text = ""
        for idx, f in enumerate(pa.get("features", [])[:8], 1):
            f_text += f"{idx}. <b>{f['name']}</b>: <code>{f['count']}</code> ({f['percentage']}%)\n"
        if not f_text:
            f_text = "Нет собранных данных по фичам."
            
        c_dist = pa.get("course_distribution", {})
        c_text = f"1 курс: <b>{c_dist.get(1, 0)}</b> | 2 курс: <b>{c_dist.get(2, 0)}</b> | 3 курс: <b>{c_dist.get(3, 0)}</b> | 4 курс: <b>{c_dist.get(4, 0)}</b>"
        
        report = (
            f"📊 <b>ПРОДУКТОВАЯ АНАЛИТИКА БОТА</b>\n\n"
            f"👥 Активно сегодня (DAU): <b>{pa['dau_today']}</b> чел\n"
            f"🟢 Онлайн прямо сейчас: <b>{pa['online_now']}</b> чел\n"
            f"📈 Всего зафиксировано событий: <b>{pa['total_events']}</b>\n\n"
            f"🔥 <b>РЕЙТИНГ ПОПУЛЯРНОСТИ ФУНКЦИЙ:</b>\n{f_text}\n"
            f"🎓 <b>Распределение студентов по курсам:</b>\n{c_text}\n\n"
            f"💡 <i>Студенты чаще всего смотрят «Завтра» и ищут преподавателей.</i>"
        )
        await query.message.reply_text(report, parse_mode="HTML")

    elif data == "adm_quick_broadcast":
        if not is_user_admin(user_id):
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Всем студентам", callback_data="brd_tgt_all")],
            [
                InlineKeyboardButton("🎓 1 курс", callback_data="brd_tgt_c1"),
                InlineKeyboardButton("🎓 2 курс", callback_data="brd_tgt_c2")
            ],
            [
                InlineKeyboardButton("🎓 3 курс", callback_data="brd_tgt_c3"),
                InlineKeyboardButton("🎓 4 курс", callback_data="brd_tgt_c4")
            ],
            [InlineKeyboardButton("🔙 Назад в админку", callback_data="adm_back")]
        ])
        await query.message.reply_text(
            "📢 <b>Быстрая рассылка из Telegram:</b>\n\n"
            "Выберите целевую аудиторию для рассылки, либо используйте веб-панель (порт 8085) для точечной настройки с опросами:",
            parse_mode="HTML",
            reply_markup=kb
        )

    elif data.startswith("brd_tgt_"):
        if not is_user_admin(user_id):
            return
        tgt = data.split("_")[2]
        target_labels = {
            "all": "👥 Всем студентам (вся база)",
            "c1": "🎓 1 курс (1-2 сем.)",
            "c2": "🎓 2 курс (3-4 сем.)",
            "c3": "🎓 3 курс (5-6 сем.)",
            "c4": "🎓 4 курс (7-8 сем.)"
        }
        lbl = target_labels.get(tgt, tgt)
        all_u = db.get_all_users()
        if tgt == "all":
            cnt = len(all_u)
        else:
            c_num = int(tgt[1])
            cnt = len([u for u in all_u if ((int(u.get("semester") or 3) + 1) // 2) == c_num])
            
        context.user_data["brd_target"] = tgt
        
        kb_opts = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚫 Отмена пары", callback_data="brd_apply_cancel"),
                InlineKeyboardButton("💻 Teams (онлайн)", callback_data="brd_apply_online")
            ],
            [
                InlineKeyboardButton("🚪 Смена аудитории", callback_data="brd_apply_room"),
                InlineKeyboardButton("🔄 Расписание обновлено", callback_data="brd_apply_update")
            ],
            [
                InlineKeyboardButton("✍️ Ввести свой текст сообщения", callback_data="brd_apply_custom")
            ],
            [
                InlineKeyboardButton("🔙 Назад к выбору аудитории", callback_data="adm_quick_broadcast")
            ]
        ])
        await query.message.reply_text(
            f"📢 <b>Целевая аудитория:</b> {lbl}\n"
            f"👥 Получателей: <b>{cnt} студентов</b>\n"
            f"🔕 Доставка: <b>Без звука (Silent Push)</b>\n\n"
            f"<i>Выберите быстрый шаблон старосты или напишите свой текст:</i>",
            parse_mode="HTML",
            reply_markup=kb_opts
        )

    elif data.startswith("brd_apply_"):
        if not is_user_admin(user_id):
            return
        tpl = data.split("_")[2]
        tpl_texts = {
            "cancel": "Внимание! Занятие по предмету сегодня отменено по решению преподавателя. Отдыхаем!",
            "online": "Внимание! Сегодняшнее занятие пройдет в дистанционном формате в MS Teams. Ссылка на подключение в чате курса.",
            "room": "Внимание! Сменилась аудитория: занятие перенесено в другую аудиторию. Проверьте обновленное расписание в боте.",
            "update": "В расписание внесены актуальные изменения из системы LUIS. Пожалуйста, обновите расписание в боте через кнопку 🔄 Обновить!"
        }
        if tpl == "custom":
            context.user_data["state"] = "awaiting_broadcast_custom_text"
            await query.message.reply_text(
                "✍️ <b>Введите текст объявления для рассылки:</b>\n\n"
                "Отправьте текст следующим сообщением прямо в этот чат (или напишите <code>отмена</code>):",
                parse_mode="HTML"
            )
            return
            
        chosen_text = tpl_texts.get(tpl, "")
        context.user_data["pending_broadcast_text"] = chosen_text
        tgt = context.user_data.get("brd_target", "all")
        
        kb_confirm = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Подтвердить и отправить", callback_data="brd_do_send")],
            [InlineKeyboardButton("❌ Отмена", callback_data="adm_back")]
        ])
        await query.message.reply_text(
            f"📢 <b>Подтверждение рассылки:</b>\n\n"
            f"🎯 Аудитория: <b>{tgt.upper()}</b>\n"
            f"🔕 Режим: <b>Без звука (тихий push)</b>\n\n"
            f"💬 <b>Текст:</b>\n«{chosen_text}»\n\n"
            f"Нажмите кнопку для отправки:",
            parse_mode="HTML",
            reply_markup=kb_confirm
        )

    elif data == "brd_do_send":
        if not is_user_admin(user_id):
            return
        tgt = context.user_data.get("brd_target", "all")
        msg_text = context.user_data.get("pending_broadcast_text", "")
        if not msg_text:
            await query.answer("Нет текста для рассылки!", show_alert=True)
            return
            
        all_u = db.get_all_users()
        if tgt == "all":
            target_users = all_u
        else:
            c_num = int(tgt[1])
            target_users = [u for u in all_u if ((int(u.get("semester") or 3) + 1) // 2) == c_num]
            
        blocked = set(str(x) for x in load_json(BLOCKED_FILE, []))
        admin_name = update.effective_user.first_name or "Даниил"
        
        sent = 0
        status_msg = await query.message.reply_text("⏳ <i>Отправка рассылки студентам...</i>", parse_mode="HTML")
        for u in target_users:
            uid = u["user_id"]
            if str(uid) in blocked or u.get("is_blocked"):
                continue
            u_lang = u.get("language") or "ru"
            formatted = locales.get_t("broadcast_header", u_lang, sender=admin_name, text=msg_text)
            try:
                await context.bot.send_message(chat_id=uid, text=formatted, parse_mode="HTML", disable_notification=True)
                sent += 1
                await asyncio.sleep(0.04)
            except Exception as e:
                err_msg = str(e).lower()
                if "blocked" in err_msg or "forbidden" in err_msg or "deactivated" in err_msg:
                    db.mark_user_blocked_bot(uid, True)
                    
        db.record_message(admin_name, f"Рассылка ({tgt})", f"{sent} чатов", msg_text, "ok", "outgoing")
        await status_msg.edit_text(
            f"✅ <b>Рассылка успешно выполнена!</b>\n\n"
            f"Доставлено студентам: <b>{sent} чел</b> (без звука 🔕)",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В админку", callback_data="adm_back")]])
        )

    elif data == "adm_vip_econ":
        if user_id == VIP_ECON_USER_ID:
            await cmd_vip_econ(update, context)
            return

    elif data == "adm_inbox":
        if not is_user_admin(user_id):
            return
        tickets = db.get_all_tickets()[:5]
        if not tickets:
            await query.message.reply_text("📭 Тикетов пока нет.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В админку", callback_data="adm_back")]]))
            return
        await query.message.reply_text("📩 <b>Последние обращения студентов:</b>", parse_mode="HTML")
        for t in tickets:
            tid = t["id"]
            status_icon = "🔴 Открыт" if t.get("status") == "open" else "🟢 Закрыт/Отвечен"
            date_s = t["created_at"][:16].replace("T", " ") if t.get("created_at") else "—"
            res = (
                f"🎫 <b>Тикет #{tid} ({t['ticket_type']})</b>\n"
                f"👤 Студент: <code>{t['user_id']}</code> | {date_s}\n"
                f"Статус: <b>{status_icon}</b>\n"
                f"💬 «{t['message_text'][:100]}»"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💬 Ответить", callback_data=f"adm_tk_rep_{tid}"),
                    InlineKeyboardButton("✅ Закрыть", callback_data=f"adm_tk_cls_{tid}")
                ]
            ])
            await query.message.reply_text(res, parse_mode="HTML", reply_markup=kb)

    elif data.startswith("adm_tk_rep_"):
        if not is_user_admin(user_id):
            return
        tid = int(data.split("_")[3])
        context.user_data["state"] = f"adm_reply_ticket_{tid}"
        await query.message.reply_text(
            f"✍️ <b>Ответ на тикет #{tid}:</b>\n\n"
            f"Введите текст ответа следующим сообщением (или напишите <code>отмена</code>):",
            parse_mode="HTML"
        )

    elif data.startswith("adm_tk_cls_"):
        if not is_user_admin(user_id):
            return
        tid = int(data.split("_")[3])
        db.close_ticket(tid)
        await query.answer(f"Тикет #{tid} закрыт!", show_alert=True)
        await query.message.reply_text(f"✅ Тикет #{tid} отмечен как решённый.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В тикеты", callback_data="adm_inbox")]]))

    elif data == "adm_patchnotes":
        if not is_user_admin(user_id):
            return
        pns = db.get_patchnotes(limit=1)
        if not pns:
            await query.message.reply_text("📢 Патчноуты еще не публиковались. Вы можете создать первый в веб-панели (порт 8085).", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад в админку", callback_data="adm_back")]]))
            return
        pn = pns[0]
        title = pn.get("title", "Обновление бота")
        total = pn.get("total_sent", 1)
        views = pn.get("views_count", 0)
        pct = pn.get("views_percent", 0)
        silent_str = "🔕 Без звука" if pn.get("is_silent") else "🔔 Обычный"
        is_test_str = "🧪 Тестовый (Даниил)" if pn.get("is_test") else "📢 Для всех студентов"
        date_str = pn.get("created_at", "")[:16].replace("T", " ")

        pn_text = (
            f"📢 <b>ПОСЛЕДНИЙ РЕЛИЗ / ПАТЧНОУТ:</b>\n\n"
            f"📌 <b>{title}</b>\n"
            f"📅 Дата: <code>{date_str}</code> | {silent_str}\n"
            f"🎯 Тип: <b>{is_test_str}</b>\n\n"
            f"📊 <b>Ознакомились с обновлением:</b>\n"
            f"<b>{views} из {total} ({pct}%)</b> студентов\n"
        )
        kb_pn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧪 Отправить тест мне (Даниилу)", callback_data=f"adm_pn_test_{pn['id']}")],
            [InlineKeyboardButton("🔙 Назад в админку", callback_data="adm_back")]
        ])
        await query.message.reply_text(pn_text, parse_mode="HTML", reply_markup=kb_pn)

    elif data.startswith("adm_pn_test_"):
        if not is_user_admin(user_id):
            return
        pn_id = int(data.split("_")[3])
        pn_item = db.get_patchnote_stats(pn_id)
        if pn_item:
            title = pn_item["title"]
            text = pn_item["content"]
            btn_text = pn_item.get("button_text") or "👍 Понятно / Ознакомился"
            sender = pn_item.get("sender_name") or "Даниил"
            full_msg = f"📢 <b>{title}</b>\n<i>От: {sender}</i>\n\n{text}"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data=f"pn_ack_{pn_id}")]])
            try:
                await context.bot.send_message(chat_id=user_id, text=full_msg, parse_mode="HTML", reply_markup=kb, disable_notification=True)
                await query.answer("✅ Тестовый патчноут отправлен вам в чат без звука!", show_alert=True)
            except Exception as e:
                await query.answer(f"Ошибка: {e}", show_alert=True)

    elif data == "adm_overrides":
        if not is_user_admin(user_id):
            return
        overrides = load_json(OVERRIDES_FILE, [])
        if not overrides:
            await query.message.reply_text(
                "🛠️ <b>Активные ручные правки расписания:</b>\n\nПравок нет. Вы можете добавить их через веб-панель (порт 8085).",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад в админку", callback_data="adm_back")]])
            )
            return
        msg = f"🛠️ <b>Активные ручные правки расписания ({len(overrides)}):</b>\n\n"
        kb_rows = []
        for o in overrides:
            oid = o.get("id", "")
            subj = o.get("subj", "Без названия")
            room = o.get("new_room", "")
            note = o.get("note", "")
            msg += f"• <b>{subj}</b> {f'({room})' if room else ''}\n  └ <i>{note}</i>\n"
            kb_rows.append([InlineKeyboardButton(f"🗑️ Удалить: {subj[:20]}", callback_data=f"adm_del_ovr_{oid}")])
        kb_rows.append([InlineKeyboardButton("🔙 Назад в админку", callback_data="adm_back")])
        await query.message.reply_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_rows))

    elif data.startswith("adm_del_ovr_"):
        if not is_user_admin(user_id):
            return
        del_id = data.split("_")[3]
        overrides = load_json(OVERRIDES_FILE, [])
        overrides = [o for o in overrides if str(o.get("id")) != str(del_id)]
        save_json(OVERRIDES_FILE, overrides)
        await query.answer("Правка удалена!", show_alert=True)
        await query.message.reply_text("✅ Правка успешно удалена из расписания.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 В админку", callback_data="adm_back")]]))

    elif data == "adm_back":
        if not is_user_admin(user_id):
            return
        context.user_data["state"] = None
        p_analytics = db.get_product_analytics()
        inbox = load_json(INBOX_FILE, [])
        unread = len([m for m in inbox if m.get("status") == "unread"])
        maint = is_maintenance_mode()
        hot_f = p_analytics.get("hot_feature", {}).get("name", "Завтра")
        hot_pct = p_analytics.get("hot_feature", {}).get("percentage", 0)
        telem = get_system_telemetry()
        admin_text = (
            f"👑 <b>ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ (PRO)</b>\n"
            f"──────────────────────\n"
            f"🟢 <b>Студентов онлайн:</b> <b>{p_analytics['online_now']}</b> чел (за 10 мин)\n"
            f"📅 <b>Активно сегодня (DAU):</b> <b>{p_analytics['dau_today']}</b> чел\n"
            f"👥 <b>Всего студентов в БД:</b> <b>{p_analytics['total_users']}</b> чел\n"
            f"📊 <b>Всего событий:</b> <b>{p_analytics['total_events']}</b>\n"
            f"🔥 <b>Топ-фича:</b> {hot_f} ({hot_pct}%)\n"
            f"📬 <b>Тикетов в очереди:</b> <b>{unread}</b> новых\n\n"
            f"🖥️ <b>Сервер:</b> RAM <b>{telem['mem_used_mb']}/{telem['mem_total_mb']} MB</b> ({telem['mem_percent']}%) | CPU <b>{telem['cpu_load_1m']}</b>\n"
            f"🛠️ <b>Режим обслуживания:</b> {'🔴 <b>ВКЛЮЧЕН</b>' if maint else '🟢 <b>ВЫКЛЮЧЕН</b>'}\n"
            f"──────────────────────\n"
            f"<i>Выберите нужный раздел на кнопках ниже:</i>"
        )
        try:
            await query.edit_message_text(admin_text, parse_mode="HTML", reply_markup=get_admin_dashboard_keyboard(user_id))
        except Exception:
            await query.message.reply_text(admin_text, parse_mode="HTML", reply_markup=get_admin_dashboard_keyboard(user_id))

    elif data == "adm_users":
        if not is_user_admin(user_id):
            return
        users_list = db.get_all_users()[:10]
        res = "👥 <b>Пользователи бота:</b>\n\n"
        for u in users_list:
            b_mark = " [⛔ БАН]" if u.get("is_blocked") else ""
            res += (
                f"• <b>{u.get('first_name') or 'ID ' + str(u['user_id'])}</b> (@{u.get('username') or '—'}){b_mark}\n"
                f"  ID: <code>{u['user_id']}</code> | Курс: {u.get('program_code', 'D01B9')} ({u.get('semester', 3)} сем.)\n"
            )
        res += "\n<i>Управление: <code>/block &lt;id&gt;</code> или <code>/unblock &lt;id&gt;</code></i>"
        await query.message.reply_text(res, parse_mode="HTML")

    elif data == "adm_broadcast":
        if not is_user_admin(user_id):
            return
        await query.message.reply_text(
            "📢 <b>Инструкция по рассылке объявлений:</b>\n\n"
            "1. <b>Обычная рассылка:</b>\n"
            "<code>/broadcast Текст объявления</code>\n\n"
            "2. <b>Рассылка с выбором имени отправителя:</b>\n"
            "<code>/broadcast_from Даниил | Завтра пара онлайн в Teams</code>\n\n"
            "3. <b>Через веб-панель:</b>\n"
            "Раздел «Массовые объявления» на порту 8085.",
            parse_mode="HTML"
        )

    elif data == "adm_toggle_maint":
        if not is_user_admin(user_id):
            return
        curr = is_maintenance_mode()
        set_maintenance_mode(not curr)
        status_text = "🔴 ВКЛЮЧЕН" if not curr else "🟢 ВЫКЛЮЧЕН"
        await query.message.reply_text(f"🛠️ Режим техобслуживания теперь: <b>{status_text}</b>", parse_mode="HTML")

    elif data == "adm_forcesync":
        if not is_user_admin(user_id):
            return
        await query.message.reply_text("⚡ <b>Запуск обновления базы из LUIS...</b>", parse_mode="HTML")
        ok, cnt, diffs = await run_live_sync(DEFAULT_PROGRAM, DEFAULT_SEMESTER)
        if ok:
            await query.message.reply_text(f"✅ База LUIS успешно обновлена! Загружено <b>{cnt}</b> занятий.", parse_mode="HTML")
        else:
            await query.message.reply_text(f"❌ Ошибка LUIS: {cnt}", parse_mode="HTML")

    elif data == "adm_close":
        try:
            await query.message.delete()
        except Exception:
            await query.edit_message_text("Панель администратора закрыта.")

# --- Background Schedule Monitor Job (Cancellations & Reschedules) ---

async def schedule_monitor_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Periodic job (every 30 mins) checking active programs/semesters for cancellations or reschedules.
    Sends targeted push notifications to students of the affected group.
    """
    now = datetime.now(TIMEZONE)
    # Run on weekdays (Monday 0 - Friday 4) between 07:30 and 19:30
    if now.weekday() >= 5:
        return
    if not (time(7, 30) <= now.time() <= time(19, 30)):
        return

    active_groups = db.get_active_programs_and_semesters()
    logger.info(f"Schedule monitor job: checking {len(active_groups)} active groups...")

    for prog_code, sem_num in active_groups:
        try:
            ok, cnt, diffs = await run_live_sync(prog_code, sem_num)
            if not ok:
                continue

            events = get_events_for(prog_code, sem_num)
            # Find cancelled or rescheduled events
            changed_events = [
                e for e in events
                if (e.get("is_cancelled") or e.get("is_rescheduled")) and not e.get("is_moved_away")
            ]

            for ev in changed_events:
                ev_id = ev.get("id") or "unknown"
                change_type = "cancelled" if ev.get("is_cancelled") else "rescheduled"
                ch_date = ev.get("date").strftime("%d.%m.%Y") if ev.get("date") else ""
                ch_time = ev.get("time", "")
                change_hash = f"{prog_code}_{sem_num}_{ev_id}_{change_type}_{ch_date}_{ch_time}"

                if not db.is_change_notified(change_hash):
                    target_students = db.get_users_for_program_semester(prog_code, sem_num)
                    # STRICT SAFETY RULE: Only alert test whitelist (Daniel & Danik Sinica) - NEVER spam all students!
                    target_students = [s for s in target_students if s["user_id"] in TEST_ALERT_USER_IDS]
                    if not target_students:
                        db.mark_change_notified(ev_id, prog_code, sem_num, change_type, change_hash)
                        continue

                    logger.info(f"New {change_type} detected: {ev.get('subj')} ({ev_id}) for {prog_code} sem {sem_num}. Alerting {len(target_students)} test admins.")

                    for st in target_students:
                        st_id = st["user_id"]
                        st_lang = st.get("language") or "ru"

                        title_tag = locales.get_t("auto_alert_cancel_title", st_lang) if change_type == "cancelled" else locales.get_t("auto_alert_resched_title", st_lang)
                        prog_label = PROGRAM_SHORT.get(prog_code, PROGRAMS.get(prog_code, prog_code)) if st_lang == "ru" else PROGRAMS.get(prog_code, prog_code)
                        sem_label = locales.get_semester_label(sem_num, st_lang)
                        grp_str = f"{prog_label} ({sem_label})"

                        ev_text = format_event(ev, lang=st_lang)
                        alert_msg = (
                            f"{title_tag} <i>[TEST NOTIFICATION]</i>\n\n"
                            f"🎓 <b>{grp_str}</b>\n"
                            f"📅 <b>{ch_date}</b>\n\n"
                            f"{ev_text}"
                        )

                        try:
                            await context.bot.send_message(chat_id=st_id, text=alert_msg, parse_mode="HTML")
                            await asyncio.sleep(0.05)
                        except Exception as send_err:
                            logger.warning(f"Could not send test alert to admin {st_id}: {send_err}")

                    db.mark_change_notified(ev_id, prog_code, sem_num, change_type, change_hash)
        except Exception as group_err:
            logger.error(f"Error checking changes for {prog_code} sem {sem_num}: {group_err}")

        await asyncio.sleep(3)

# --- Background Auto-Sync Job (Silent, No spam broadcasts) ---

async def scheduled_sync_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Executing scheduled LUIS sync job (silent)...")
    ok, count_or_err, diffs = await run_live_sync(DEFAULT_PROGRAM, DEFAULT_SEMESTER)
    if ok:
        logger.info(f"LUIS sync successful: {count_or_err} events synced. Diffs detected: {len(diffs) if diffs else 0}.")
    else:
        logger.warning(f"LUIS scheduled sync warning: {count_or_err}")

def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is not set in .env")
        return

    # Initialize SQLite database
    db.init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Public Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["econ", "econom", "bsp2"], cmd_vip_econ))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("segodnya", cmd_today))
    app.add_handler(CommandHandler("tomorrow", cmd_tomorrow))
    app.add_handler(CommandHandler("zavtra", cmd_tomorrow))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("nedelya", cmd_week))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("now", cmd_now))
    app.add_handler(CommandHandler("seychas", cmd_now))
    app.add_handler(CommandHandler("radar", cmd_now))
    app.add_handler(CommandHandler("find", cmd_find))
    app.add_handler(CommandHandler(["teacher", "teachers", "prepod", "pasniedzejs", "find_teacher", "search_teacher"], cmd_find_teacher))
    app.add_handler(CommandHandler("search", cmd_find))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("update", cmd_sync))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler(["faq", "spravka"], cmd_help))
    app.add_handler(CommandHandler(["cancel", "stop", "exit", "otmena"], cmd_cancel))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Admin Commands
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("reply", cmd_reply))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("broadcast_from", cmd_broadcast_from))
    app.add_handler(CommandHandler("block", cmd_block))
    app.add_handler(CommandHandler("unblock", cmd_unblock))

    # Messages & Callbacks
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Background Sync Schedule (silent background sync every 4h and 07:00 AM, NO spam monitor)
    if app.job_queue:
        app.job_queue.run_repeating(scheduled_sync_job, interval=14400, first=3600)
        app.job_queue.run_daily(scheduled_sync_job, time=time(7, 0, tzinfo=TIMEZONE))

    logger.info("DU Schedule Bot successfully started and polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
