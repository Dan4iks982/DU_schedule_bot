import os
import sys
import json
import uuid
import asyncio
import subprocess
import logging
import shutil
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
load_dotenv()
import db
import locales

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("web_admin")

TIMEZONE = ZoneInfo("Europe/Riga")
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOG_FILE = DATA_DIR / "bot.log"
CHATS_FILE = DATA_DIR / "registered_chats.json"
LAST_SYNC_FILE = DATA_DIR / "last_sync.json"
BLOCKED_FILE = DATA_DIR / "blocked_users.json"
STATS_FILE = DATA_DIR / "stats.json"
CONFIG_FILE = DATA_DIR / "config.json"
OVERRIDES_FILE = DATA_DIR / "manual_overrides.json"
HISTORY_FILE = DATA_DIR / "message_history.json"
INBOX_FILE = DATA_DIR / "inbox_messages.json"
TEMPLATES_DIR = BASE_DIR / "templates"

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
ACTIVE_SESSIONS = {}

DU_PROGRAMS_MAP = {
    "D01B9": "Информационные технологии (PBSP D01B9)",
    "D1270": "Biznesa un finanšu procesi (PBSP D1270)",
    "D1240": "Psiholoģija (BSP D1240)",
    "D02DO": "Valodu un kultūras studijas (BSP D02DO)",
    "D0154": "Fizioterapija (PBSP D0154)"
}
DU_FACULTY_MAP = {}
du_p_file = DATA_DIR / "du_programs.json"
if du_p_file.exists():
    try:
        with open(du_p_file, "r", encoding="utf-8") as _f:
            _d = json.load(_f)
            for _fak in _d.get("faculties", []):
                _fak_name = _fak.get("name_ru") or _fak.get("name", "Факультет")
                for _p in _fak.get("programs", []):
                    DU_PROGRAMS_MAP[_p["code"]] = _p.get("name_ru", _p.get("name", _p["code"]))
                    DU_FACULTY_MAP[_p["code"]] = _fak_name
    except Exception:
        pass


MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
    'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
    'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

WEEKDAY_RU = {
    0: "Понедельник", 1: "Вторник", 2: "Среда",
    3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"
}

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("BOT_TOKEN="):
                    BOT_TOKEN = line.strip().split("=", 1)[1].strip('"\'')

bot_process: Optional[subprocess.Popen] = None
bot_started_at: Optional[datetime] = None
is_manually_stopped = False

