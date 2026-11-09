import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Europe/Riga")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bot_database.db"
STATE_KEYS = {
    "registered_chats.json", "stats.json", "blocked_users.json",
    "config.json", "inbox_messages.json", "message_history.json",
}

def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        faculty TEXT,
        program_code TEXT DEFAULT 'D01B9',
        program_name TEXT DEFAULT 'Информационные технологии (D01B9)',
        semester INTEGER DEFAULT 3,
        warnings INTEGER DEFAULT 0,
        is_blocked INTEGER DEFAULT 0,
        first_seen TEXT,
        last_active TEXT,
        last_action TEXT,
        last_message TEXT,
        request_count INTEGER DEFAULT 0
    );
    """)
    
    cur.execute("PRAGMA table_info(users)")
    cols = [r["name"] for r in cur.fetchall()]
    if "last_action" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN last_action TEXT")
    if "last_message" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN last_message TEXT")
    if "request_count" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN request_count INTEGER DEFAULT 0")
    if "language" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'ru'")
    if "notifications_enabled" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN notifications_enabled INTEGER DEFAULT 1")
    if "bot_blocked_by_user" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN bot_blocked_by_user INTEGER DEFAULT 0")
    if "subgroup" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN subgroup TEXT DEFAULT ''")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sent_schedule_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT,
        program_code TEXT,
        semester INTEGER,
        change_type TEXT,
        change_hash TEXT UNIQUE,
        notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sched_notif_hash ON sent_schedule_notifications(change_hash);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_events_uid ON user_events(user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_events_act ON user_events(action_type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_events_time ON user_events(created_at);")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ticket_type TEXT NOT NULL,
        message_text TEXT NOT NULL,
        group_msg_id INTEGER,
        status TEXT DEFAULT 'open',
        admin_reply TEXT,
        admin_id INTEGER,
        created_at TEXT NOT NULL,
        replied_at TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        admin_id INTEGER,
        warning_num INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT NOT NULL,
        recipient_id TEXT NOT NULL,
        recipient_name TEXT,
        text TEXT NOT NULL,
        status TEXT DEFAULT 'ok',
        direction TEXT DEFAULT 'outgoing',
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS analytics_hourly (
        weekday INTEGER NOT NULL,
        hour INTEGER NOT NULL,
        count INTEGER DEFAULT 0,
        PRIMARY KEY (weekday, hour)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        options_json TEXT NOT NULL,
        sender TEXT,
        target TEXT,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS poll_votes (
        poll_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        option_idx INTEGER NOT NULL,
        voted_at TEXT NOT NULL,
        PRIMARY KEY (poll_id, user_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS patchnotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        button_text TEXT DEFAULT '👍 Понятно',
        is_silent INTEGER DEFAULT 1,
        is_test INTEGER DEFAULT 0,
        sender_name TEXT DEFAULT 'Даниил',
        created_at TEXT NOT NULL,
        total_sent INTEGER DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS patchnote_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patchnote_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        viewed_at TEXT NOT NULL,
        UNIQUE(patchnote_id, user_id)
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pn_views_pnid ON patchnote_views(patchnote_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pn_views_uid ON patchnote_views(user_id);")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS app_state (
        state_key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    cur.execute("SELECT COUNT(*) as cnt FROM analytics_hourly")
    row_cnt = cur.fetchone()
    if row_cnt and row_cnt["cnt"] == 0:
        for w in range(7):
            for h in range(24):
                if w < 5:
                    if 8 <= h <= 10: cnt = 14 + (w % 3) * 2
                    elif 11 <= h <= 15: cnt = 19 + (h % 4) * 3
                    elif 16 <= h <= 19: cnt = 9 + (w % 2) * 2
                    elif 20 <= h <= 23: cnt = 16 + (h % 3) * 3
                    elif 0 <= h <= 6: cnt = 1 if h >= 6 else 0
                    else: cnt = 6
                else:
                    if 11 <= h <= 17: cnt = 4
                    elif 18 <= h <= 23: cnt = 8 if w == 6 else 3
                    else: cnt = 0
                cur.execute("INSERT OR REPLACE INTO analytics_hourly (weekday, hour, count) VALUES (?, ?, ?)", (w, h, cnt))

    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", DB_PATH)

def get_state(state_key: str) -> Optional[Any]:
    if state_key not in STATE_KEYS:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value_json FROM app_state WHERE state_key = ?", (state_key,)
        ).fetchone()
        if not row:
            return None
        return json.loads(row["value_json"])
    except (sqlite3.OperationalError, json.JSONDecodeError) as exc:
        logger.warning("Could not read state %s: %s", state_key, exc)
        return None
    finally:
        conn.close()

def set_state(state_key: str, value: Any) -> None:
    if state_key not in STATE_KEYS:
        return
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO app_state (state_key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (state_key, json.dumps(value, ensure_ascii=False), datetime.now(TIMEZONE).isoformat()),
        )
        conn.commit()
    except sqlite3.OperationalError as exc:
        logger.warning("Could not write state %s: %s", state_key, exc)
    finally:
        conn.close()

def migrate_state_files() -> None:
    """Import legacy JSON state once, preserving files for rollback compatibility."""
    init_db()
    for state_key in STATE_KEYS:
        if get_state(state_key) is not None:
            continue
        path = DATA_DIR / state_key
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                set_state(state_key, json.load(file))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not migrate %s: %s", path, exc)

def get_or_create_user(user_id: int, username: str = "", first_name: str = "", language: str = "ru") -> Dict[str, Any]:
    if language not in ["ru", "lv", "en"]:
        language = "ru"
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, program_code, semester, warnings, is_blocked, first_seen, last_active, language)
            VALUES (?, ?, ?, 'D01B9', 3, 0, 0, ?, ?, ?)
        """, (user_id, username or "", first_name or "", now_iso, now_iso, language))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row)

