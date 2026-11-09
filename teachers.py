import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("teachers")
TIMEZONE = ZoneInfo("Europe/Riga")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEACHERS_CATALOG_FILE = DATA_DIR / "du_teachers.json"
TEACHERS_CACHE_DIR = DATA_DIR / "teachers"
TEACHERS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TEACHER_SCRAPE_SEMAPHORE = asyncio.Semaphore(1)
TEACHER_SCRAPE_LOCKS = {}

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

try:
    import locales
except ImportError:
    locales = None

TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "z", "з": "z",
    "и": "i", "й": "j", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "c", "ш": "s", "щ": "s",
    "ы": "y", "э": "e", "ю": "ju", "я": "ja",
    "č": "c", "š": "s", "ž": "z", "ā": "a", "ē": "e", "ī": "i", "ū": "u", "ģ": "g", "ķ": "k",
    "ļ": "l", "ņ": "n"
}

def normalize_text(text: str) -> str:
    res = text.lower()
    for src, dst in TRANSLIT_MAP.items():
        res = res.replace(src, dst)
    return res.strip()

def get_all_teachers() -> List[Dict[str, Any]]:
    if not TEACHERS_CATALOG_FILE.exists():
        return []
    try:
        with open(TEACHERS_CATALOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Error loading du_teachers.json: %s", e)
        return []

def find_teachers(query: str) -> List[Dict[str, Any]]:
    norm_q = normalize_text(query)
    if not norm_q:
        return []

    teachers = get_all_teachers()
    matches = []
    for t in teachers:
        name = t.get("name", "")
        norm_name = normalize_text(name)
        if norm_q in norm_name:
            matches.append(t)

    return matches[:10]

async def _scrape_teacher_schedule(teacher_id: str, teacher_name: str) -> List[Dict[str, Any]]:
    cache_file = TEACHERS_CACHE_DIR / f"events_{teacher_id}.json"
    
    # Check cache freshness (12 hours)
    if cache_file.exists():
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime, tz=TIMEZONE)
            if datetime.now(TIMEZONE) - mtime < timedelta(hours=12):
                raw_cache = await asyncio.to_thread(cache_file.read_text, encoding="utf-8")
                return json.loads(raw_cache)
        except Exception:
            pass

    script_path = BASE_DIR / "scraper_teacher.js"
    if not script_path.exists():
        logger.error("scraper_teacher.js not found at %s", script_path)
        return []

    try:
        proc = await asyncio.create_subprocess_exec(
            "node",
            str(script_path),
            str(teacher_id),
            teacher_name,
            cwd=str(BASE_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=40)
        out_str = stdout.decode("utf-8", errors="ignore")
        if cache_file.exists():
            raw_cache = await asyncio.to_thread(cache_file.read_text, encoding="utf-8")
            return json.loads(raw_cache)
    except Exception as e:
        logger.error("Error scraping teacher schedule: %s", e)

    return []

async def scrape_teacher_schedule(teacher_id: str, teacher_name: str) -> List[Dict[str, Any]]:
    key = str(teacher_id)
    lock = TEACHER_SCRAPE_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        async with TEACHER_SCRAPE_SEMAPHORE:
            return await _scrape_teacher_schedule(teacher_id, teacher_name)

def parse_teacher_events(raw_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    parsed = []
    for e in raw_events:
        start_str = e.get("start") or ""
        sp = start_str.split()
        if len(sp) < 5:
            continue
        try:
            mon_str, day_num, year_num, t_str = sp[1], int(sp[2]), int(sp[3]), sp[4][:5]
            ev_date = date(year_num, MONTH_MAP.get(mon_str, 9), day_num)
        except Exception:
            continue

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

        raw = e.get("raw", {})
        parc_tips = raw.get("parc_tips", "").strip()
        cnames = e.get("className", [])
        if isinstance(cnames, str):
            cnames = [cnames]
        cnames_set = set(cnames)
        if parc_tips == "Pārcelta" or "tips-R" in cnames_set:
            continue

        parts = [p.strip() for p in (e.get("title") or "").split("\n") if p.strip()]
        subj = parts[0] if parts else "Занятие"

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
        if not grp and len(parts) > 2:
            grp = parts[2]

        room = ""
        for p in parts[1:]:
            p_clean = p.strip()
            if p_clean == grp or any(w in p_clean.lower() for w in ["grup", "gr.", "visām", "visam", "prog.", "valoda", "studijas"]):
                continue
            if not room:
                room = p_clean

        parsed.append({
            "date": ev_date,
            "weekday": ev_date.weekday(),
            "time": t_str,
            "end_time": end_t,
            "subj": subj,
            "room": room,
            "group": grp
        })

    parsed.sort(key=lambda x: (x["date"], x["time"]))
    return parsed

def get_teacher_status_card(teacher_name: str, events: List[Dict[str, Any]], lang: str = "ru") -> str:
    if not events:
        if lang == "lv":
            return f"👨‍🏫 <b>{teacher_name}</b>\n\nLUIS rudens semestrī nodarbības nav atrastas vai saraksts vēl nav publicēts."
        elif lang == "en":
            return f"👨‍🏫 <b>{teacher_name}</b>\n\nNo classes found in LUIS for autumn semester or schedule is not yet published."
        return f"👨‍🏫 <b>{teacher_name}</b>\n\nЗанятий в осеннем семестре LUIS не найдено или расписание еще не опубликовано."

    now = datetime.now(TIMEZONE)
    today = now.date()
    now_time = now.strftime("%H:%M")

    today_events = [e for e in events if e["date"] == today]
    today_events.sort(key=lambda x: x["time"])

    current_class = None
    next_class_today = None

    for ev in today_events:
        st = ev["time"]
        en = ev["end_time"]
        if st <= now_time <= en:
            current_class = ev
            break
        elif now_time < st and not next_class_today:
            next_class_today = ev

    lbl_faculty = {"ru": "Преподаватель", "lv": "Pasniedzējs", "en": "Faculty member"}.get(lang, "Преподаватель")
    lines = [f"👨‍🏫 <b>{lbl_faculty}: {teacher_name}</b>\n"]

    lbl_room = {"ru": "Аудитория", "lv": "Telpa", "en": "Room"}.get(lang, "Аудитория")
    lbl_group = {"ru": "Группа", "lv": "Grupa", "en": "Group"}.get(lang, "Группа")

    # Current Status
    if current_class:
        lbl_cur = {"ru": "🟢 <b>СЕЙЧАС ИДЕТ ПАРА:</b>", "lv": "🟢 <b>PAŠLAIK NOTIEK NODARBĪBA:</b>", "en": "🟢 <b>CLASS IN PROGRESS:</b>"}.get(lang, "🟢 <b>СЕЙЧАС ИДЕТ ПАРА:</b>")
        lines.append(lbl_cur)
        lines.append(f"⏰ <b>{current_class['time']} — {current_class['end_time']}</b>")
        lines.append(f"📖 <b>{current_class['subj']}</b>")
        if current_class['room']:
            lines.append(f"🏛️ <b>{lbl_room}:</b> <code>{current_class['room']}</code>")
        if current_class.get('group'):
            grp_fmt = locales.format_event_group(current_class['group'], lang) if locales else f"👥 {current_class['group']}"
            lines.append(f"   {grp_fmt}")
        lines.append("")
    elif next_class_today:
        lbl_nxt = {"ru": "⏳ <b>Следующая пара сегодня:</b>", "lv": "⏳ <b>Nākamā nodarbība šodien:</b>", "en": "⏳ <b>Next class today:</b>"}.get(lang, "⏳ <b>Следующая пара сегодня:</b>")
        lines.append(lbl_nxt)
        lines.append(f"⏰ <b>{next_class_today['time']} — {next_class_today['end_time']}</b>")
        lines.append(f"📖 <b>{next_class_today['subj']}</b>")
        if next_class_today['room']:
            lines.append(f"🏛️ <b>{lbl_room}:</b> <code>{next_class_today['room']}</code>")
        if next_class_today.get('group'):
            grp_fmt = locales.format_event_group(next_class_today['group'], lang) if locales else f"👥 {next_class_today['group']}"
            lines.append(f"   {grp_fmt}")
        lines.append("")
    elif today_events:
        if lang == "lv":
            lines.append("🏁 <b>Šodien visas nodarbības ir beigušās.</b>")
            lines.append(f"Kopā šodien bija nodarbības: {len(today_events)}\n")
        elif lang == "en":
            lines.append("🏁 <b>All classes finished for today.</b>")
            lines.append(f"Total classes today: {len(today_events)}\n")
        else:
            lines.append("🏁 <b>На сегодня пары окончены.</b>")
            lines.append(f"Всего сегодня было пар: {len(today_events)}\n")
    else:
        if lang == "lv":
            lines.append("🏖️ <b>Šodien pasniedzējam nodarbību nav.</b>\n")
        elif lang == "en":
            lines.append("🏖️ <b>No classes today for this instructor.</b>\n")
        else:
            lines.append("🏖️ <b>Сегодня у преподавателя нет занятий.</b>\n")

    # Upcoming Schedule
    upcoming = [e for e in events if e["date"] >= today]
    if not upcoming:
        upcoming = events[-10:]

    # Group by date (next 3 study days)
    days_map = {}
    for ev in upcoming:
        d = ev["date"]
        if d not in days_map:
            if len(days_map) >= 4:
                break
            days_map[d] = []
        days_map[d].append(ev)

    if days_map:
        lbl_up = {"ru": "📅 <b>Расписание на ближайшие дни:</b>", "lv": "📅 <b>Nodarbību saraksts tuvākajām dienām:</b>", "en": "📅 <b>Upcoming schedule:</b>"}.get(lang, "📅 <b>Расписание на ближайшие дни:</b>")
        lines.append(lbl_up)
        for d, ev_list in days_map.items():
            if locales:
                w_name = locales.get_weekday_name(d.weekday(), lang)
            else:
                w_name = WEEKDAYS_RU[d.weekday()]
            day_str = d.strftime("%d.%m")
            today_suffix = {"ru": " (Сегодня)", "lv": " (Šodien)", "en": " (Today)"}.get(lang, " (Сегодня)")
            is_today = today_suffix if d == today else ""
            lines.append(f"\n<b>{w_name}, {day_str}{is_today}:</b>")
            for ev in ev_list:
                room_txt = f" • 🏛️ {ev['room']}" if ev['room'] else ""
                grp_txt = f" • {locales.format_event_group(ev['group'], lang)}" if ev.get('group') and locales else ""
                lines.append(f"  ⏰ <code>{ev['time']}</code> — {ev['subj']}{room_txt}{grp_txt}")

    return "\n".join(lines)