app = FastAPI(title="LU Schedule Bot Admin Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_json(file_path: Path, default=None):
    if default is None:
        default = {}
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(file_path: Path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_maintenance_mode() -> bool:
    cfg = load_json(CONFIG_FILE, {})
    return bool(cfg.get("maintenance_mode", False))

def set_maintenance_mode(enabled: bool):
    cfg = load_json(CONFIG_FILE, {})
    cfg["maintenance_mode"] = enabled
    save_json(CONFIG_FILE, cfg)

def start_bot_process():
    global bot_process, bot_started_at, is_manually_stopped
    if bot_process and bot_process.poll() is None:
        return "Already running"

    is_manually_stopped = False
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(LOG_FILE, "a", encoding="utf-8")

    python_bin = sys.executable
    logger.info(f"Starting bot process with {python_bin}...")
    bot_process = subprocess.Popen(
        [python_bin, str(BASE_DIR / "bot.py")],
        cwd=str(BASE_DIR),
        stdout=log_fp,
        stderr=subprocess.STDOUT,
        text=True
    )
    bot_started_at = datetime.now(TIMEZONE)
    return "Started"

def stop_bot_process():
    global bot_process, is_manually_stopped
    is_manually_stopped = True
    if bot_process and bot_process.poll() is None:
        logger.info("Stopping bot process...")
        bot_process.terminate()
        try:
            bot_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bot_process.kill()
        return "Stopped"
    return "Not running"

def get_system_telemetry():
    telemetry = {
        "mem_total_mb": 0,
        "mem_used_mb": 0,
        "mem_percent": 0,
        "cpu_load_1m": 0.0,
        "cpu_load_5m": 0.0,
        "cpu_load_15m": 0.0,
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
            telemetry["cpu_load_5m"] = float(loads[1])
            telemetry["cpu_load_15m"] = float(loads[2])
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

def get_live_radar(prog_code: str = "D01B9"):
    events_file = DATA_DIR / f"events_{prog_code}.json"
    if not events_file.exists():
        return {"status": "none", "current_class": None, "next_class": None, "now_time": ""}
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            raw_events = json.load(f)
    except Exception:
        return {"status": "none", "current_class": None, "next_class": None, "now_time": ""}

    overrides = load_json(OVERRIDES_FILE, [])

    events = []
    for e in raw_events:
        sp = (e.get("start") or "").split()
        if len(sp) >= 5:
            mon_str, day_num, year_num, t_str = sp[1], int(sp[2]), int(sp[3]), sp[4][:5]
            ev_date = date(year_num, MONTH_MAP.get(mon_str, 9), day_num)

            end_str = e.get("end") or ""
            sp_end = end_str.split()
            end_t = sp_end[4][:5] if len(sp_end) >= 5 else ""
            if not end_t:
                try:
                    sh, sm = map(int, t_str.split(":"))
                    em = sm + 95
                    end_t = f"{sh + em // 60:02d}:{em % 60:02d}"
                except Exception:
                    end_t = t_str

            parts = [p.strip() for p in (e.get("title") or "").split("\n") if p.strip()]
            subj = parts[0] if parts else "Занятие"
            room = parts[1] if len(parts) > 1 else ""
            raw = e.get("raw", {})
            change = raw.get("changetext", "").strip()
            parc_tips = raw.get("parc_tips", "").strip()
            cnames = e.get("className", [])
            if isinstance(cnames, str):
                cnames = [cnames]
            cnames_set = set(cnames)
            if parc_tips == "Pārcelta" or "tips-R" in cnames_set:
                continue

            for ov in overrides:
                ov_d = (ov.get("date") or "").strip()
                ov_s = (ov.get("subj") or "").strip().lower()
                if ov_d and ev_date.strftime("%Y-%m-%d") != ov_d:
                    continue
                if ov_s and ov_s not in subj.lower():
                    continue
                change = f"[РУЧНОЕ ИЗМЕНЕНИЕ] {ov.get('note', '')}"
                if ov.get("new_room"):
                    room = ov["new_room"].strip()

            events.append({
                "date": ev_date,
                "weekday": ev_date.weekday(),
                "time": t_str,
                "end_time": end_t,
                "subj": subj,
                "room": room,
                "type": e.get("raw", {}).get("lulecturetype", "").strip().replace("\n", " "),
                "change": change
            })

    now = datetime.now(TIMEZONE)
    today = now.date()
    current_time_str = now.strftime("%H:%M")
    today_events = [ev for ev in events if ev["date"] == today]
    today_events.sort(key=lambda x: x["time"])

    current_class = None
    next_class = None

    for ev in today_events:
        st_t = ev["time"]
        en_t = ev["end_time"]
        if st_t <= current_time_str <= en_t:
            try:
                sh, sm = map(int, st_t.split(":"))
                eh, em = map(int, en_t.split(":"))
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
                "date": ev["date"].strftime("%Y-%m-%d"),
                "remaining_min": rem_min,
                "progress_pct": pct
            }
            break

    for ev in today_events:
        if ev["time"] > current_time_str:
            try:
                sh, sm = map(int, ev["time"].split(":"))
                st_dt = datetime.combine(today, time(sh, sm), tzinfo=TIMEZONE)
                starts_in = max(0, int((st_dt - now).total_seconds() // 60))
            except Exception:
                starts_in = 0
            next_class = {
                **ev,
                "date": ev["date"].strftime("%Y-%m-%d"),
                "starts_in_min": starts_in,
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
                    "date": next_d.strftime("%Y-%m-%d"),
                    "when": f"{wname}, {next_d.strftime('%d.%m')}"
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

async def watchdog_task():
    while True:
        await asyncio.sleep(5)
        if not is_manually_stopped:
            if bot_process is None or bot_process.poll() is not None:
                logger.warning("Bot process died unexpectedly, restarting...")
                start_bot_process()

@app.on_event("startup")
async def startup_event():
    start_bot_process()
    asyncio.create_task(watchdog_task())

@app.on_event("shutdown")
def shutdown_event():
    stop_bot_process()

# --- API Endpoints ---

@app.get("/api/status")
def api_status():
    status = "stopped"
    pid = None
    uptime = None
    if not is_manually_stopped and bot_process and bot_process.poll() is None:
        status = "running"
        pid = bot_process.pid
        if bot_started_at:
            delta = datetime.now(TIMEZONE) - bot_started_at
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            mins, secs = divmod(remainder, 60)
            uptime = f"{hours}ч {mins}м {secs}с"
    elif not is_manually_stopped:
        status = "dead"

    last_sync = load_json(LAST_SYNC_FILE, {})
    chats = load_json(CHATS_FILE, {})
    stats = load_json(STATS_FILE, {})
    blocked = load_json(BLOCKED_FILE, [])
    config = load_json(CONFIG_FILE, {})
    inbox = load_json(INBOX_FILE, [])
    unread_inbox = len([m for m in inbox if m.get("status") == "unread"])

    return {
        "status": status,
        "pid": pid,
        "uptime": uptime,
        "last_sync": last_sync.get("last_sync"),
        "event_count": last_sync.get("event_count", 0),
        "chats_count": len(chats),
        "blocked_count": len(blocked),
        "maintenance_mode": config.get("maintenance_mode", False),
        "unread_inbox": unread_inbox,
        "total_inbox": len(inbox),
        "radar": get_live_radar("D01B9"),
        "total_requests": stats.get("total_requests", 0),
        "commands": stats.get("commands", {}),
        "telemetry": get_system_telemetry(),
        "server_time": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/api/radar")
def api_radar():
    return get_live_radar("D01B9")

@app.post("/api/bot/restart")
def api_restart():
    stop_bot_process()
    res = start_bot_process()
    return {"result": "restarted", "detail": res}

@app.post("/api/bot/start")
def api_start():
    res = start_bot_process()
    return {"result": res}

@app.post("/api/bot/stop")
def api_stop():
    res = stop_bot_process()
    return {"result": res}

@app.post("/api/sync")
async def api_sync():
    logger.info("Admin triggered manual LUIS sync...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(BASE_DIR / "scraper.js"),
            "D01B9",
            "3",
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        out_str = stdout.decode("utf-8", errors="ignore")
        if proc.returncode == 0 and "success\":true" in out_str:
            stop_bot_process()
            start_bot_process()
            return {"success": True, "message": "Синхронизация завершена успешно!"}
        else:
            return {"success": False, "message": stderr.decode("utf-8", errors="ignore") or out_str}
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- User Management & Blocking ---

class BlockRequest(BaseModel):
    user_id: int
    reason: Optional[str] = ""

@app.get("/api/users")
def api_users():
    chats = load_json(CHATS_FILE, {})
    blocked = load_json(BLOCKED_FILE, [])
    blocked_set = set(str(x) for x in blocked)

    result = []
    for cid, info in chats.items():
        is_blk = cid in blocked_set
        result.append({
            "id": int(cid) if cid.lstrip("-").isdigit() else cid,
            "title": info.get("title", "Unknown"),
            "username": info.get("username", ""),
            "type": info.get("type", "private"),
            "request_count": info.get("request_count", 0),
            "first_seen": info.get("first_seen", ""),
            "last_active": info.get("last_active", ""),
            "is_blocked": is_blk
        })
    return result

class WarnRequest(BaseModel):
    user_id: int
    reason: Optional[str] = "Предупреждение из панели управления"

class TicketReplyRequest(BaseModel):
    ticket_id: int
    message: str
    sender_name: Optional[str] = "Даниил"

@app.post("/api/users/warn")
async def api_warn_user(req: WarnRequest):
    current_warn, is_banned = db.add_warning(req.user_id, admin_id=0, reason=req.reason)
    user_lang = db.get_user_language(req.user_id)
    msg = ""
    if is_banned:
        db.block_user(req.user_id)
        blocked = load_json(BLOCKED_FILE, [])
        if req.user_id not in blocked and str(req.user_id) not in blocked:
            blocked.append(req.user_id)
            save_json(BLOCKED_FILE, blocked)
        chats = load_json(CHATS_FILE, {})
        if str(req.user_id) in chats:
            chats[str(req.user_id)]["is_blocked"] = True
            save_json(CHATS_FILE, chats)
        msg = f"Пользователю {req.user_id} выдано 3-е предупреждение. Он АВТОМАТИЧЕСКИ ЗАБЛОКИРОВАН!"
        if BOT_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": req.user_id,
                            "text": locales.get_t("user_banned_3warns_msg", user_lang),
                            "parse_mode": "HTML"
                        }
                    )
            except Exception:
                pass
    else:
        msg = f"Выдано предупреждение ({current_warn}/3) пользователю {req.user_id}"
        if BOT_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": req.user_id,
                            "text": locales.get_t("user_warned_msg", user_lang, warn=current_warn),
                            "parse_mode": "HTML"
                        }
                    )
            except Exception:
                pass
    return {"success": True, "warnings": current_warn, "is_blocked": is_banned, "message": msg}

class RemoveWarnRequest(BaseModel):
    user_id: int

@app.post("/api/users/remove_warning")
async def api_remove_warning(req: RemoveWarnRequest):
    new_warn, was_unblocked = db.remove_warning(req.user_id, admin_id=0)
    user_lang = db.get_user_language(req.user_id)

    if was_unblocked:
        blocked = load_json(BLOCKED_FILE, [])
        uid_str = str(req.user_id)
        blocked = [x for x in blocked if str(x) != uid_str]
        save_json(BLOCKED_FILE, blocked)
        chats = load_json(CHATS_FILE, {})
        if uid_str in chats:
            chats[uid_str]["is_blocked"] = False
            save_json(CHATS_FILE, chats)

    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                notif_text = locales.get_t("user_unwarned_msg", user_lang, warn=new_warn)
                if was_unblocked:
                    notif_text += locales.get_t("user_unblocked_note", user_lang)
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": req.user_id,
                        "text": notif_text,
                        "parse_mode": "HTML"
                    }
                )
        except Exception:
            pass

    msg = f"Снято 1 предупреждение с пользователя {req.user_id} (теперь {new_warn}/3)."
    if was_unblocked:
        msg += " Пользователь автоматически разблокирован!"

    return {
        "success": True,
        "warnings": new_warn,
        "was_unblocked": was_unblocked,
        "message": msg
    }

@app.post("/api/tickets/reply")
async def api_reply_ticket(req: TicketReplyRequest):
    ticket = db.get_ticket(req.ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Тикет не найден")
    sender = req.sender_name.strip() if req.sender_name else "Даниил"
    user_id = ticket["user_id"]
    user_lang = db.get_user_language(user_id)
    db.reply_to_ticket(req.ticket_id, req.message, admin_id=0)
    db.record_message(sender, str(user_id), f"Студент {user_id}", req.message, "ok", "outgoing")

    orig_msg = ticket.get("message_text", "").strip() if ticket else ""
    t_type = ticket.get("ticket_type", "support") if ticket else "support"
    formatted_reply = locales.format_ticket_reply(
        sender=sender,
        ticket_id=req.ticket_id,
        ticket_type=t_type,
        orig_text=orig_msg,
        reply_text=req.message,
        lang=user_lang
    )

    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": user_id,
                        "text": formatted_reply,
                        "parse_mode": "HTML"
                    }
                )
                if res.status_code != 200:
                    err_text = res.text.lower()
                    if "blocked" in err_text or "forbidden" in err_text or "deactivated" in err_text:
                        db.mark_user_blocked_bot(user_id, True)
        except Exception as e:
            err_msg = str(e).lower()
            if "blocked" in err_msg or "forbidden" in err_msg or "deactivated" in err_msg:
                db.mark_user_blocked_bot(user_id, True)
            return {"success": False, "message": f"Ошибка отправки в Telegram: {e}"}
    return {"success": True, "message": f"Ответ успешно отправлен студенту по тикету #{req.ticket_id}!"}