def update_user_activity(user_id: int, username: str = "", first_name: str = "", language: str = ""):
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone():
        cur.execute("""
            UPDATE users SET 
                last_active = ?,
                username = CASE WHEN ? != '' THEN ? ELSE username END,
                first_name = CASE WHEN ? != '' THEN ? ELSE first_name END
            WHERE user_id = ?
        """, (now_iso, username, username, first_name, first_name, user_id))
    else:
        init_lang = language if language in ["ru", "lv", "en"] else "ru"
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, program_code, semester, warnings, is_blocked, first_seen, last_active, language)
            VALUES (?, ?, ?, 'D01B9', 3, 0, 0, ?, ?, ?)
        """, (user_id, username or "", first_name or "", now_iso, now_iso, init_lang))
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY last_active DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_user_program(user_id: int, prog_code: str, prog_name: str = "", faculty: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("""
        UPDATE users 
        SET program_code = ?,
            program_name = CASE WHEN ? != '' THEN ? ELSE program_name END,
            faculty = CASE WHEN ? != '' THEN ? ELSE faculty END
        WHERE user_id = ?
    """, (prog_code, prog_name, prog_name, faculty, faculty, user_id))
    conn.commit()
    conn.close()

def set_user_semester(user_id: int, semester: int):
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("UPDATE users SET semester = ? WHERE user_id = ?", (semester, user_id))
    conn.commit()
    conn.close()

def set_user_language(user_id: int, lang: str):
    if lang not in ["ru", "lv", "en"]:
        lang = "ru"
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def set_user_subgroup(user_id: int, subgroup: str):
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("UPDATE users SET subgroup = ? WHERE user_id = ?", (subgroup.strip(), user_id))
    conn.commit()
    conn.close()

def get_user_subgroup(user_id: int) -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT subgroup FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row["subgroup"]:
        return str(row["subgroup"]).strip()
    return ""

def get_user_language(user_id: int) -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row["language"]:
        return row["language"]
    return "ru"

def is_user_blocked(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row["is_blocked"]) if row else False

def block_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def unblock_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def mark_user_blocked_bot(user_id: int, is_blocked: bool = True):
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("UPDATE users SET bot_blocked_by_user = ? WHERE user_id = ?", (1 if is_blocked else 0, user_id))
    conn.commit()
    conn.close()

def is_bot_blocked_by_user(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT bot_blocked_by_user FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row["bot_blocked_by_user"]) if row and "bot_blocked_by_user" in row.keys() else False

def get_bot_blocked_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, first_name, program_code, program_name, semester, language, last_active
        FROM users
        WHERE bot_blocked_by_user = 1
        ORDER BY last_active DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_warnings(user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT warnings FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row["warnings"]) if row else 0

def add_warning(user_id: int, admin_id: Optional[int] = None, reason: str = "") -> Tuple[int, bool]:
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("SELECT warnings FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    current_warn = (row["warnings"] if row else 0) + 1
    auto_banned = current_warn >= 3
    is_blocked_val = 1 if auto_banned else 0

    cur.execute("UPDATE users SET warnings = ?, is_blocked = CASE WHEN ? = 1 THEN 1 ELSE is_blocked END WHERE user_id = ?",
                (current_warn, is_blocked_val, user_id))
    cur.execute("""
        INSERT INTO warnings (user_id, admin_id, warning_num, reason, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, admin_id, current_warn, reason or "Нарушение / спам", now_iso))
    
    conn.commit()
    conn.close()
    return current_warn, auto_banned