@app.post("/api/bot/toggle_maintenance")
def api_toggle_maintenance():
    curr = is_maintenance_mode()
    set_maintenance_mode(not curr)
    return {"success": True, "maintenance_mode": not curr}

@app.post("/api/users/block")
def api_block_user(req: BlockRequest):
    db.block_user(req.user_id)
    blocked = load_json(BLOCKED_FILE, [])
    uid_str = str(req.user_id)
    if uid_str not in [str(x) for x in blocked]:
        blocked.append(req.user_id)
        save_json(BLOCKED_FILE, blocked)

    chats = load_json(CHATS_FILE, {})
    if uid_str in chats:
        chats[uid_str]["is_blocked"] = True
        save_json(CHATS_FILE, chats)

    logger.info(f"Blocked user: {req.user_id}")
    return {"success": True, "message": f"Пользователь {req.user_id} заблокирован"}

@app.post("/api/users/unblock")
def api_unblock_user(req: BlockRequest):
    db.unblock_user(req.user_id)
    blocked = load_json(BLOCKED_FILE, [])
    blocked = [x for x in blocked if str(x) != str(req.user_id)]
    save_json(BLOCKED_FILE, blocked)

    chats = load_json(CHATS_FILE, {})
    uid_str = str(req.user_id)
    if uid_str in chats:
        chats[uid_str]["is_blocked"] = False
        save_json(CHATS_FILE, chats)

    logger.info(f"Unblocked user: {req.user_id}")
    return {"success": True, "message": f"Пользователь {req.user_id} разблокирован"}

@app.get("/api/users/blocked_bot")
def api_get_blocked_bot_users():
    return db.get_bot_blocked_users()

@app.post("/api/users/{user_id}/unmark_blocked")
def api_unmark_blocked_bot_user(user_id: int):
    db.mark_user_blocked_bot(user_id, False)
    return {"success": True, "message": f"Пользователь {user_id} отмечен как разблокировавший бота"}

# --- Incoming Messages & Live Dialogue ---

class ReadInboxRequest(BaseModel):
    message_id: Optional[str] = None
    user_id: Optional[int] = None
    all: Optional[bool] = False

@app.get("/api/inbox")
def api_get_inbox():
    inbox = load_json(INBOX_FILE, [])
    unread_count = len([m for m in inbox if m.get("status") == "unread"])
    return {
        "total": len(inbox),
        "unread": unread_count,
        "messages": list(reversed(inbox[-300:]))
    }

@app.post("/api/inbox/read")
def api_mark_inbox_read(req: ReadInboxRequest):
    inbox = load_json(INBOX_FILE, [])
    for m in inbox:
        if req.all:
            m["status"] = "read"
        elif req.message_id and m.get("id") == req.message_id:
            m["status"] = "read"
        elif req.user_id and m.get("user_id") == req.user_id:
            m["status"] = "read"
    save_json(INBOX_FILE, inbox)
    return {"success": True}

@app.delete("/api/inbox/{msg_id}")
def api_delete_inbox(msg_id: str):
    inbox = load_json(INBOX_FILE, [])
    inbox = [m for m in inbox if str(m.get("id")) != str(msg_id)]
    save_json(INBOX_FILE, inbox)
    return {"success": True}

@app.get("/api/conversations")
def api_get_conversations():
    inbox = load_json(INBOX_FILE, [])
    chats = load_json(CHATS_FILE, {})
    users_map = {}

    for m in inbox:
        uid = m.get("user_id")
        if not uid:
            continue
        if uid not in users_map:
            users_map[uid] = {
                "user_id": uid,
                "user_name": m.get("user_name") or chats.get(str(uid), {}).get("title", f"ID {uid}"),
                "username": m.get("username") or chats.get(str(uid), {}).get("username", ""),
                "chat_type": m.get("chat_type", "private"),
                "last_message": m.get("text", ""),
                "last_time": m.get("time", ""),
                "unread_count": 0
            }
        else:
            users_map[uid]["last_message"] = m.get("text", "")
            users_map[uid]["last_time"] = m.get("time", "")
        if m.get("status") == "unread":
            users_map[uid]["unread_count"] += 1

    for cid, info in chats.items():
        try:
            uid = int(cid)
        except Exception:
            continue
        if uid not in users_map:
            users_map[uid] = {
                "user_id": uid,
                "user_name": info.get("title", f"ID {uid}"),
                "username": info.get("username", ""),
                "chat_type": info.get("type", "private"),
                "last_message": "—",
                "last_time": info.get("last_active", ""),
                "unread_count": 0
            }

    conv_list = list(users_map.values())
    conv_list.sort(key=lambda x: (x["unread_count"] > 0, x["last_time"]), reverse=True)
    return conv_list

@app.get("/api/conversations/{user_id}")
def api_get_conversation_thread(user_id: int):
    inbox = load_json(INBOX_FILE, [])
    history = load_json(HISTORY_FILE, [])
    thread = []

    for m in inbox:
        if m.get("user_id") == user_id or m.get("chat_id") == user_id:
            thread.append({
                "type": "incoming",
                "id": m.get("id"),
                "time": m.get("time"),
                "sender_name": m.get("user_name"),
                "text": m.get("text"),
                "is_command": m.get("is_command", False),
                "is_question": m.get("is_question", False),
                "status": m.get("status")
            })

    for h in history:
        rec = str(h.get("recipient", ""))
        if rec == str(user_id):
            thread.append({
                "type": "outgoing",
                "time": h.get("time"),
                "sender_name": h.get("sender", "Староста"),
                "text": h.get("message"),
                "status": h.get("status", "ok")
            })

    thread.sort(key=lambda x: x.get("time", ""))
    return thread

# --- Direct & Broadcast Messaging ---

class DirectMessageRequest(BaseModel):
    user_id: int
    message: str
    sender_name: Optional[str] = "Даниил"

@app.post("/api/message/user")
async def api_message_user(req: DirectMessageRequest):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Текст сообщения не может быть пустым")

    sender = req.sender_name.strip() if req.sender_name and req.sender_name.strip() else "Даниил"
    user_lang = db.get_user_language(req.user_id)
    formatted_msg = locales.format_direct_message(sender=sender, text=req.message, lang=user_lang)

    chats = load_json(CHATS_FILE, {})
    user_info = chats.get(str(req.user_id), {})
    user_title = user_info.get("title", f"ID {req.user_id}")

    success = False
    error_msg = ""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            res = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": req.user_id,
                    "text": formatted_msg,
                    "parse_mode": "HTML"
                }
            )
            if res.status_code == 200:
                success = True
            else:
                data = res.json()
                error_msg = data.get("description", f"HTTP {res.status_code}")
                if "blocked" in error_msg.lower() or "forbidden" in error_msg.lower() or "deactivated" in error_msg.lower():
                    db.mark_user_blocked_bot(req.user_id, True)
        except Exception as e:
            error_msg = str(e)
            if "blocked" in error_msg.lower() or "forbidden" in error_msg.lower() or "deactivated" in error_msg.lower():
                db.mark_user_blocked_bot(req.user_id, True)

    # Record in SQLite and JSON
    try:
        db.record_message(sender, str(req.user_id), user_title, req.message.strip(), "ok" if success else "err", "outgoing")
    except Exception as e:
        logger.error(f"Error saving message to DB: {e}")

    history = load_json(HISTORY_FILE, [])
    history.append({
        "time": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "target": f"{user_title}",
        "recipient": str(req.user_id),
        "sender": sender,
        "message": req.message.strip(),
        "status": "ok" if success else "err"
    })
    save_json(HISTORY_FILE, history[-300:])

    # Mark user's incoming messages as replied
    inbox = load_json(INBOX_FILE, [])
    for m in inbox:
        if m.get("user_id") == req.user_id and m.get("status") == "unread":
            m["status"] = "replied"
    save_json(INBOX_FILE, inbox)

    if success:
        return {"success": True, "message": "Сообщение успешно отправлено!"}
    else:
        return {"success": False, "message": f"Ошибка отправки: {error_msg}"}