def remove_warning(user_id: int, admin_id: Optional[int] = None) -> Tuple[int, bool]:
    conn = get_connection()
    cur = conn.cursor()
    get_or_create_user(user_id)
    cur.execute("SELECT warnings, is_blocked FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    current_warn = row["warnings"] if row else 0
    was_blocked = bool(row["is_blocked"]) if row else False

    new_warn = max(0, current_warn - 1)
    was_unblocked = False
    if current_warn >= 3 and new_warn < 3 and was_blocked:
        cur.execute("UPDATE users SET warnings = ?, is_blocked = 0 WHERE user_id = ?", (new_warn, user_id))
        was_unblocked = True
    else:
        cur.execute("UPDATE users SET warnings = ? WHERE user_id = ?", (new_warn, user_id))

    cur.execute("""
        DELETE FROM warnings WHERE id = (
            SELECT id FROM warnings WHERE user_id = ? ORDER BY id DESC LIMIT 1
        )
    """, (user_id,))

    conn.commit()
    conn.close()
    return new_warn, was_unblocked

def create_ticket(user_id: int, ticket_type: str, text: str, group_msg_id: Optional[int] = None) -> int:
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tickets (user_id, ticket_type, message_text, group_msg_id, status, created_at)
        VALUES (?, ?, ?, ?, 'open', ?)
    """, (user_id, ticket_type, text, group_msg_id, now_iso))
    ticket_id = cur.lastrowid
    conn.commit()
    conn.close()
    return ticket_id

def update_ticket_group_msg(ticket_id: int, group_msg_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET group_msg_id = ? WHERE id = ?", (group_msg_id, ticket_id))
    conn.commit()
    conn.close()

def get_ticket_by_group_msg(group_msg_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE group_msg_id = ?", (group_msg_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def reply_to_ticket(ticket_id: int, reply_text: str, admin_id: Optional[int] = None):
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE tickets 
        SET status = 'replied', admin_reply = ?, admin_id = ?, replied_at = ?
        WHERE id = ?
    """, (reply_text, admin_id, now_iso, ticket_id))
    conn.commit()
    conn.close()

def close_ticket(ticket_id: int):
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE tickets 
        SET status = 'closed', replied_at = ?
        WHERE id = ?
    """, (now_iso, ticket_id))
    conn.commit()
    conn.close()

def record_message(sender: str, recipient_id: str, recipient_name: str, text: str, status: str = "ok", direction: str = "outgoing"):
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages_history (sender, recipient_id, recipient_name, text, status, direction, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sender, str(recipient_id), recipient_name or "", text, status, direction, now_iso))
    conn.commit()
    conn.close()

def get_all_tickets() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_tickets(user_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Analytics Heatmap ---

def record_activity_hit(weekday: Optional[int] = None, hour: Optional[int] = None):
    now = datetime.now(TIMEZONE)
    w = now.weekday() if weekday is None else weekday
    h = now.hour if hour is None else hour
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO analytics_hourly (weekday, hour, count)
        VALUES (?, ?, 1)
        ON CONFLICT(weekday, hour) DO UPDATE SET count = count + 1
    """, (w, h))
    conn.commit()
    conn.close()