class BroadcastRequest(BaseModel):
    message: str
    sender_name: Optional[str] = "Даниил"
    target: str = "all"  # all, groups, private, selected_users, courses, programs
    selected_users: Optional[List[int]] = None
    target_courses: Optional[List[int]] = None
    target_semesters: Optional[List[int]] = None
    target_programs: Optional[List[str]] = None
    poll_options: Optional[List[str]] = None
    disable_notification: Optional[bool] = False

@app.post("/api/broadcast")
async def api_broadcast(req: BroadcastRequest):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Текст сообщения не может быть пустым")

    chats = load_json(CHATS_FILE, {})
    blocked = set(str(x) for x in load_json(BLOCKED_FILE, []))

    targets = []
    target_desc = "Всем"
    db_users_map = {u["user_id"]: u for u in db.get_all_users()}

    if req.target == "selected_users":
        if not req.selected_users:
            return {"success": False, "message": "Не выбрано ни одного пользователя для точечной рассылки"}
        for uid in req.selected_users:
            cid = str(uid)
            if cid not in blocked:
                targets.append(cid)
        target_desc = f"Выбранным ({len(targets)} чел.)"

    elif req.target == "courses":
        target_courses = set(req.target_courses or [])
        target_sems = set(req.target_semesters or [])
        if not target_courses and not target_sems:
            return {"success": False, "message": "Не выбран ни один курс или семестр для рассылки"}

        for cid, info in chats.items():
            if cid in blocked or info.get("type") != "private":
                continue
            uid = int(cid) if cid.lstrip("-").isdigit() else None
            u_db = db_users_map.get(uid)
            user_sem = int(u_db.get("semester", 3)) if u_db else 3
            user_course = (user_sem + 1) // 2
            if user_course in target_courses or user_sem in target_sems:
                targets.append(cid)
        c_names = ", ".join([f"{c} курс" for c in sorted(target_courses)])
        target_desc = f"Курсы: {c_names}" if c_names else "Выбранные курсы"

    elif req.target == "programs":
        target_progs = set(p.strip().upper() for p in (req.target_programs or []))
        if not target_progs:
            return {"success": False, "message": "Не выбрана ни одна программа обучения"}

        for cid, info in chats.items():
            if cid in blocked or info.get("type") != "private":
                continue
            uid = int(cid) if cid.lstrip("-").isdigit() else None
            u_db = db_users_map.get(uid)
            user_prog = (u_db.get("program_code", "D01B9") if u_db else "D01B9").upper()
            if user_prog in target_progs:
                targets.append(cid)
        p_names = ", ".join(sorted(target_progs))
        target_desc = f"Программы: {p_names}"

    else:
        for cid, info in chats.items():
            if cid in blocked:
                continue
            ctype = info.get("type", "private")
            if req.target == "groups" and ctype not in ["group", "supergroup"]:
                continue
            if req.target == "private" and ctype != "private":
                continue
            targets.append(cid)
        if req.target == "groups":
            target_desc = "Групповые чаты"
        elif req.target == "private":
            target_desc = "Личные сообщения"
        else:
            target_desc = "Всем студентам"

    if not targets:
        return {"success": False, "message": f"Нет доступных получателей для рассылки ({target_desc})"}

    sender = req.sender_name.strip() if req.sender_name and req.sender_name.strip() else "Даниил"
    formatted_msg = f"📢 <b>Объявление от {sender}:</b>\n\n{req.message.strip()}"

    reply_markup = None
    poll_id = None
    if req.poll_options and len(req.poll_options) >= 2:
        poll_id = db.create_poll(req.message.strip(), req.poll_options, sender, req.target)
        inline_keyboard = []
        row = []
        for idx, opt in enumerate(req.poll_options):
            row.append({"text": opt, "callback_data": f"poll_vote_{poll_id}_{idx}"})
            if len(row) == 2:
                inline_keyboard.append(row)
                row = []
        if row:
            inline_keyboard.append(row)
        reply_markup = {"inline_keyboard": inline_keyboard}

    sent = 0
    failed = 0

    async with httpx.AsyncClient(timeout=10) as client:
        for cid in targets:
            try:
                user_lang = db.get_user_language(int(cid)) or "ru"
                user_formatted_msg = locales.get_t("broadcast_header", user_lang, sender=sender, text=req.message.strip())
                payload = {
                    "chat_id": int(cid),
                    "text": user_formatted_msg,
                    "parse_mode": "HTML"
                }
                if req.disable_notification:
                    payload["disable_notification"] = True
                if reply_markup:
                    payload["reply_markup"] = reply_markup

                res = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=payload
                )
                if res.status_code == 200:
                    sent += 1
                else:
                    failed += 1
                    err_text = res.text.lower()
                    if "blocked" in err_text or "forbidden" in err_text or "deactivated" in err_text:
                        db.mark_user_blocked_bot(int(cid), True)
            except Exception as e:
                failed += 1
                err_text = str(e).lower()
                if "blocked" in err_text or "forbidden" in err_text or "deactivated" in err_text:
                    db.mark_user_blocked_bot(int(cid), True)
            await asyncio.sleep(0.05)

    try:
        db.record_message(sender, f"Рассылка ({target_desc})", f"{sent} чатов", req.message.strip(), "ok" if sent > 0 else "err", "outgoing")
    except Exception as e:
        logger.error(f"Error saving broadcast to DB: {e}")

    history = load_json(HISTORY_FILE, [])
    history.append({
        "time": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "target": f"Рассылка ({target_desc})",
        "recipient": f"{sent} адресатов",
        "sender": sender,
        "message": req.message.strip(),
        "has_poll": bool(poll_id),
        "status": "ok" if sent > 0 else "err"
    })
    save_json(HISTORY_FILE, history[-300:])

    return {
        "success": True,
        "sent": sent,
        "failed": failed,
        "total": len(targets),
        "target_desc": target_desc,
        "poll_id": poll_id,
        "message": f"Рассылка ({target_desc}) завершена! Доставлено: {sent} из {len(targets)}" + (" (опрос прикреплён)" if poll_id else "")
    }

# --- Patchnotes Management Endpoints ---

class PatchnoteRequest(BaseModel):
    title: str
    text: str
    button_text: Optional[str] = "👍 Понятно"
    is_silent: Optional[bool] = True
    target: str = "test"  # "test" (only Daniil 879446270) or "all" (all students)
    sender_name: Optional[str] = "Даниил"

@app.post("/api/patchnotes/send")
async def api_patchnotes_send(req: PatchnoteRequest):
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="Заголовок не может быть пустым")
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Текст патчноута не может быть пустым")

    sender = req.sender_name.strip() if req.sender_name and req.sender_name.strip() else "Даниил"
    btn_text = req.button_text.strip() if req.button_text and req.button_text.strip() else "👍 Понятно"
    is_test = (req.target == "test")

    chats = load_json(CHATS_FILE, {})
    blocked = set(str(x) for x in load_json(BLOCKED_FILE, []))

    targets = []
    if is_test:
        # Test mode: ONLY Daniil
        targets = ["879446270"]
    else:
        for cid, info in chats.items():
            if cid in blocked or info.get("type") != "private":
                continue
            targets.append(cid)

    if not targets:
        return {"success": False, "message": "Нет доступных получателей"}

    # Create patchnote in DB to acquire ID
    pn_id = db.create_patchnote(
        title=req.title.strip(),
        content=req.text.strip(),
        button_text=btn_text,
        is_silent=bool(req.is_silent),
        is_test=is_test,
        sender_name=sender,
        total_sent=len(targets)
    )

    reply_markup = {
        "inline_keyboard": [
            [{"text": btn_text, "callback_data": f"pn_ack_{pn_id}"}]
        ]
    }

    sent = 0
    failed = 0

    async with httpx.AsyncClient(timeout=10) as client:
        for cid in targets:
            try:
                formatted_msg = f"📢 <b>{req.title.strip()}</b>\n\n{req.text.strip()}"
                payload = {
                    "chat_id": int(cid),
                    "text": formatted_msg,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup
                }
                if req.is_silent:
                    payload["disable_notification"] = True

                res = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=payload
                )
                if res.status_code == 200:
                    sent += 1
                else:
                    failed += 1
                    err_text = res.text.lower()
                    if "blocked" in err_text or "forbidden" in err_text or "deactivated" in err_text:
                        db.mark_user_blocked_bot(int(cid), True)
            except Exception as e:
                failed += 1
                err_text = str(e).lower()
                if "blocked" in err_text or "forbidden" in err_text or "deactivated" in err_text:
                    db.mark_user_blocked_bot(int(cid), True)
            await asyncio.sleep(0.05)

    db.update_patchnote_sent_count(pn_id, sent)

    target_label = "Тест (Даниил)" if is_test else f"Всем студентам ({sent} чел.)"
    try:
        db.record_message(sender, f"Патчноут ({target_label})", req.title.strip(), req.text.strip(), "ok" if sent > 0 else "err", "outgoing")
    except Exception as e:
        logger.error(f"Error saving patchnote to DB messages_history: {e}")

    return {
        "success": True,
        "patchnote_id": pn_id,
        "sent": sent,
        "failed": failed,
        "is_test": is_test,
        "message": f"Патчноут успешно отправлен: доставлено {sent}, ошибок {failed} ({target_label})"
    }

@app.get("/api/patchnotes/list")
async def api_patchnotes_list():
    pns = db.get_patchnotes(limit=50)
    return {"success": True, "patchnotes": pns}