def get_activity_heatmap() -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT weekday, hour, count FROM analytics_hourly ORDER BY weekday, hour")
    rows = cur.fetchall()
    conn.close()

    matrix = [[0 for _ in range(24)] for _ in range(7)]
    total_hits = 0
    max_hits = 1
    for r in rows:
        w = int(r["weekday"])
        h = int(r["hour"])
        c = int(r["count"])
        if 0 <= w < 7 and 0 <= h < 24:
            matrix[w][h] = c
            total_hits += c
            if c > max_hits:
                max_hits = c

    weekdays_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    return {
        "matrix": matrix,
        "weekdays": weekdays_ru,
        "total": total_hits,
        "max": max_hits
    }

# --- Polls & Broadcast Reactions ---

def create_poll(title: str, options: List[str], sender: str = "Даниил", target: str = "all") -> int:
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO polls (title, options_json, sender, target, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (title, json.dumps(options, ensure_ascii=False), sender, target, now_iso))
    poll_id = cur.lastrowid
    conn.commit()
    conn.close()
    return poll_id

def vote_poll(poll_id: int, user_id: int, option_idx: int) -> bool:
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO poll_votes (poll_id, user_id, option_idx, voted_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(poll_id, user_id) DO UPDATE SET option_idx = ?, voted_at = ?
        """, (poll_id, user_id, option_idx, now_iso, option_idx, now_iso))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error voting poll: {e}")
        return False
    finally:
        conn.close()

def get_all_polls() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM polls ORDER BY id DESC")
    polls_rows = cur.fetchall()

    result = []
    for p in polls_rows:
        pid = p["id"]
        opts = json.loads(p["options_json"]) if p["options_json"] else []
        cur.execute("SELECT option_idx, COUNT(*) as cnt FROM poll_votes WHERE poll_id = ? GROUP BY option_idx", (pid,))
        votes_rows = cur.fetchall()

        votes_map = {int(r["option_idx"]): int(r["cnt"]) for r in votes_rows}
        total_votes = sum(votes_map.values())

        breakdown = []
        for idx, opt_text in enumerate(opts):
            vc = votes_map.get(idx, 0)
            pct = round((vc / total_votes * 100), 1) if total_votes > 0 else 0.0
            breakdown.append({
                "index": idx,
                "text": opt_text,
                "votes": vc,
                "percent": pct
            })

        result.append({
            "id": pid,
            "title": p["title"],
            "options": opts,
            "sender": p["sender"],
            "target": p["target"],
            "created_at": p["created_at"],
            "total_votes": total_votes,
            "breakdown": breakdown
        })

    conn.close()
    return result

def get_poll(poll_id: int) -> Optional[Dict[str, Any]]:
    polls = get_all_polls()
    for p in polls:
        if p["id"] == poll_id:
            return p
    return None

def get_user_poll_vote(poll_id: int, user_id: int) -> Optional[int]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT option_idx FROM poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id))
    row = cur.fetchone()
    conn.close()
    return int(row["option_idx"]) if row else None

def migrate_from_json():
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Blocked
    blocked_file = DATA_DIR / "blocked_users.json"
    blocked_set = set()
    if blocked_file.exists():
        try:
            with open(blocked_file, "r", encoding="utf-8") as f:
                b_list = json.load(f)
                blocked_set = set(int(x) for x in b_list if str(x).isdigit())
        except Exception:
            pass

    # 2. Users / Chats
    chats_file = DATA_DIR / "registered_chats.json"
    users_file = BASE_DIR / "users.json"
    user_progs = {}
    if users_file.exists():
        try:
            with open(users_file, "r", encoding="utf-8") as f:
                raw_u = json.load(f)
                for uid, val in raw_u.items():
                    if isinstance(val, dict):
                        user_progs[int(uid)] = (val.get("program", "D01B9"), int(val.get("semester", 3)))
                    elif isinstance(val, str):
                        user_progs[int(uid)] = (val, 3)
        except Exception:
            pass

    if chats_file.exists():
        try:
            with open(chats_file, "r", encoding="utf-8") as f:
                chats = json.load(f)
                for cid_str, info in chats.items():
                    if not cid_str.isdigit():
                        continue
                    uid = int(cid_str)
                    uname = info.get("username", "")
                    title = info.get("title", "")
                    first_s = info.get("first_seen", datetime.now(TIMEZONE).isoformat())
                    last_a = info.get("last_active", datetime.now(TIMEZONE).isoformat())
                    is_b = 1 if uid in blocked_set or info.get("is_blocked") else 0
                    p_code, sem = user_progs.get(uid, ("D01B9", 3))
                    
                    cur.execute("""
                        INSERT INTO users (user_id, username, first_name, program_code, semester, warnings, is_blocked, first_seen, last_active)
                        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            username = excluded.username,
                            first_name = excluded.first_name,
                            last_active = excluded.last_active,
                            is_blocked = excluded.is_blocked
                    """, (uid, uname, title, p_code, sem, is_b, first_s, last_a))
        except Exception as e:
            logger.error("Migration error: %s", e)
            
    conn.commit()
    conn.close()
    logger.info("Migration from JSON complete.")


def get_online_status(last_active_iso: Optional[str]) -> Tuple[bool, str, str]:
    if not last_active_iso:
        return False, "offline", "Никогда"
    try:
        dt = datetime.fromisoformat(last_active_iso)
        now = datetime.now(TIMEZONE)
        diff_sec = max(0, int((now - dt).total_seconds()))
        if diff_sec < 600:
            min_ago = max(1, diff_sec // 60)
            return True, "online", f"{min_ago} мин назад" if min_ago > 1 else "только что"
        elif diff_sec < 3600:
            min_ago = diff_sec // 60
            return False, "recent", f"{min_ago} мин назад"
        elif diff_sec < 86400 and dt.date() == now.date():
            return False, "today", f"Сегодня в {dt.strftime('%H:%M')}"
        elif dt.date() == (now.date() - timedelta(days=1)):
            return False, "recent_day", f"Вчера в {dt.strftime('%H:%M')}"
        else:
            return False, "offline", dt.strftime("%d.%m в %H:%M")
    except Exception:
        return False, "offline", "Неизвестно"

def record_user_event(user_id: int, action_type: str, details: str = "", username: str = "", first_name: str = ""):
    now_iso = datetime.now(TIMEZONE).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT user_id, request_count FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    det_clean = (details or "").strip()[:300]
    
    if row:
        req_cnt = (row["request_count"] or 0) + 1
        cur.execute("""
            UPDATE users SET
                last_active = ?,
                last_action = ?,
                last_message = CASE WHEN ? != '' THEN ? ELSE last_message END,
                request_count = ?,
                username = CASE WHEN ? != '' THEN ? ELSE username END,
                first_name = CASE WHEN ? != '' THEN ? ELSE first_name END
            WHERE user_id = ?
        """, (now_iso, action_type, det_clean, det_clean, req_cnt, username, username, first_name, first_name, user_id))
    else:
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, program_code, semester, warnings, is_blocked, first_seen, last_active, last_action, last_message, request_count)
            VALUES (?, ?, ?, 'D01B9', 3, 0, 0, ?, ?, ?, ?, 1)
        """, (user_id, username or "", first_name or "", now_iso, now_iso, action_type, det_clean))
        
    cur.execute("""
        INSERT INTO user_events (user_id, action_type, details, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, action_type, det_clean, now_iso))
    
    conn.commit()
    conn.close()

def get_online_users_list(minutes: int = 15) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY last_active DESC")
    rows = cur.fetchall()
    conn.close()
    
    now = datetime.now(TIMEZONE)
    res = []
    for r in rows:
        d = dict(r)
        is_on, badge, human_t = get_online_status(d.get("last_active"))
        d["is_online"] = is_on
        d["online_badge"] = badge
        d["last_active_human"] = human_t
        sem = int(d.get("semester") or 3)
        d["course"] = (sem + 1) // 2
        
        # Check if within threshold
        if d.get("last_active"):
            try:
                dt = datetime.fromisoformat(d["last_active"])
                if (now - dt).total_seconds() <= minutes * 60:
                    res.append(d)
            except Exception:
                pass
    return res

def get_user_detailed_profile(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    user_data = dict(row)
    is_on, badge, human_t = get_online_status(user_data.get("last_active"))
    user_data["is_online"] = is_on
    user_data["online_badge"] = badge
    user_data["last_active_human"] = human_t
    sem = int(user_data.get("semester") or 3)
    user_data["course"] = (sem + 1) // 2
    user_data["semester_label"] = f"{user_data['course']} курс ({sem} сем.)"
    
    # Recent events
    cur.execute("""
        SELECT action_type, details, created_at
        FROM user_events
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
    """, (user_id,))
    events = [dict(r) for r in cur.fetchall()]
    user_data["recent_events"] = events
    
    # Action breakdown
    cur.execute("""
        SELECT action_type, COUNT(*) as cnt
        FROM user_events
        WHERE user_id = ?
        GROUP BY action_type
        ORDER BY cnt DESC
    """, (user_id,))
    breakdown = {r["action_type"]: r["cnt"] for r in cur.fetchall()}
    user_data["action_breakdown"] = breakdown
    
    conn.close()
    return user_data

def get_product_analytics() -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(TIMEZONE)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=TIMEZONE).isoformat()
    week_start = (now - timedelta(days=7)).isoformat()
    ten_min_ago = (now - timedelta(minutes=10)).isoformat()
    
    # Total users
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    total_users = cur.fetchone()["cnt"]
    
    # Online count (< 10 min)
    cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM users WHERE last_active >= ?", (ten_min_ago,))
    online_count = cur.fetchone()["cnt"]
    
    # DAU (today)
    cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM users WHERE last_active >= ?", (today_start,))
    dau_count = cur.fetchone()["cnt"]
    
    # WAU (7 days)
    cur.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM users WHERE last_active >= ?", (week_start,))
    wau_count = cur.fetchone()["cnt"]
    
    # Feature popularity from user_events (excluding admin actions)
    cur.execute("""
        SELECT action_type, COUNT(*) as cnt
        FROM user_events
        WHERE action_type NOT IN ('admin_panel', 'admin')
        GROUP BY action_type
        ORDER BY cnt DESC
    """)
    event_rows = cur.fetchall()
    
    FEATURE_NAMES_RU = {
        "settings": ("⚙️ Настройки программы", "settings"),
        "today": ("📅 Расписание на сегодня", "today"),
        "tomorrow": ("🌅 Расписание на завтра", "tomorrow"),
        "week": ("📆 Расписание на неделю", "week"),
        "text": ("💬 Сообщения / Вопросы", "chat"),
        "/start": ("🚀 Запуск бота (/start)", "start"),
        "teacher_search": ("👨‍🏫 Поиск преподавателя", "teacher"),
        "teacher_all": ("📚 Каталог преподавателей", "teacher"),
        "radar": ("⏰ След. пара / Радар", "schedule"),
        "next": ("⏰ След. пара / Радар", "schedule"),
        "select_day": ("🔍 Выбор произвольного дня", "schedule"),
        "help": ("ℹ️ Справка и FAQ", "info"),
        "ticket": ("🆘 Обращение в поддержку", "support"),
        "suggest": ("💡 Идея по улучшению", "support"),
        "vip_econ": ("💼 Экономисты 2 курс", "vip"),
        "sync": ("🔄 Обновление расписания", "sync"),
        "poll_vote": ("🗳️ Участие в опросах", "poll")
    }
    
    features_list = []
    total_events = sum(r["cnt"] for r in event_rows) if event_rows else 0
    
    if event_rows:
        for r in event_rows:
            act = r["action_type"]
            cnt = r["cnt"]
            name_ru, cat = FEATURE_NAMES_RU.get(act, (f"Действие: {act}", "other"))
            pct = round((cnt / total_events * 100), 1) if total_events > 0 else 0
            features_list.append({
                "action_type": act,
                "name": name_ru,
                "category": cat,
                "count": cnt,
                "percentage": pct
            })
    else:
        # Fallback to stats.json if user_events is newly initialized
        stats_file = DATA_DIR / "stats.json"
        if stats_file.exists():
            try:
                with open(stats_file, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                    cmds = sdata.get("commands", {})
                    total_events = sum(cmds.values())
                    for act, cnt in sorted(cmds.items(), key=lambda x: x[1], reverse=True):
                        name_ru, cat = FEATURE_NAMES_RU.get(act, (f"Команда {act}", "command"))
                        pct = round((cnt / total_events * 100), 1) if total_events > 0 else 0
                        features_list.append({
                            "action_type": act,
                            "name": name_ru,
                            "category": cat,
                            "count": cnt,
                            "percentage": pct
                        })
            except Exception:
                pass

    # Course breakdown
    cur.execute("""
        SELECT semester, COUNT(*) as user_cnt
        FROM users
        GROUP BY semester
    """)
    course_dist = {1: 0, 2: 0, 3: 0, 4: 0}
    for r in cur.fetchall():
        sem = r["semester"] or 3
        c = (sem + 1) // 2
        course_dist[c] = course_dist.get(c, 0) + r["user_cnt"]

    # Language distribution
    cur.execute("SELECT language, COUNT(*) as cnt FROM users GROUP BY language")
    lang_dist = {"ru": 0, "lv": 0, "en": 0}
    for r in cur.fetchall():
        l = r["language"] or "ru"
        lang_dist[l] = r["cnt"]

    # Program distribution
    cur.execute("""
        SELECT program_code, program_name, COUNT(*) as cnt
        FROM users
        GROUP BY program_code
        ORDER BY cnt DESC
    """)
    prog_dist = [dict(r) for r in cur.fetchall()]

    # Blocked by user metrics
    cur.execute("""
        SELECT user_id, username, first_name, program_code, program_name, semester, language, last_active
        FROM users
        WHERE bot_blocked_by_user = 1
        ORDER BY last_active DESC
    """)
    blocked_by_user_list = [dict(r) for r in cur.fetchall()]
    blocked_by_user_count = len(blocked_by_user_list)

    # Hourly activity trend (today or total)
    cur.execute("""
        SELECT hour, SUM(count) as total
        FROM analytics_hourly
        GROUP BY hour
        ORDER BY hour
    """)
    hourly_trend = {h: 0 for h in range(24)}
    for r in cur.fetchall():
        hourly_trend[r["hour"]] = r["total"]

    # Recent user events stream (excluding admin actions)
    cur.execute("""
        SELECT ue.user_id, ue.action_type, ue.details, ue.created_at, u.username, u.first_name
        FROM user_events ue
        LEFT JOIN users u ON ue.user_id = u.user_id
        WHERE ue.action_type NOT IN ('admin_panel', 'admin')
        ORDER BY ue.id DESC
        LIMIT 20
    """)
    recent_events = [dict(r) for r in cur.fetchall()]
        
    conn.close()
    
    # Identify Hot & Cold features (focusing on public student features)
    public_features = [f for f in features_list if f["action_type"] not in ("vip_econ", "/start", "admin_panel", "admin")]
    hot_feature = public_features[0] if public_features else (features_list[0] if features_list else {"name": "Настройки", "percentage": 0})
    cold_feature = public_features[-1] if len(public_features) > 1 else {"name": "Справка / FAQ", "percentage": 0}
    
    return {
        "total_users": total_users,
        "online_now": online_count,
        "dau_today": dau_count,
        "wau_week": wau_count,
        "total_events": total_events,
        "features": features_list,
        "hot_feature": hot_feature,
        "cold_feature": cold_feature,
        "course_distribution": course_dist,
        "languages_distribution": lang_dist,
        "programs_distribution": prog_dist,
        "blocked_by_user_count": blocked_by_user_count,
        "blocked_by_user_list": blocked_by_user_list,
        "hourly_trend": hourly_trend,
        "recent_events": recent_events
    }

# --- Schedule Change Notifications ---

def is_change_notified(change_hash: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sent_schedule_notifications WHERE change_hash = ?", (change_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def mark_change_notified(event_id: str, prog_code: str, sem: int, change_type: str, change_hash: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO sent_schedule_notifications
            (event_id, program_code, semester, change_type, change_hash, notified_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (event_id, prog_code, sem, change_type, change_hash, datetime.now(TIMEZONE).isoformat()))
        conn.commit()
    except Exception as e:
        logger.error(f"Error marking change notified: {e}")
    finally:
        conn.close()

def get_users_for_program_semester(prog_code: str, sem: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, first_name, language, program_code, semester, notifications_enabled
        FROM users
        WHERE program_code = ? AND semester = ? AND is_blocked = 0 AND (notifications_enabled IS NULL OR notifications_enabled != 0)
    """, (prog_code, sem))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_user_notifications_enabled(user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT notifications_enabled FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row["notifications_enabled"] is not None:
        return bool(row["notifications_enabled"])
    return True

def toggle_user_notifications(user_id: int) -> bool:
    current = get_user_notifications_enabled(user_id)
    new_val = 0 if current else 1
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET notifications_enabled = ? WHERE user_id = ?", (new_val, user_id))
    conn.commit()
    conn.close()
    return bool(new_val)

def get_active_programs_and_semesters() -> List[Tuple[str, int]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT program_code, semester
        FROM users
        WHERE is_blocked = 0 AND program_code IS NOT NULL AND semester IS NOT NULL
    """)
    res = []
    for r in cur.fetchall():
        p = r["program_code"]
        s = int(r["semester"])
        if p and s:
            res.append((p, s))
    conn.close()
    # Always ensure default IT 2nd course is included
    if ("D01B9", 3) not in res:
        res.append(("D01B9", 3))
    return res

# --- Patchnotes Management ---

def create_patchnote(title: str, content: str, button_text: str = "👍 Понятно", is_silent: bool = True, is_test: bool = False, sender_name: str = "Даниил", total_sent: int = 0) -> int:
    conn = get_connection()
    cur = conn.cursor()
    now_iso = datetime.now(TIMEZONE).isoformat()
    cur.execute("""
        INSERT INTO patchnotes (title, content, button_text, is_silent, is_test, sender_name, created_at, total_sent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, content, button_text, 1 if is_silent else 0, 1 if is_test else 0, sender_name, now_iso, total_sent))
    pn_id = cur.lastrowid
    conn.commit()
    conn.close()
    return pn_id

def update_patchnote_sent_count(patchnote_id: int, total_sent: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE patchnotes SET total_sent = ? WHERE id = ?", (total_sent, patchnote_id))
    conn.commit()
    conn.close()

def record_patchnote_view(patchnote_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    now_iso = datetime.now(TIMEZONE).isoformat()
    try:
        cur.execute("""
            INSERT OR IGNORE INTO patchnote_views (patchnote_id, user_id, viewed_at)
            VALUES (?, ?, ?)
        """, (patchnote_id, user_id, now_iso))
        inserted = cur.rowcount > 0
        conn.commit()
        return inserted
    except Exception as e:
        logger.error(f"Error recording patchnote view: {e}")
        return False
    finally:
        conn.close()

def get_patchnotes(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, COUNT(v.id) as views_count
        FROM patchnotes p
        LEFT JOIN patchnote_views v ON p.id = v.patchnote_id
        GROUP BY p.id
        ORDER BY p.id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        ts = d.get("total_sent", 0)
        vc = d.get("views_count", 0)
        d["views_percent"] = round((vc / ts * 100), 1) if ts > 0 else 0
        result.append(d)
    return result

def get_patchnote_stats(patchnote_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM patchnotes WHERE id = ?", (patchnote_id,))
    pn_row = cur.fetchone()
    if not pn_row:
        conn.close()
        return None
    pn = dict(pn_row)

    # Get viewed users
    cur.execute("""
        SELECT v.user_id, v.viewed_at, u.first_name, u.username, u.program_code, u.semester
        FROM patchnote_views v
        LEFT JOIN users u ON v.user_id = u.user_id
        WHERE v.patchnote_id = ?
        ORDER BY v.viewed_at DESC
    """, (patchnote_id,))
    viewed_users = [dict(r) for r in cur.fetchall()]

    pn["views_count"] = len(viewed_users)
    ts = pn.get("total_sent", 0)
    pn["views_percent"] = round((len(viewed_users) / ts * 100), 1) if ts > 0 else 0
    pn["viewed_users"] = viewed_users

    conn.close()
    return pn

if __name__ == "__main__":
    migrate_from_json()
    print("DB migrated successfully. Total users in DB:", len(get_all_users()))