@app.get("/api/patchnotes/{patchnote_id}/stats")
async def api_patchnotes_stats(patchnote_id: int):
    stats = db.get_patchnote_stats(patchnote_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Патчноут не найден")
    return {"success": True, "stats": stats}

@app.get("/api/analytics/heatmap")
def api_get_heatmap():
    return db.get_activity_heatmap()

@app.get("/api/polls")
def api_get_polls():
    return db.get_all_polls()

@app.get("/api/teachers")
def api_get_teachers(q: str = ""):
    import teachers
    if q.strip():
        return teachers.find_teachers(q.strip())
    return teachers.get_all_teachers()

@app.get("/status", response_class=HTMLResponse)
def status_page():
    status_file = TEMPLATES_DIR / "status.html"
    if status_file.exists():
        with open(status_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Status page template not found</h1>")

@app.get("/api/messages/history")
def api_messages_history():
    return load_json(HISTORY_FILE, [])

@app.get("/api/tickets")
def api_get_tickets():
    return db.get_all_tickets()

@app.get("/api/db/users")
def api_get_db_users():
    raw_users = db.get_all_users()
    enriched = []
    for u in raw_users:
        prog_code = u.get("program_code") or "D01B9"
        prog_name = u.get("program_name") or DU_PROGRAMS_MAP.get(prog_code, prog_code)
        faculty_name = DU_FACULTY_MAP.get(prog_code, "🌿 Естественные науки, IT и здоровье")
        sem = int(u.get("semester") or 3)
        course = (sem + 1) // 2
        is_on, badge, human_t = db.get_online_status(u.get("last_active"))
        enriched.append({
            **u,
            "faculty": faculty_name,
            "program_code": prog_code,
            "program_name": prog_name,
            "semester": sem,
            "course": course,
            "semester_label": f"{course} курс ({sem} сем.)",
            "is_online": is_on,
            "online_badge": badge,
            "last_active_human": human_t,
            "last_action": u.get("last_action") or "",
            "last_message": u.get("last_message") or "",
            "request_count": u.get("request_count") or 0
        })
    return enriched

class LoginRequest(BaseModel):
    login: str
    password: str

@app.post("/api/auth/login")
def api_auth_login(req: LoginRequest):
    login_clean = req.login.strip().lower()
    for lk, acc in ADMIN_ACCOUNTS.items():
        if lk.lower() == login_clean and acc["password"] == req.password.strip():
            token = f"adm_token_{uuid.uuid4().hex[:16]}"
            session_info = {
                "login": lk,
                "name": acc["name"],
                "username": acc["username"],
                "role": acc["role"],
                "user_id": acc["user_id"],
                "vip_danik": acc.get("vip_danik", False),
                "login_time": datetime.now(TIMEZONE).isoformat()
            }
            ACTIVE_SESSIONS[token] = session_info
            return {
                "success": True,
                "token": token,
                "admin": session_info
            }
    raise HTTPException(status_code=401, detail="Неверный логин или пароль администратора")

@app.get("/api/auth/me")
def api_auth_me(request: Request):
    token = request.headers.get("X-Admin-Token")
    if token and token in ACTIVE_SESSIONS:
        return {"authenticated": True, "admin": ACTIVE_SESSIONS[token]}
    # Return unauthenticated if no valid token
    return {"authenticated": False}

@app.get("/api/analytics/product")
def api_get_product_analytics():
    return db.get_product_analytics()

@app.get("/api/users/{user_id}/profile")
def api_get_user_profile(user_id: int):
    prof = db.get_user_detailed_profile(user_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    prog_code = prof.get("program_code") or "D01B9"
    prof["program_name"] = prof.get("program_name") or DU_PROGRAMS_MAP.get(prog_code, prog_code)
    prof["faculty"] = DU_FACULTY_MAP.get(prog_code, "🌿 Естественные науки, IT и здоровье")
    return prof

# --- Schedule Overrides ---

class OverrideRequest(BaseModel):
    subj: str
    note: str
    date: Optional[str] = ""
    new_room: Optional[str] = ""
    new_group: Optional[str] = ""

@app.get("/api/overrides")
def api_get_overrides():
    return load_json(OVERRIDES_FILE, [])

@app.post("/api/overrides")
def api_add_override(req: OverrideRequest):
    overrides = load_json(OVERRIDES_FILE, [])
    item = {
        "id": str(uuid.uuid4())[:8],
        "subj": req.subj.strip(),
        "note": req.note.strip(),
        "date": req.date.strip() if req.date else "",
        "new_room": req.new_room.strip() if req.new_room else "",
        "new_group": req.new_group.strip() if req.new_group else "",
        "created_at": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    }
    overrides.append(item)
    save_json(OVERRIDES_FILE, overrides)
    return {"success": True, "item": item}

@app.delete("/api/overrides/{item_id}")
def api_delete_override(item_id: str):
    overrides = load_json(OVERRIDES_FILE, [])
    overrides = [o for o in overrides if str(o.get("id")) != str(item_id)]
    save_json(OVERRIDES_FILE, overrides)
    return {"success": True}

# --- Bot Config & Maintenance Mode ---

@app.get("/api/config")
def api_get_config():
    return load_json(CONFIG_FILE, {
        "maintenance_mode": False,
        "maintenance_msg": "⚙️ Бот находится на техническом обслуживании. Пожалуйста, попробуйте позже."
    })

@app.post("/api/config")
def api_post_config(cfg: Dict[str, Any]):
    current = load_json(CONFIG_FILE, {
        "maintenance_mode": False,
        "maintenance_msg": "⚙️ Бот находится на техническом обслуживании. Пожалуйста, попробуйте позже."
    })
    current.update(cfg)
    save_json(CONFIG_FILE, current)
    return {"success": True, "config": current}

# --- Data Export ---

@app.get("/api/export/{filename}")
def api_export_file(filename: str):
    allowed_files = {
        "events_D01B9.json": DATA_DIR / "events_D01B9.json",
        "registered_chats.json": DATA_DIR / "registered_chats.json",
        "stats.json": DATA_DIR / "stats.json",
        "bot.log": DATA_DIR / "bot.log",
        "manual_overrides.json": DATA_DIR / "manual_overrides.json",
        "message_history.json": DATA_DIR / "message_history.json",
        "inbox_messages.json": DATA_DIR / "inbox_messages.json",
        "config.json": DATA_DIR / "config.json",
        "blocked_users.json": DATA_DIR / "blocked_users.json",
        "bot_database.db": DATA_DIR / "bot_database.db"
    }
    target = allowed_files.get(filename)
    if not target or not target.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(path=str(target), filename=filename, media_type="application/octet-stream")

# --- Schedule & Cancellations Analytics ---

@app.get("/api/schedule/analytics")
def api_schedule_analytics(prog_code: str = "D01B9"):
    sched_file = DATA_DIR / f"events_{prog_code}.json"
    if not sched_file.exists():
        return {}

    try:
        with open(sched_file, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception:
        return {}

    courses = {}
    cancellations = []
    rescheduled = []
    rooms_count = {}

    for e in events:
        raw = e.get("raw", {})
        title_full = e.get("title", "").strip()
        parts = [p.strip() for p in title_full.split("\n") if p.strip()]
        subj = parts[0] if parts else "Unknown"
        room = parts[1] if len(parts) > 1 else "Онлайн / Не указана"

        parc_tips = raw.get("parc_tips", "").strip()
        parc_uz = raw.get("parc_uz", "").strip()
        change = raw.get("changetext", "").strip()
        start = e.get("start", "")
        time_str = raw.get("lutime", "")
        date_str = " ".join(start.split()[1:4]) if start else ""

        rooms_count[room] = rooms_count.get(room, 0) + 1

        if subj not in courses:
            courses[subj] = {
                "name": subj,
                "total_classes": 0,
                "rooms": set(),
                "types": set()
            }
        courses[subj]["total_classes"] += 1
        courses[subj]["rooms"].add(room)
        ltype = raw.get("lulecturetype", "").strip().replace("\n", " ")
        if ltype:
            courses[subj]["types"].add(ltype)

        if "atcelt" in parc_tips.lower() or "atcelt" in change.lower():
            cancellations.append({
                "subj": subj,
                "date": date_str,
                "time": time_str,
                "room": room,
                "change": "Отменено (Atcelta)"
            })
        elif "pārcelt" in parc_tips.lower() or "pārcelt" in parc_uz.lower() or "pārcelt" in change.lower():
            change_desc = "Перенесено (Pārcelta)"
            if parc_uz and parc_uz != "Pārceltā":
                change_desc = f"Перенесено на {parc_uz}"
            elif parc_tips and parc_tips != "Pārcelta":
                change_desc = f"Перенесено ({parc_tips})"
            rescheduled.append({
                "subj": subj,
                "date": date_str,
                "time": time_str,
                "room": room,
                "change": change_desc
            })

    courses_list = []
    for k, v in sorted(courses.items()):
        courses_list.append({
            "name": v["name"],
            "total_classes": v["total_classes"],
            "rooms": list(v["rooms"]),
            "types": list(v["types"])
        })

    return {
        "total_events": len(events),
        "total_courses": len(courses_list),
        "cancellations": cancellations,
        "rescheduled": rescheduled,
        "courses": courses_list,
        "rooms": [{"room": k, "count": v} for k, v in sorted(rooms_count.items(), key=lambda x: x[1], reverse=True)]
    }

# --- Schedule Search API ---

@app.get("/api/schedule/search")
def api_schedule_search(q: str = ""):
    sched_file = DATA_DIR / "events_D01B9.json"
    if not sched_file.exists() or not q.strip():
        return []

    try:
        with open(sched_file, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception:
        return []

    query = q.strip().lower()
    results = []
    for e in events:
        raw = e.get("raw", {})
        title_full = e.get("title", "")
        if query in title_full.lower() or query in raw.get("lutime", "").lower() or query in raw.get("lulecturetype", "").lower():
            parts = [p.strip() for p in title_full.split("\n") if p.strip()]
            results.append({
                "subj": parts[0] if parts else "Занятие",
                "room": parts[1] if len(parts) > 1 else "",
                "time": raw.get("lutime", ""),
                "type": raw.get("lulecturetype", "").strip().replace("\n", " "),
                "change": raw.get("changetext", "").strip()
            })
    return results[:50]

@app.get("/api/schedule/weekday/{wday}")
def api_schedule_weekday(wday: int, prog_code: str = "D01B9", sem: int = 3):
    sched_file = DATA_DIR / f"events_{prog_code}_sem{sem}.json"
    if not sched_file.exists():
        sched_file = DATA_DIR / f"events_{prog_code}.json"
    if not sched_file.exists():
        return []

    try:
        with open(sched_file, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    except Exception:
        return []

    overrides = load_json(OVERRIDES_FILE, [])
    now = datetime.now(TIMEZONE)
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    target_date = monday + timedelta(days=wday)

    result = []
    for e in events_data:
        raw = e.get("raw", {})
        start = e.get("start", "")
        sp = start.split()
        if len(sp) >= 5:
            mon_str = sp[1]
            day_num = int(sp[2])
            year_num = int(sp[3])
            mon_num = MONTH_MAP.get(mon_str, 9)
            ev_date = date(year_num, mon_num, day_num)
            t_str = sp[4][:5]
        else:
            continue

        if ev_date != target_date:
            continue

        parc_tips = raw.get("parc_tips", "").strip()
        cnames = e.get("className", [])
        if isinstance(cnames, str):
            cnames = [cnames]
        cnames_set = set(cnames)
        if parc_tips == "Pārcelta" or "tips-R" in cnames_set:
            continue

        title_full = e.get("title", "").strip()
        parts = [p.strip() for p in title_full.split("\n") if p.strip()]
        subj = parts[0] if parts else "Unknown"

        # Group extraction
        ltype = raw.get("lulecturetype", "").strip()
        piezimes = raw.get("piezimes", "").strip()
        grp = ""
        if piezimes and ("grup" in piezimes.lower() or "gr." in piezimes.lower()):
            grp = piezimes
        if not grp:
            ltype_lines = [l.strip() for l in ltype.split("\n") if l.strip()]
            if len(ltype_lines) > 1:
                grp = " • ".join(ltype_lines[1:])
        if not grp:
            for p in parts[1:]:
                if any(w in p.lower() for w in ["grup", "gr."]):
                    grp = p
                    break

        room = ""
        for p in parts[1:]:
            p_clean = p.strip()
            if p_clean == grp or any(w in p_clean.lower() for w in ["grup", "gr.", "visām", "visam", "prog.", "valoda", "studijas"]):
                continue
            if not room:
                room = p_clean

        change = raw.get("changetext", "").strip()
        for ov in overrides:
            ov_d = (ov.get("date") or "").strip()
            ov_s = (ov.get("subj") or "").strip().lower()
            if ov_d and ev_date.strftime("%Y-%m-%d") != ov_d:
                continue
            if ov_s and ov_s not in subj.lower():
                continue
            change = f"[РУЧНОЕ ИЗМЕНЕНИЕ] {ov.get('note', '')}"
            if ov.get("new_room"):
                room = ov["new_room"].strip()
            if ov.get("new_group"):
                grp = ov["new_group"].strip()

        formatted_group = locales.format_event_group(grp, "ru") if grp and locales else grp

        result.append({
            "time": t_str,
            "subj": subj,
            "room": room or "Онлайн / Не указана",
            "type": ltype.split("\n")[0] if ltype else "Занятие",
            "group": formatted_group,
            "group_raw": grp,
            "change": change
        })

    result.sort(key=lambda x: x["time"])
    return result

# --- Logs ---

@app.get("/api/logs")
def api_logs():
    if not LOG_FILE.exists():
        return {"logs": "Логи пока пусты..."}
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            return {"logs": "".join(lines[-200:])}
    except Exception as e:
        return {"logs": f"Ошибка чтения логов: {e}"}

@app.post("/api/logs/clear")
def api_clear_logs():
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"[{datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] Logs cleared by admin.\n")
        return {"success": True, "message": "Логи очищены"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/", response_class=HTMLResponse)
def index():
    index_file = TEMPLATES_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            resp = HTMLResponse(content=f.read())
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp
    return HTMLResponse(content="<h1>Admin template not found</h1>")

def main():
    port = int(os.getenv("ADMIN_PORT", 8085))
    logger.info(f"Starting Web Admin Panel Pro on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    main()
