"""
Localization (i18n) module for DU Schedule Bot.
Supports Russian (ru), Latvian (lv), and English (en).
"""

import re
from typing import Dict, Any, List, Optional

LANG_NAMES = {
    "ru": "🇷🇺 Русский",
    "lv": "🇱🇻 Latviešu",
    "en": "🇬🇧 English"
}

BUTTONS = {
    "today": {"ru": "📅 Сегодня", "lv": "📅 Šodien", "en": "📅 Today"},
    "tomorrow": {"ru": "⏭️ Завтра", "lv": "⏭️ Rīt", "en": "⏭️ Tomorrow"},
    "week": {"ru": "📆 Вся неделя", "lv": "📆 Visa nedēļa", "en": "📆 Full Week"},
    "next": {"ru": "⏰ След. пара", "lv": "⏰ Nākamā nodarbība", "en": "⏰ Next class"},
    "teacher": {"ru": "👨‍🏫 Поиск преподавателя", "lv": "👨‍🏫 Pasniedzēja meklēšana", "en": "👨‍🏫 Find Teacher"},
    "select_day": {"ru": "🔍 Выбрать день", "lv": "🔍 Izvēlēties dienu", "en": "🔍 Select Day"},
    "update": {"ru": "🔄 Обновить", "lv": "🔄 Atjaunot", "en": "🔄 Refresh"},
    "settings": {"ru": "⚙️ Настройки", "lv": "⚙️ Iestatījumi", "en": "⚙️ Settings"},
    "help": {"ru": "ℹ️ Справка / FAQ", "lv": "ℹ️ Palīdzība / FAQ", "en": "ℹ️ Help / FAQ"},
    "vip_econ": {"ru": "💼 Экономисты 2 курс", "lv": "💼 Ekonomisti 2. kurss", "en": "💼 Economists 2nd Year"},
    "support": {"ru": "🆘 Поддержка", "lv": "🆘 Atbalsts", "en": "🆘 Support"},
    "suggest": {"ru": "💡 Предложить улучшение", "lv": "💡 Ieteikt uzlabojumu", "en": "💡 Suggest Feature"}
}

# Reverse mapping from any button text in any language to internal action key
NAV_BUTTON_TO_ACTION = {}
for action, langs in BUTTONS.items():
    for l_code, text in langs.items():
        NAV_BUTTON_TO_ACTION[text] = action

# Also include historic/alternate variants
ALT_MAPPINGS = {
    # Russian alternates
    "👨‍🏫 Преподаватель": "teacher",
    "👨‍🏫 Преподаватели": "teacher",
    "👨‍🏫 Найти преподавателя": "teacher",
    "Поиск преподавателя": "teacher",
    "Преподаватель": "teacher",
    "⏰ Следующая пара": "next",
    "🔄 Обновить из LUIS": "update",
    "ℹ️ Справка": "help",
    "❓ FAQ": "help",
    "Справка": "help",
    "Помощь": "help",
    "FAQ": "help",
    "/faq": "help",
    "💼 Экономисты": "vip_econ",
    "/econ": "vip_econ",
    "🆘 Написать в поддержку": "support",
    "💡 Идеи и улучшения": "suggest",

    # Latvian alternates
    "Šodien": "today",
    "Rīt": "tomorrow",
    "Visa nedēļa": "week",
    "Nākamā nodarbība": "next",
    "Nākamā": "next",
    "Pasniedzējs": "teacher",
    "Pasniedzēji": "teacher",
    "Meklēt pasniedzēju": "teacher",
    "Izvēlēties dienu": "select_day",
    "Atjaunot": "update",
    "Iestatījumi": "settings",
    "Palīdzība": "help",
    "Atbalsts": "support",
    "Ieteikums": "suggest",

    # English alternates
    "Today": "today",
    "Tomorrow": "tomorrow",
    "Week": "week",
    "Next class": "next",
    "Next lesson": "next",
    "Teacher": "teacher",
    "Teachers": "teacher",
    "Find teacher": "teacher",
    "Select day": "select_day",
    "Refresh": "update",
    "Sync": "update",
    "Settings": "settings",
    "Help": "help",
    "Support": "support",
    "Suggest": "suggest"
}
NAV_BUTTON_TO_ACTION.update(ALT_MAPPINGS)

WEEKDAYS = {
    "ru": ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
    "lv": ["Pirmdiena", "Otrdiena", "Trešdiena", "Ceturtdiena", "Piektdiena", "Sestdiena", "Svētdiena"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
}

WEEKDAYS_SHORT = {
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"],
    "lv": ["P", "O", "T", "C", "Pk", "S"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
}

LESSON_TYPES = {
    "ru": {
        "Prakt": "Практика",
        "Lekcij": "Лекция",
        "Semin": "Семинар"
    },
    "lv": {
        "Prakt": "Praktiskie darbi",
        "Lekcij": "Lekcija",
        "Semin": "Seminārs"
    },
    "en": {
        "Prakt": "Practical work",
        "Lekcij": "Lecture",
        "Semin": "Seminar"
    }
}

STRINGS: Dict[str, Dict[str, str]] = {
    # General UI & Banners
    "room_online": {
        "ru": "💻 <b>Онлайн (tiešsaistē)</b>",
        "lv": "💻 <b>Tiešsaistē (online)</b>",
        "en": "💻 <b>Online (remote)</b>"
    },
    "room_aud": {
        "ru": "🏛️ Ауд: <b>{room}</b>",
        "lv": "🏛️ Telpa: <b>{room}</b>",
        "en": "🏛️ Room: <b>{room}</b>"
    },
    "rescheduled_badge": {
        "ru": "⚠️ <b>ПЕРЕНЕСЕНО</b>",
        "lv": "⚠️ <b>PĀRCELTA</b>",
        "en": "⚠️ <b>RESCHEDULED</b>"
    },
    "rescheduled_from_prefix": {
        "ru": "перенесено с",
        "lv": "pārcelta no",
        "en": "rescheduled from"
    },
    "rescheduled_generic": {
        "ru": "перенесенное занятие",
        "lv": "pārcelta nodarbība",
        "en": "rescheduled class"
    },
    "cancelled_class": {
        "ru": "🚫 <b><s>{time} — {subj}</s></b>\n   ❌ <b>ЗАНЯТИЕ ОТМЕНЕНО</b>",
        "lv": "🚫 <b><s>{time} — {subj}</s></b>\n   ❌ <b>NODARBĪBA ATCELTA</b>",
        "en": "🚫 <b><s>{time} — {subj}</s></b>\n   ❌ <b>CLASS CANCELLED</b>"
    },
    "teacher_label": {
        "ru": "👨‍🏫 Преподаватель",
        "lv": "👨‍🏫 Pasniedzējs",
        "en": "👨‍🏫 Lecturer"
    },
    "auto_alert_cancel_title": {
        "ru": "🚨 <b>ВНИМАНИЕ: ЗАНЯТИЕ ОТМЕНЕНО!</b>",
        "lv": "🚨 <b>UZMANĪBU: NODARBĪBA ATCELTA!</b>",
        "en": "🚨 <b>ATTENTION: CLASS CANCELLED!</b>"
    },
    "auto_alert_resched_title": {
        "ru": "⚠️ <b>ВНИМАНИЕ: ЗАНЯТИЕ ПЕРЕНЕСЕНО!</b>",
        "lv": "⚠️ <b>UZMANĪBU: NODARBĪBA PĀRCELTA!</b>",
        "en": "⚠️ <b>ATTENTION: CLASS RESCHEDULED!</b>"
    },
    "auto_alert_group": {
        "ru": "🎓 <b>Группа:</b> {group}",
        "lv": "🎓 <b>Grupa:</b> {group}",
        "en": "🎓 <b>Group:</b> {group}"
    },
    "btn_notifications": {
        "ru": "🔔 Уведомления об отменах",
        "lv": "🔔 Paziņojumi par izmaiņām",
        "en": "🔔 Change Notifications"
    },
    "notifications_status_on": {
        "ru": "ВКЛ ✅",
        "lv": "IESLĒGTI ✅",
        "en": "ON ✅"
    },
    "notifications_status_off": {
        "ru": "ВЫКЛ ❌",
        "lv": "IZSLĒGTI ❌",
        "en": "OFF ❌"
    },
    "notifications_toggled_msg": {
        "ru": "🔔 Автоматические уведомления об отменах и переносах пар: <b>{status}</b>",
        "lv": "🔔 Automātiskie paziņojumi par nodarbību atcelšanu un pārcelšanu: <b>{status}</b>",
        "en": "🔔 Automatic class cancellation and reschedule notifications: <b>{status}</b>"
    },
    "holiday_banner": {
        "ru": "🎉 <b>Праздничный день (выходной)</b> — занятий нет!",
        "lv": "🎉 <b>Svētku diena (brīvdiena)</b> — nodarbību nav!",
        "en": "🎉 <b>Holiday (Day off)</b> — no classes!"
    },
    "no_classes_day": {
        "ru": "🎉 <b>На этот день занятий нет!</b> Отдыхаем.",
        "lv": "🎉 <b>Šajā dienā nodarbību nav!</b> Atpūšamies.",
        "en": "🎉 <b>No classes on this day!</b> Enjoy your free time."
    },
    "shortened_day": {
        "ru": "⏱️ <i>Сокращенный день</i>\n\n",
        "lv": "⏱️ <i>Saīsinātā diena</i>\n\n",
        "en": "⏱️ <i>Shortened day</i>\n\n"
    },
    "no_classes_week": {
        "ru": "Занятий на этой неделе не найдено.",
        "lv": "Šajā nedēļā nodarbību nav.",
        "en": "No classes found for this week."
    },
    "week_header": {
        "ru": "📆 <b>Расписание на неделю ({start} — {end})</b>",
        "lv": "📆 <b>Nodarbību saraksts nedēļai ({start} — {end})</b>",
        "en": "📆 <b>Weekly Schedule ({start} — {end})</b>"
    },
    "current_week_header": {
        "ru": "📆 <b>Расписание на текущую неделю ({start} — {end})</b>",
        "lv": "📆 <b>Šīs nedēļas nodarbību saraksts ({start} — {end})</b>",
        "en": "📆 <b>Current Week Schedule ({start} — {end})</b>"
    },
    "next_week_header": {
        "ru": "📆 <b>Расписание на следующую неделю ({start} — {end})</b>",
        "lv": "📆 <b>Nākamās nedēļas nodarbību saraksts ({start} — {end})</b>",
        "en": "📆 <b>Next Week Schedule ({start} — {end})</b>"
    },
    "btn_prev_week": {
        "ru": "◀️ Текущая неделя ({start} — {end})",
        "lv": "◀️ Šī nedēļa ({start} — {end})",
        "en": "◀️ Current week ({start} — {end})"
    },
    "btn_next_week": {
        "ru": "Следующая неделя ({start} — {end}) ▶️",
        "lv": "Nākamā nedēļa ({start} — {end}) ▶️",
        "en": "Next week ({start} — {end}) ▶️"
    },
    "btn_current_week_home": {
        "ru": "🏠 Текущая неделя ({start} — {end})",
        "lv": "🏠 Šī nedēļa ({start} — {end})",
        "en": "🏠 Current week ({start} — {end})"
    },
    "no_schedule_loaded": {
        "ru": "ℹ️ <b>Расписание для этой программы еще не загружено из LUIS.</b>\n\nНажмите кнопку 🔄 <b>Обновить</b> (или введите <code>/update</code>), чтобы бот автоматически скачал расписание с сайта университета!",
        "lv": "ℹ️ <b>Šīs programmas nodarbību saraksts vēl nav ielādēts no LUIS.</b>\n\nNospiediet pogu 🔄 <b>Atjaunot</b> (vai ievadiet <code>/update</code>), lai bots automātiski lejupielādētu sarakstu no universitātes sistēmas!",
        "en": "ℹ️ <b>Schedule for this program is not loaded from LUIS yet.</b>\n\nClick 🔄 <b>Refresh</b> button (or send <code>/update</code>) to fetch the official schedule from university system!"
    },

    # Radar & Next Class
    "radar_title": {
        "ru": "📍 <b>РАДАР ЗАНЯТИЙ (Время: {time})</b>\n🎓 <i>{prog}</i>\n\n",
        "lv": "📍 <b>NODARBĪBU RADARS (Laiks: {time})</b>\n🎓 <i>{prog}</i>\n\n",
        "en": "📍 <b>CLASS RADAR (Time: {time})</b>\n🎓 <i>{prog}</i>\n\n"
    },
    "radar_in_class": {
        "ru": "🟢 <b>СЕЙЧАС ИДЕТ ЗАНЯТИЕ:</b>",
        "lv": "🟢 <b>PAŠLAIK NOTIEK NODARBĪBA:</b>",
        "en": "🟢 <b>CLASS IN PROGRESS:</b>"
    },
    "radar_progress": {
        "ru": "⏳ До конца: <b>{rem} мин</b> ({pct}% пары прошло)\n[{bar}]\n",
        "lv": "⏳ Līdz beigām: <b>{rem} min</b> ({pct}% no nodarbības pagājuši)\n[{bar}]\n",
        "en": "⏳ Time left: <b>{rem} min</b> ({pct}% passed)\n[{bar}]\n"
    },
    "radar_rem_min": {
        "ru": "До конца занятия: <b>{rem} мин</b>",
        "lv": "Līdz beigām: <b>{rem} min</b>",
        "en": "Time remaining: <b>{rem} min</b>"
    },
    "radar_break": {
        "ru": "☕ <b>СЕЙЧАС ПЕРЕРЫВ МЕЖДУ ПАРАМИ!</b>",
        "lv": "☕ <b>PAŠLAIK IR STARPBRĪDIS!</b>",
        "en": "☕ <b>BREAK BETWEEN CLASSES!</b>"
    },
    "radar_break_desc": {
        "ru": "До следующего занятия осталось: <b>{starts_in} мин</b>\n\n",
        "lv": "Līdz nākamajai nodarbībai atlicis: <b>{starts_in} min</b>\n\n",
        "en": "Time until next class: <b>{starts_in} min</b>\n\n"
    },
    "radar_starts_at": {
        "ru": "⏰ Начало в <b>{time}</b>\n",
        "lv": "⏰ Sākums plkst. <b>{time}</b>\n",
        "en": "⏰ Starts at <b>{time}</b>\n"
    },
    "radar_next_class": {
        "ru": "⏭️ <b>Следующая пара:</b>",
        "lv": "⏭️ <b>Nākamā nodarbība:</b>",
        "en": "⏭️ <b>Next class:</b>"
    },
    "radar_done_today": {
        "ru": "🌙 <b>На сегодня все занятия окончены!</b>",
        "lv": "🌙 <b>Šodien visas nodarbības ir beigušās!</b>",
        "en": "🌙 <b>All classes finished for today!</b>"
    },
    "radar_nearest": {
        "ru": "⏭️ Ближайшее занятие: <b>{when}</b> в <b>{time}</b>:\n📚 <b>{subj}</b>",
        "lv": "⏭️ Tuvākā nodarbība: <b>{when}</b> plkst. <b>{time}</b>:\n📚 <b>{subj}</b>",
        "en": "⏭️ Nearest class: <b>{when}</b> at <b>{time}</b>:\n📚 <b>{subj}</b>"
    },
    "radar_closest_class": {
        "ru": "⏭️ Ближайшее занятие: <b>{when}</b> в <b>{time}</b>:\n📚 <b>{subj}</b> ({room})",
        "lv": "⏭️ Tuvākā nodarbība: <b>{when}</b> plkst. <b>{time}</b>:\n📚 <b>{subj}</b> ({room})",
        "en": "⏭️ Nearest class: <b>{when}</b> at <b>{time}</b>:\n📚 <b>{subj}</b> ({room})"
    },
    "radar_no_classes_today": {
        "ru": "🎉 На сегодня занятий нет! Отдыхаем.",
        "lv": "🎉 Šodien nodarbību nav! Atpūšamies.",
        "en": "🎉 No classes today! Enjoy your free time."
    },
    "when_today": {
        "ru": "сегодня",
        "lv": "šodien",
        "en": "today"
    },

    # Live Sync with LUIS
    "sync_cooldown": {
        "ru": "⏳ <b>Слишком часто!</b>\nОбновлять расписание вручную можно не чаще одного раза в <b>15 минут</b>.\n\nСледующее обновление будет доступно через: <b>{min} мин {sec} сек</b>.",
        "lv": "⏳ <b>Pārāk bieži!</b>\nManuāli atjaunot sarakstu drīkst ne biežāk kā reizi <b>15 minūtēs</b>.\n\nNākamā atjaunošana būs pieejama pēc: <b>{min} min {sec} sek</b>.",
        "en": "⏳ <b>Too frequent!</b>\nYou can manually refresh the schedule once every <b>15 minutes</b>.\n\nNext refresh available in: <b>{min} min {sec} sec</b>."
    },
    "sync_in_progress": {
        "ru": "⏳ <b>Подключаюсь к LUIS и загружаю актуальные данные...</b>\n<i>Это займет около 10-15 секунд.</i>",
        "lv": "⏳ <b>Pieslēdzos LUIS un ielādēju aktuālos datus...</b>\n<i>Tas aizņems apmēram 10-15 sekundes.</i>",
        "en": "⏳ <b>Connecting to LUIS and fetching latest data...</b>\n<i>This will take about 10-15 seconds.</i>"
    },
    "sync_success": {
        "ru": "✅ <b>Расписание успешно обновлено из LUIS!</b>\n\n🎓 Программа: <i>{prog}</i>\n📚 Курс: <b>{course}</b>\n📊 Загружено событий: <b>{count}</b>",
        "lv": "✅ <b>Nodarbību saraksts veiksmīgi atjaunots no LUIS!</b>\n\n🎓 Programma: <i>{prog}</i>\n📚 Kurss: <b>{course}</b>\n📊 Ielādēti notikumi: <b>{count}</b>",
        "en": "✅ <b>Schedule successfully updated from LUIS!</b>\n\n🎓 Program: <i>{prog}</i>\n📚 Course: <b>{course}</b>\n📊 Loaded events: <b>{count}</b>"
    },
    "sync_diffs_title": {
        "ru": "\n\n⚠️ <b>Обнаружены свежие изменения ({count}):</b>\n",
        "lv": "\n\n⚠️ <b>Konstatētas jaunas izmaiņas ({count}):</b>\n",
        "en": "\n\n⚠️ <b>New changes detected ({count}):</b>\n"
    },
    "sync_error": {
        "ru": "❌ Ошибка при синхронизации с LUIS: {err}\nИспользуются сохраненные данные расписания.",
        "lv": "❌ Kļūda, sinhronizējot ar LUIS: {err}\nTiek izmantoti iepriekš saglabātie nodarbību dati.",
        "en": "❌ Error syncing with LUIS: {err}\nUsing cached schedule data."
    },

    # Schedule Search
    "find_usage": {
        "ru": "🔍 <b>Поиск по расписанию</b>\n\nИспользование: <code>/find &lt;название предмета или аудитория&gt;</code>\n\nПримеры:\n• <code>/find Datu bāzes</code>\n• <code>/find 408</code>\n• <code>/find C#</code>",
        "lv": "🔍 <b>Meklēšana nodarbību sarakstā</b>\n\nLietošana: <code>/find &lt;priekšmets vai telpa&gt;</code>\n\nPiemēri:\n• <code>/find Datu bāzes</code>\n• <code>/find 408</code>\n• <code>/find C#</code>",
        "en": "🔍 <b>Schedule Search</b>\n\nUsage: <code>/find &lt;subject or room&gt;</code>\n\nExamples:\n• <code>/find Datu bāzes</code>\n• <code>/find 408</code>\n• <code>/find C#</code>"
    },
    "find_min_len": {
        "ru": "⚠️ Пожалуйста, укажите хотя бы 2 буквы для поиска (например: <code>/find база</code> или <code>/find 113</code>).",
        "lv": "⚠️ Lūdzu, ievadiet vismaz 2 burtus meklēšanai (piemēram: <code>/find datu</code> vai <code>/find 113</code>).",
        "en": "⚠️ Please enter at least 2 characters to search (e.g.: <code>/find data</code> or <code>/find 113</code>)."
    },
    "find_not_found": {
        "ru": "🔍 По запросу «<b>{q}</b>» ничего не найдено в расписании.",
        "lv": "🔍 Pēc vaicājuma «<b>{q}</b>» nodarbību sarakstā nekas netika atrasts.",
        "en": "🔍 No classes found matching «<b>{q}</b>»."
    },
    "find_results_title": {
        "ru": "🔍 <b>Результаты поиска «{q}»</b> (найдено {count} занятий):\n\n",
        "lv": "🔍 <b>Meklēšanas rezultāti «{q}»</b> (atrastas {count} nodarbības):\n\n",
        "en": "🔍 <b>Search results for «{q}»</b> (found {count} classes):\n\n"
    },
    "find_more": {
        "ru": "<i>...и еще {count} занятий в семестре.</i>",
        "lv": "<i>...un vēl {count} nodarbības semestrī.</i>",
        "en": "<i>...and {count} more classes in this semester.</i>"
    },

    # Access & System
    "user_blocked": {
        "ru": "⛔ Доступ к боту ограничен администратором.",
        "lv": "⛔ Piekļuve botam ir liegta.",
        "en": "⛔ Access to the bot is restricted by administrator."
    },
    "maintenance_msg": {
        "ru": "🛠️ Бот временно на техническом обслуживании. Скоро вернемся!",
        "lv": "🛠️ Bots pašlaik atrodas tehniskajā apkopē. Drīz būsim atpakaļ!",
        "en": "🛠️ The bot is currently under maintenance. We will be back soon!"
    },

    # Failsafe & Cancel
    "action_cancelled": {
        "ru": "🔄 <b>Действие отменено, состояние сброшено.</b>\n\nГлавное меню готово к работе! Выберите нужный раздел ниже 👇",
        "lv": "🔄 <b>Darbība atcelta, stāvoklis atiestatīts.</b>\n\nGalvenā izvēlne ir gatava darbam! Izvēlieties vajadzīgo sadaļu zemāk 👇",
        "en": "🔄 <b>Action cancelled, state reset.</b>\n\nMain menu is ready! Select the desired section below 👇"
    },
    "cancel_hint": {
        "ru": "🛑 <i>Если передумали или бот ждёт ввод — отправьте <code>/cancel</code> или напишите «<b>отмена</b>».</i>",
        "lv": "🛑 <i>Lai atceltu, nosūtiet <code>/cancel</code> vai uzrakstiet \"<b>atcelt</b>\".</i>",
        "en": "🛑 <i>To cancel, send <code>/cancel</code> or type \"<b>cancel</b>\".</i>"
    },

    # Teacher Search
    "teacher_search_title": {
        "ru": "👨‍🏫 <b>Поиск преподавателя Даугавпилсского Университета (DU)</b>\n\nВведите фамилию или имя преподавателя (на русском или латышском):\n<i>Например: Ruža, Ружа, Кравалис, Teivāns, Знотиня, Дробишевска...</i>\n\n💡 Или откройте <b>полный каталог всех 236 преподавателей</b> кнопкой ниже.\n\n🛑 <i>Для отмены отправьте <code>/cancel</code> или напишите «<b>отмена</b>».</i>",
        "lv": "👨‍🏫 <b>Daugavpils Universitātes (DU) pasniedzēja meklēšana</b>\n\nIevadiet pasniedzēja uzvārdu vai vārdu (latviešu vai krievu valodā):\n<i>Piemēram: Ruža, Teivāns, Kravale, Znotiņa, Čapļinska...</i>\n\n💡 Vai atveriet <b>visu 236 pasniedzēju katalogu</b> ar pogu zemāk.\n\n🛑 <i>Lai atceltu, nosūtiet <code>/cancel</code> vai uzrakstiet \"<b>atcelt</b>\".</i>",
        "en": "👨‍🏫 <b>Daugavpils University (DU) Faculty Search</b>\n\nEnter the instructor's last name or first name:\n<i>For example: Ruža, Teivans, Kravale, Znotina...</i>\n\n💡 Or open the <b>full directory of 236 faculty members</b> via the button below.\n\n🛑 <i>To cancel, send <code>/cancel</code> or type \"<b>cancel</b>\".</i>"
    },
    "teacher_catalog_btn": {
        "ru": "📚 Полный каталог преподавателей (/teacher all)",
        "lv": "📚 Pilns pasniedzēju katalogs (/teacher all)",
        "en": "📚 Full Faculty Directory (/teacher all)"
    },
    "teacher_not_found": {
        "ru": "❌ Преподаватель по запросу «<b>{q}</b>» не найден в каталоге DU (236 преподавателей).\n\n💡 Попробуйте ввести часть фамилии (например: <code>Руж</code> или <code>Ruza</code>).\n🛑 <i>Для отмены отправьте <code>/cancel</code> или напишите «<b>отмена</b>».</i>",
        "lv": "❌ Pasniedzējs pēc pieprasījuma «<b>{q}</b>» netika atrasts DU katalogā (236 pasniedzēji).\n\n💡 Mēģiniet ievadīt daļu uzvārda (piem.: <code>Ruž</code> vai <code>Teiv</code>).\n🛑 <i>Lai atceltu, nosūtiet <code>/cancel</code> vai uzrakstiet \"<b>atcelt</b>\".</i>",
        "en": "❌ Instructor matching «<b>{q}</b>» not found in DU directory (236 faculty members).\n\n💡 Try entering part of the surname (e.g. <code>Ruz</code> or <code>Teiv</code>).\n🛑 <i>To cancel, send <code>/cancel</code> or type \"<b>cancel</b>\".</i>"
    },

    # Settings Menu
    "settings_title": {
        "ru": "⚙️ <b>Настройки расписания</b>\n\n🎓 <b>Текущая программа:</b>\n{prog}\n\n📚 <b>Текущий курс:</b> <b>{course}</b>\n🌐 <b>Язык интерфейса:</b> <b>{lang_name}</b>\n\n<i>Выберите нужное действие кнопками ниже:</i>",
        "lv": "⚙️ <b>Nodarbību saraksta iestatījumi</b>\n\n🎓 <b>Pašreizējā programma:</b>\n{prog}\n\n📚 <b>Pašreizējais kurss:</b> <b>{course}</b>\n🌐 <b>Saskarnes valoda:</b> <b>{lang_name}</b>\n\n<i>Izvēlieties darbību zemāk:</i>",
        "en": "⚙️ <b>Schedule Settings</b>\n\n🎓 <b>Current Program:</b>\n{prog}\n\n📚 <b>Current Year:</b> <b>{course}</b>\n🌐 <b>Interface Language:</b> <b>{lang_name}</b>\n\n<i>Choose an action below:</i>"
    },
    "btn_choose_faculty": {
        "ru": "🏛️ Выбрать факультет и программу",
        "lv": "🏛️ Izvēlēties fakultāti un programmu",
        "en": "🏛️ Choose Faculty & Program"
    },
    "btn_change_language": {
        "ru": "🌐 Сменить язык / Change Language",
        "lv": "🌐 Mainīt valodu / Change Language",
        "en": "🌐 Change Language"
    },
    "choose_language_prompt": {
        "ru": "🌐 <b>Выберите язык интерфейса бота:</b>\n<i>Valodas izvēle / Language selection:</i>",
        "lv": "🌐 <b>Izvēlieties bota saskarnes valodu:</b>\n<i>Valodas izvēle / Language selection:</i>",
        "en": "🌐 <b>Select bot interface language:</b>\n<i>Valodas izvēle / Language selection:</i>"
    },
    "language_changed": {
        "ru": "✅ Язык успешно переключен на <b>Русский</b>!",
        "lv": "✅ Valoda veiksmīgi nomainīta uz <b>Latviešu</b>!",
        "en": "✅ Language successfully changed to <b>English</b>!"
    },

    # Day selection prompt
    "select_day_prompt": {
        "ru": "📅 <b>Выберите день недели:</b>\n\n💡 <i>Или используйте поиск по названию/аудитории:</i> <code>/find &lt;предмет&gt;</code>",
        "lv": "📅 <b>Izvēlieties nedēļas dienu:</b>\n\n💡 <i>Vai meklējiet pēc priekšmeta/telpas:</i> <code>/find &lt;nosaukums&gt;</code>",
        "en": "📅 <b>Select day of the week:</b>\n\n💡 <i>Or search by subject/room:</i> <code>/find &lt;subject&gt;</code>"
    },

    # Support & Feedback
    "support_prompt": {
        "ru": "🆘 <b>Служба поддержки</b>\n\nОпишите ваш вопрос или проблему в ответном сообщении, и администраторы ответят вам здесь в ближайшее время!\n\n🛑 <i>(Для отмены напишите <code>/cancel</code> или «<b>отмена</b>»)</i>",
        "lv": "🆘 <b>Atbalsta dienests</b>\n\nAprakstiet savu jautājumu vai problēmu atbildes ziņojumā, un administratori drīzumā jums atbildēs tepat!\n\n🛑 <i>(Lai atceltu, nosūtiet <code>/cancel</code> vai uzrakstiet \"<b>atcelt</b>\")</i>",
        "en": "🆘 <b>Support Helpdesk</b>\n\nDescribe your inquiry or issue in your reply, and administrators will respond to you right here shortly!\n\n🛑 <i>(To cancel, send <code>/cancel</code> or type \"<b>cancel</b>\")</i>"
    },
    "suggest_prompt": {
        "ru": "💡 <b>Предложение по улучшению</b>\n\nКакую функцию или новую возможность вы бы хотели видеть в боте? Напишите вашу идею, и мы обязательно рассмотрим её!\n\n🛑 <i>(Для отмены напишите <code>/cancel</code> или «<b>отмена</b>»)</i>",
        "lv": "💡 <b>Ieteikums uzlabojumam</b>\n\nKādu funkciju vai jaunu iespēju jūs vēlētos redzēt botā? Uzrakstiet savu ideju, un mēs to noteikti izskatīsim!\n\n🛑 <i>(Lai atceltu, nosūtiet <code>/cancel</code> vai uzrakstiet \"<b>atcelt</b>\")</i>",
        "en": "💡 <b>Feature Suggestion</b>\n\nWhat feature or enhancement would you like to see in the bot? Share your thoughts, and we will definitely review them!\n\n🛑 <i>(To cancel, send <code>/cancel</code> or type \"<b>cancel</b>\")</i>"
    },
    "ticket_sent": {
        "ru": "✅ <b>Ваше сообщение (Тикет #{id}) успешно отправлено администраторам!</b>",
        "lv": "✅ <b>Jūsu ziņojums (Biļete #{id}) ir veiksmīgi nosūtīts administratoriem!</b>",
        "en": "✅ <b>Your message (Ticket #{id}) was successfully sent to administrators!</b>"
    },

    # Welcome / Start Message
    "start_welcome": {
        "ru": (
            "👋 Привет, <b>{name}</b>! Добро пожаловать в <b>DU Schedule Bot</b> 🎓\n\n"
            "Мы — студенты Даугавпилсского Университета, создавшие этого бота, чтобы расписание всегда было под рукой быстро и удобно.\n\n"
            "📌 <b>Что умеет бот:</b>\n"
            "• 📅 <b>Расписание на сегодня, завтра и всю неделю</b> — актуальные пары, время и аудитории с учетом всех изменений.\n"
            "• ⏰ <b>«След. пара»</b> — покажет текущую пару или время до начала следующей.\n"
            "• 👨‍🏫 <b>«Поиск преподавателя»</b> (<code>/teacher</code>) — поиск любого преподавателя DU, где у него сейчас пара и аудитория.\n"
            "• 🔄 <b>Прямая синхронизация с LUIS</b> — обновления данных в один клик.\n\n"
            "💡 <b>Бот в активной разработке:</b>\n"
            "Если бот ждет ввод (например, поиск преподавателя или тикет) или если что-то зависло — просто отправьте <code>/cancel</code> (или напишите «<b>отмена</b>»). Бот моментально сбросит ожидание и вернет главное меню!\n\n"
            "🎓 <b>Ваш профиль:</b>\n"
            "• Программа: <b>{prog}</b>\n"
            "• Курс: <b>{sem}</b>\n"
            "• Язык: <b>{lang_name}</b>\n\n"
            "⚙️ <i>Вы всегда можете изменить программу, курс и язык в меню «⚙️ Настройки».</i>\n\n"
            "👇 Выберите нужное действие на клавиатуре ниже:"
        ),
        "lv": (
            "👋 Sveicināti, <b>{name}</b>! Laipni lūgti <b>DU Schedule Bot</b> 🎓\n\n"
            "Mēs esam Daugavpils Universitātes studenti, kas izveidoja šo botu, lai nodarbību saraksts vienmēr būtu ērti un ātri pieejams.\n\n"
            "📌 <b>Bota iespējas:</b>\n"
            "• 📅 <b>Saraksts šodienai, rītdienai un visai nedēļai</b> — aktuālās nodarbības, laiki un telpas ar visām izmaiņām.\n"
            "• ⏰ <b>«Nākamā nodarbība»</b> — parādīs pašreizējo nodarbību vai laiku līdz nākamajai.\n"
            "• 👨‍🏫 <b>«Pasniedzēja meklēšana»</b> (<code>/teacher</code>) — uzziniet, kur pasniedzējam pašlaik notiek lekcija.\n"
            "• 🔄 <b>Tiešā sinhronizācija ar LUIS</b> — jaunākie dati ar vienu klikšķi.\n\n"
            "💡 <b>Bots aktīvi attīstās:</b>\n"
            "Ja bots gaida teksta ievadi vai vēlaties atgriezties izvēlnē — vienkārši nosūtiet <code>/cancel</code> (vai uzrakstiet \"<b>atcelt</b>\"). Bots uzreiz atiestatīs stāvokli un atgriezīs galveno izvēlni!\n\n"
            "🎓 <b>Jūsu profils:</b>\n"
            "• Programma: <b>{prog}</b>\n"
            "• Kurss: <b>{sem}</b>\n"
            "• Valoda: <b>{lang_name}</b>\n\n"
            "⚙️ <i>Jūs vienmēr varat mainīt programmu, kursu un valodu sadaļā «⚙️ Iestatījumi».</i>\n\n"
            "👇 Izvēlieties vajadzīgo darbību tastatūrā zemāk:"
        ),
        "en": (
            "👋 Hello, <b>{name}</b>! Welcome to <b>DU Schedule Bot</b> 🎓\n\n"
            "We are Daugavpils University students who built this bot to make the timetable fast, clear, and convenient for everyone.\n\n"
            "📌 <b>Key Features:</b>\n"
            "• 📅 <b>Today, Tomorrow & Full Week Timetable</b> — verified classes, exact timings, and classrooms.\n"
            "• ⏰ <b>«Next class» Radar</b> — displays your active class or countdown to the next one.\n"
            "• 👨‍🏫 <b>«Faculty Search»</b> (<code>/teacher</code>) — find where any DU professor is teaching right now.\n"
            "• 🔄 <b>Live LUIS Sync</b> — fetch the freshest updates with one click.\n\n"
            "💡 <b>Active Development Notice:</b>\n"
            "If the bot is awaiting text input or if you ever want to reset — just send <code>/cancel</code> (or type \"<b>cancel</b>\"). The bot instantly resets to the main menu!\n\n"
            "🎓 <b>Your Profile:</b>\n"
            "• Program: <b>{prog}</b>\n"
            "• Year/Sem: <b>{sem}</b>\n"
            "• Language: <b>{lang_name}</b>\n\n"
            "⚙️ <i>You can adjust your program, study year, and language anytime in «⚙️ Settings».</i>\n\n"
            "👇 Choose an action on the keyboard below:"
        )
    },

    # Help / FAQ
    "help_faq": {
        "ru": (
            "ℹ️ <b>Справка по использованию DU Schedule Bot (FAQ)</b>\n\n"
            "Бот создан студентами для всего сообщества Даугавпилсского университета, чтобы сделать доступ к расписанию быстрым, точным и удобным.\n\n"
            "📌 <b>Основные возможности и кнопки:</b>\n"
            "• 📅 <b>Сегодня</b> (<code>/today</code>) — пары на сегодня со временем, аудиториями, типами занятий и преподавателями.\n"
            "• ⏭️ <b>Завтра</b> (<code>/tomorrow</code>) — расписание на следующий день.\n"
            "• 📆 <b>Вся неделя</b> (<code>/week</code>) — расписание недели с удобным переключением <code>◀️</code> / <code>▶️</code>. В конце недели бот сам подскажет расписание на следующую неделю!\n"
            "• ⏰ <b>След. пара</b> (<code>/next</code>) — радар в реальном времени: какая пара идет прямо сейчас и сколько минут осталось, либо когда начнется следующая.\n"
            "• 👨‍🏫 <b>Поиск препода</b> (<code>/teacher</code>) — где у преподавателя сейчас пара, расписание на неделю и каталог из 236 преподавателей (<code>/teacher all</code>).\n"
            "• 🔍 <b>Поиск / Выбор дня</b> (<code>/day</code>) — расписание на конкретный день или поиск по названию предмета, аудитории и типу занятия.\n"
            "• 🔄 <b>Обновить</b> (<code>/update</code>) — синхронизация расписания напрямую из системы LUIS.\n"
            "• ⚙️ <b>Настройки</b> (<code>/settings</code>) — факультет, программа, курс/семестр, выбор своей группы/подгруппы и язык интерфейса.\n\n"
            "👥 <b>Группы и фильтрация занятий:</b>\n"
            "В <b>⚙️ Настройки</b> доступен выбор академической группы: если на вашем курсе есть разделение (лабораторные, практики, потоки), бот скроет чужие пары и покажет только ваши занятия и общие лекции. Если группа одна — лишних надписей не будет.\n\n"
            "🛑 <b>Как отменить ввод или вернуться в меню?</b>\n"
            "Если бот ожидает текст (при поиске преподавателя или обращении в поддержку):\n"
            "👉 Отправьте <code>/cancel</code> (или напишите «<b>отмена</b>», «<b>stop</b>», либо нажмите любую кнопку нижнего меню). Ожидание мгновенно сбросится!\n\n"
            "🆘 <b>Нужна помощь или есть идея?</b>\n"
            "Откройте <b>⚙️ Настройки</b> и нажмите <b>«🆘 Поддержка»</b> или <b>«💡 Предложить улучшение»</b> — администраторы оперативно помогут!"
        ),
        "lv": (
            "ℹ️ <b>DU Schedule Bot lietošanas pamācība (FAQ)</b>\n\n"
            "Bots ir studentu veidots projekts Daugavpils Universitātes studentiem un mācībspēkiem, lai nodrošinātu ātru, precīzu un ērtu piekļuvi nodarbību sarakstam.\n\n"
            "📌 <b>Galvenās iespējas un pogas:</b>\n"
            "• 📅 <b>Šodien</b> (<code>/today</code>) — šīs dienas nodarbības ar laikiem, auditorijām, nodarbību veidiem un pasniedzējiem.\n"
            "• ⏭️ <b>Rīt</b> (<code>/tomorrow</code>) — nākamās dienas nodarbību saraksts.\n"
            "• 📆 <b>Visa nedēļa</b> (<code>/week</code>) — pilns nedēļas saraksts ar ērto pārslēgšanu <code>◀️</code> / <code>▶️</code>. Nedēļas nogalē bots automātiski atver nākamo nedēļu!\n"
            "• ⏰ <b>Nākamā nodarbība</b> (<code>/next</code>) — reāllaika radars: kura nodarbība notiek pašlaik un cik minūtes palikušas, vai cikos sāksies nākamā.\n"
            "• 👨‍🏫 <b>Pasniedzēja meklēšana</b> (<code>/teacher</code>) — kur pasniedzējam pašlaik ir lekcija, pasniedzēja nedēļas saraksts un visu 236 pasniedzēju katalogs (<code>/teacher all</code>).\n"
            "• 🔍 <b>Dienas izvēle / Meklēšana</b> (<code>/day</code>) — saraksts konkrētai dienai vai meklēšana pēc priekšmeta nosaukuma, auditorijas vai veida.\n"
            "• 🔄 <b>Atjaunot</b> (<code>/update</code>) — datu sinhronizācija tieši no LUIS sistēmas.\n"
            "• ⚙️ <b>Iestatījumi</b> (<code>/settings</code>) — fakultāte, studiju programma, kurss/semestris, akadēmiskās grupas izvēle un valoda.\n\n"
            "👥 <b>Grupas un nodarbību filtrēšana:</b>\n"
            "Sadaļā <b>⚙️ Iestatījumi</b> varat izvēlēties savu akadēmisko grupu vai plūsmu: bots paslēps citu grupu nodarbības un parādīs tikai jūsu nodarbības un kopīgās lekcijas.\n\n"
            "🛑 <b>Kā atcelt ievadi vai atgriezties izvēlnē?</b>\n"
            "Ja bots gaida teksta ievadi (meklējot pasniedzēju vai rakstot atbalstam):\n"
            "👉 Nosūtiet <code>/cancel</code> (vai uzrakstiet \"<b>atcelt</b>\", \"<b>stop</b>\", vai vienkārši nospiediet jebkuru izvēlnes pogu). Gaidīšana tiks nekavējoties atcelta!\n\n"
            "🆘 <b>Nepieciešama palīdzība vai ir ideja?</b>\n"
            "Atveriet <b>⚙️ Iestatījumi</b> un nospiediet <b>«🆘 Atbalsts»</b> vai <b>«💡 Ieteikt uzlabojumu»</b> — administratori jums ātri atbildēs!"
        ),
        "en": (
            "ℹ️ <b>DU Schedule Bot User Guide (FAQ)</b>\n\n"
            "Created by students for the Daugavpils University community to provide fast, reliable, and convenient timetable access.\n\n"
            "📌 <b>Core Features and Buttons:</b>\n"
            "• 📅 <b>Today</b> (<code>/today</code>) — today's classes with rooms, times, lesson types, and instructors.\n"
            "• ⏭️ <b>Tomorrow</b> (<code>/tomorrow</code>) — schedule for tomorrow.\n"
            "• 📆 <b>Full Week</b> (<code>/week</code>) — complete weekly timetable with easy <code>◀️</code> / <code>▶️</code> navigation. Towards the weekend, the bot automatically previews the upcoming week!\n"
            "• ⏰ <b>Next Class</b> (<code>/next</code>) — live radar showing the class currently in progress (with remaining time) or when the next class begins.\n"
            "• 👨‍🏫 <b>Find Teacher</b> (<code>/teacher</code>) — find where an instructor is teaching right now, view their weekly timetable, and explore the directory of 236 professors (<code>/teacher all</code>).\n"
            "• 🔍 <b>Select Day / Search</b> (<code>/day</code>) — view schedule for any specific weekday or search classes by subject, room, or lecture type.\n"
            "• 🔄 <b>Refresh</b> (<code>/update</code>) — fetch the latest schedule directly from the LUIS system.\n"
            "• ⚙️ <b>Settings</b> (<code>/settings</code>) — change faculty, study program, year/semester, academic group, or interface language.\n\n"
            "👥 <b>Groups and Timetable Filtering:</b>\n"
            "In <b>⚙️ Settings</b>, you can select your academic group or stream: the bot filters out other groups' classes, displaying only your practicals and common lectures.\n\n"
            "🛑 <b>How to cancel input or return to the menu?</b>\n"
            "If the bot is awaiting text input (when searching for a teacher or submitting feedback):\n"
            "👉 Send <code>/cancel</code> (or type \"<b>cancel</b>\", \"<b>stop</b>\", or simply tap any menu button). The bot will immediately reset the waiting state!\n\n"
            "🆘 <b>Need help or have an idea?</b>\n"
            "Go to <b>⚙️ Settings</b> and tap <b>«🆘 Support»</b> or <b>«💡 Suggest Feature»</b> — our administrators will respond promptly!"
        )
    },

    # Ticket replies & Direct messages
    "ticket_reply_header": {
        "ru": "💬 <b>Ответ от службы поддержки ({sender}){label}:</b>\n\n",
        "lv": "💬 <b>Atbilde no atbalsta dienesta ({sender}){label}:</b>\n\n",
        "en": "💬 <b>Reply from Support Team ({sender}){label}:</b>\n\n"
    },
    "ticket_label_support": {
        "ru": " по вашему обращению (Тикет #{ticket_id})",
        "lv": " par jūsu pieteikumu (Biļete #{ticket_id})",
        "en": " regarding your ticket (#{ticket_id})"
    },
    "ticket_label_suggestion": {
        "ru": " по вашему предложению (Тикет #{ticket_id})",
        "lv": " par jūsu ieteikumu (Biļete #{ticket_id})",
        "en": " regarding your suggestion (Ticket #{ticket_id})"
    },
    "ticket_quote_header": {
        "ru": "<b>Ваше сообщение:</b>\n<blockquote>{orig_text}</blockquote>\n\n",
        "lv": "<b>Jūsu ziņa:</b>\n<blockquote>{orig_text}</blockquote>\n\n",
        "en": "<b>Your message:</b>\n<blockquote>{orig_text}</blockquote>\n\n"
    },
    "ticket_reply_body_title": {
        "ru": "<b>Ответ:</b>\n{reply_text}",
        "lv": "<b>Atbilde:</b>\n{reply_text}",
        "en": "<b>Reply:</b>\n{reply_text}"
    },
    "direct_msg_header": {
        "ru": "💬 <b>Сообщение от: {sender}</b>\n\n{text}",
        "lv": "💬 <b>Ziņa no: {sender}</b>\n\n{text}",
        "en": "💬 <b>Message from: {sender}</b>\n\n{text}"
    },
    "user_warned_msg": {
        "ru": "⚠️ <b>Предупреждение от администрации ({warn}/3)</b>\n\nПожалуйста, соблюдайте правила и воздержитесь от спама или некорректных сообщений. При получении 3 предупреждений вы будете заблокированы.",
        "lv": "⚠️ <b>Brīdinājums no administrācijas ({warn}/3)</b>\n\nLūdzu, ievērojiet noteikumus un atturieties no surogātpasta vai nekorektām ziņām. Saņemot 3 brīdinājumus, jūs tiksiet bloķēts.",
        "en": "⚠️ <b>Warning from administration ({warn}/3)</b>\n\nPlease follow the rules and refrain from spam or inappropriate messages. Upon receiving 3 warnings, you will be banned."
    },
    "user_banned_3warns_msg": {
        "ru": "🚫 <b>Вы были заблокированы в боте</b>\n\nВы получили 3/3 предупреждений за спам или нарушение правил. Доступ к боту закрыт.",
        "lv": "🚫 <b>Jūs tikāt bloķēts botā</b>\n\nJūs saņēmāt 3/3 brīdinājumus par surogātpastu vai noteikumu pārkāpšanu. Piekļuve botam ir slēgta.",
        "en": "🚫 <b>You have been banned from the bot</b>\n\nYou received 3/3 warnings for spam or rule violations. Access to the bot is restricted."
    },
    "user_unwarned_msg": {
        "ru": "💚 <b>С вас снято 1 предупреждение!</b>\n\nТекущее количество страйков: <b>{warn}/3</b>.",
        "lv": "💚 <b>Jums tika noņemts 1 brīdinājums!</b>\n\nPašreizējais brīdinājumu skaits: <b>{warn}/3</b>.",
        "en": "💚 <b>1 warning has been removed!</b>\n\nCurrent active strikes: <b>{warn}/3</b>."
    },
    "user_unblocked_note": {
        "ru": "\n\nВаш доступ к боту <b>разблокирован</b>. Соблюдайте правила!",
        "lv": "\n\nJūsu piekļuve botam ir <b>atbloķēta</b>. Lūdzu, ievērojiet noteikumus!",
        "en": "\n\nYour access to the bot has been <b>restored</b>. Please follow the rules!"
    },
    "user_manually_blocked_msg": {
        "ru": "🚫 <b>Вы были заблокированы администратором бота.</b>",
        "lv": "🚫 <b>Bota administrators ir bloķējis jūsu piekļuvi.</b>",
        "en": "🚫 <b>You have been banned by the bot administrator.</b>"
    },
    "week_empty_day": {
        "ru": "📅 <b>{day} ({date})</b> — занятий нет",
        "lv": "📅 <b>{day} ({date})</b> — nodarbību nav",
        "en": "📅 <b>{day} ({date})</b> — no classes"
    },
    "week_holiday_day": {
        "ru": "🎉 <b>{day} ({date})</b> — выходной день",
        "lv": "🎉 <b>{day} ({date})</b> — brīvdiena",
        "en": "🎉 <b>{day} ({date})</b> — day off (holiday)"
    },
    "broadcast_header": {
        "ru": "📢 <b>Объявление от {sender}:</b>\n\n{text}",
        "lv": "📢 <b>Paziņojums no {sender}:</b>\n\n{text}",
        "en": "📢 <b>Announcement from {sender}:</b>\n\n{text}"
    },
    "btn_choose_subgroup": {
        "ru": "👥 Выбрать группу",
        "lv": "👥 Izvēlēties grupu",
        "en": "👥 Choose group"
    },
    "subgroup_prompt": {
        "ru": (
            "👥 <b>Выберите вашу академическую группу:</b>\n\n"
            "В программе <i>Valodu un kultūras studijas (D02DO)</i> занятия делятся по группам. "
            "Выберите свою группу, чтобы в расписании отображались только ваши пары и общие лекции (<i>Visām grupām</i>):"
        ),
        "lv": (
            "👥 <b>Izvēlieties savu akadēmisko grupu:</b>\n\n"
            "Programmā <i>Valodu un kultūras studijas (D02DO)</i> nodarbības ir sadalītas pa grupām. "
            "Izvēlieties savu grupu, lai redzētu tikai savas nodarbības un kopīgās lekcijas (<i>Visām grupām</i>):"
        ),
        "en": (
            "👥 <b>Choose your academic group:</b>\n\n"
            "In the <i>Language and Culture Studies (D02DO)</i> program, classes are divided by group. "
            "Choose your group to see your classes and common lectures (<i>Visām grupām</i>):"
        )
    },
    "subgroup_prompt_generic": {
        "ru": (
            "👥 <b>Выберите вашу академическую группу:</b>\n\n"
            "В программе <i>{prog}</i> ({course}) занятия разделены по группам. "
            "Выберите свою группу, чтобы в расписании отображались только ваши пары и общие лекции (<i>Visām grupām</i>):"
        ),
        "lv": (
            "👥 <b>Izvēlieties savu akadēmisko grupu:</b>\n\n"
            "Programmā <i>{prog}</i> ({course}) nodarbības ir sadalītas pa grupām. "
            "Izvēlieties savu grupu, lai redzētu tikai savas nodarbības un kopīgās lekcijas (<i>Visām grupām</i>):"
        ),
        "en": (
            "👥 <b>Choose your academic group:</b>\n\n"
            "In program <i>{prog}</i> ({course}), classes are divided by group. "
            "Select your group to see your classes and shared lectures (<i>Visām grupām</i>):"
        )
    },
    "subgroup_single_info": {
        "ru": "ℹ️ На вашем курсе единая группа — разделения нет, все учатся вместе!",
        "lv": "ℹ️ Jūsu kursā ir vienota grupa — sadalījuma nav, visi mācās kopā!",
        "en": "ℹ️ Your course has a single group — all students study together!"
    },
    "subgroup_btn_single": {
        "ru": "👥 Группа: Единая (без разделения)",
        "lv": "👥 Grupa: Vienota (nav sadalījuma)",
        "en": "👥 Group: Single (no division)"
    }
}

D02DO_SUBGROUPS: Dict[str, Dict[str, str]] = {
    "ANGST": {
        "code": "ANGST",
        "ru": "🇬🇧 Английская филология (ANGST)",
        "lv": "🇬🇧 Angļu filoloģija (ANGST)",
        "en": "🇬🇧 English Philology (ANGST)",
        "short_ru": "🇬🇧 Английская филология",
        "short_lv": "🇬🇧 Angļu filoloģija",
        "short_en": "🇬🇧 English Philology",
    },
    "RUSST": {
        "code": "RUSST",
        "ru": "🇷🇺 Русская филология (RUSST)",
        "lv": "🇷🇺 Krievu filoloģija (RUSST)",
        "en": "🇷🇺 Russian Philology (RUSST)",
        "short_ru": "🇷🇺 Русская филология",
        "short_lv": "🇷🇺 Krievu filoloģija",
        "short_en": "🇷🇺 Russian Philology",
    },
    "LATST": {
        "code": "LATST",
        "ru": "🇱🇻 Латышская филология (LATST)",
        "lv": "🇱🇻 Latviešu filoloģija (LATST)",
        "en": "🇱🇻 Latvian Philology (LATST)",
        "short_ru": "🇱🇻 Латышская филология",
        "short_lv": "🇱🇻 Latviešu filoloģija",
        "short_en": "🇱🇻 Latvian Philology",
    },
    "ALL": {
        "code": "ALL",
        "ru": "👥 Все группы (без фильтра)",
        "lv": "👥 Visas grupas (bez filtra)",
        "en": "👥 All groups (no filter)",
        "short_ru": "👥 Все группы",
        "short_lv": "👥 Visas grupas",
        "short_en": "👥 All groups",
    }
}

def get_d02do_subgroup_label(subgroup_code: str, lang: str = "ru", short: bool = False) -> str:
    """Return formatted label for a D02DO subgroup/stream."""
    if not subgroup_code:
        subgroup_code = "ALL"
    sg = D02DO_SUBGROUPS.get(str(subgroup_code).strip().upper(), D02DO_SUBGROUPS["ALL"])
    key = f"short_{lang}" if short else lang
    return sg.get(key, sg.get(lang, str(subgroup_code)))

def get_subgroup_label(prog_code: str, subgroup_code: str, lang: str = "ru", short: bool = False) -> str:
    """Return formatted label for any program's subgroup/stream."""
    if not subgroup_code or str(subgroup_code).strip().upper() == "ALL":
        lbls = {
            "ru": "👥 Все группы" if short else "👥 Все группы (без фильтра)",
            "lv": "👥 Visas grupas" if short else "👥 Visas grupas (bez filtra)",
            "en": "👥 All groups" if short else "👥 All groups (no filter)"
        }
        return lbls.get(lang, "👥 Все группы")

    code_str = str(subgroup_code).strip()
    if prog_code == "D02DO":
        return get_d02do_subgroup_label(code_str, lang=lang, short=short)

    m = re.match(r"^(\d+)", code_str)
    if m:
        num = m.group(1)
        if short:
            lbls = {
                "ru": f"👥 {num}-я группа",
                "lv": f"👥 {num}. grupa",
                "en": f"👥 Group {num}"
            }
        else:
            lbls = {
                "ru": f"👥 {num}-я группа",
                "lv": f"👥 {num}. grupa",
                "en": f"👥 Group {num}"
            }
        return lbls.get(lang, f"👥 {num}. grupa")

    return f"👥 {code_str}"


def get_t(key: str, lang_code: str = "ru", **kwargs) -> str:
    """Retrieve localized string with safe fallback to Russian."""
    if lang_code not in ["ru", "lv", "en"]:
        lang_code = "ru"
    entry = STRINGS.get(key)
    if not entry:
        return key
    text = entry.get(lang_code) or entry.get("ru", key)
    if kwargs:
        if "lang_name" in kwargs and "lang" not in kwargs:
            kwargs["lang"] = kwargs["lang_name"]
        elif "lang" in kwargs and "lang_name" not in kwargs:
            kwargs["lang_name"] = kwargs["lang"]
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def get_semester_label(sem_num: int, lang: str = "ru") -> str:
    """Format semester and academic course/year label."""
    # Mapping for Autumn semester: 1->1, 2->1, 3->3, 4->3, 5->5, 6->5, 7->7, 8->7
    sem_map = {1: 1, 2: 1, 3: 3, 4: 3, 5: 5, 6: 5, 7: 7, 8: 7}
    mapped = sem_map.get(sem_num, sem_num)
    course_num = (mapped + 1) // 2
    if lang == "lv":
        return f"{course_num}. kurss / {mapped}. sem."
    elif lang == "en":
        return f"Year {course_num} / Sem {mapped}"
    return f"{course_num} курс / {mapped} сем."

def get_weekday_name(wday_idx: int, lang: str = "ru") -> str:
    """Return localized weekday name (0 = Monday, 6 = Sunday)."""
    lst = WEEKDAYS.get(lang) or WEEKDAYS["ru"]
    return lst[wday_idx % 7]

def get_clean_lesson_type(ltype_raw: str, lang: str = "ru") -> str:
    """Normalize and localize lesson type."""
    if not ltype_raw:
        return ""
    low = ltype_raw.lower()
    types_map = LESSON_TYPES.get(lang) or LESSON_TYPES["ru"]
    if "prakt" in low or "laborat" in low:
        return types_map["Prakt"]
    elif "lekcij" in low:
        return types_map["Lekcij"]
    elif "semin" in low:
        return types_map["Semin"]
    base = ltype_raw.split("[")[0].strip()
    return base


def format_event_group(group_raw: str, lang: str = "ru", show_all_groups: bool = True) -> str:
    """Normalize and localize group/audience information for schedule events."""
    if not group_raw:
        return ""

    if lang not in ["ru", "lv", "en"]:
        lang = "ru"

    g_clean = group_raw.strip()

    # Pure 'Visām grupām'
    if g_clean.lower() in ["visām grupām", "visam grupam"]:
        if not show_all_groups:
            return ""
        if lang == "ru":
            return "👥 Все группы"
        elif lang == "en":
            return "👥 All groups"
        else:
            return "👥 Visām grupām"

    # Combined groups with 'kopā' (e.g. 'No 09:00 1. un 2. gr. kopā' or '1. un 2. gr. kopā')
    if "kopā" in g_clean.lower() or "kopa" in g_clean.lower():
        if "1" in g_clean and "2" in g_clean:
            if lang == "ru":
                return "👥 1-я и 2-я группы вместе"
            elif lang == "en":
                return "👥 Groups 1 & 2 together"
            else:
                return "👥 1. un 2. grupa kopā"
        else:
            if lang == "ru":
                return f"👥 Все группы вместе ({g_clean})"
            elif lang == "en":
                return f"👥 Groups together ({g_clean})"
            else:
                return f"👥 Grupas kopā ({g_clean})"

    # Stream with Visām grupām, e.g. 'RUSST a.prog. • Visām grupām'
    m_stream = re.match(r"^([A-Za-z0-9]+)\s+a\.prog\.\s*(?:•\s*Visām grupām)?$", g_clean, re.IGNORECASE)
    if m_stream:
        prog_name = m_stream.group(1).upper()
        if "visām" in g_clean.lower() or "visam" in g_clean.lower():
            if lang == "ru":
                return f"👥 {prog_name} (Все группы)"
            elif lang == "en":
                return f"👥 {prog_name} (All groups)"
            else:
                return f"👥 {prog_name} (Visām grupām)"
        else:
            return f"👥 {prog_name}"

    # Specific groups with optional specialization: e.g. '1.grupa (programmēšanas inženieris)', '2.grupa', '3. grupa'
    m_grp = re.match(r"^(\d+)\s*\.?\s*grupa(?:\s*\((.*?)\))?$", g_clean, re.IGNORECASE)
    if m_grp:
        num = m_grp.group(1)
        spec = (m_grp.group(2) or "").strip()
        spec_trans = {
            "programmēšanas inženieris": {
                "ru": "инженер-программист",
                "lv": "programmēšanas inženieris",
                "en": "software engineer"
            },
            "fizioterapija": {
                "ru": "физиотерапия",
                "lv": "fizioterapija",
                "en": "physiotherapy"
            }
        }

        spec_text = ""
        if spec:
            s_dict = spec_trans.get(spec.lower())
            if s_dict:
                spec_text = f" ({s_dict.get(lang, spec)})"
            else:
                spec_text = f" ({spec})"

        if lang == "ru":
            return f"👥 {num}-я группа{spec_text}"
        elif lang == "en":
            return f"👥 Group {num}{spec_text}"
        else:
            return f"👥 {num}. grupa{spec_text}"

    # Known tracks/specializations
    tracks = {
        "ķīniešu valoda": {"ru": "Китайский язык", "lv": "Ķīniešu valoda", "en": "Chinese language"},
        "vācu valoda": {"ru": "Немецкий язык", "lv": "Vācu valoda", "en": "German language"},
        "franču valoda": {"ru": "Французский язык", "lv": "Franču valoda", "en": "French language"},
        "rusistikas studijas ar specializāciju krievu filoloģijā": {
            "ru": "Русская филология",
            "lv": "Krievu filoloģija",
            "en": "Russian Philology"
        },
        "latviešu valoda kā otra valoda": {
            "ru": "Латышский как второй язык",
            "lv": "Latviešu valoda kā otra valoda",
            "en": "Latvian as a second language"
        }
    }

    t_match = tracks.get(g_clean.lower())
    if t_match:
        return f"👥 {t_match.get(lang, g_clean)}"

    return f"👥 {g_clean}"



def format_ticket_reply(
    sender: str,
    ticket_id: Optional[int] = None,
    ticket_type: Optional[str] = None,
    orig_text: Optional[str] = None,
    reply_text: str = "",
    lang: str = "ru"
) -> str:
    """Format localized reply to student's support or suggestion ticket."""
    if lang not in ["ru", "lv", "en"]:
        lang = "ru"
    label = ""
    if ticket_id:
        if ticket_type == "suggestion":
            label = get_t("ticket_label_suggestion", lang, ticket_id=ticket_id)
        else:
            label = get_t("ticket_label_support", lang, ticket_id=ticket_id)

    header = get_t("ticket_reply_header", lang, sender=sender, label=label)
    quote_block = ""
    if orig_text and orig_text.strip():
        quote_block = get_t("ticket_quote_header", lang, orig_text=orig_text.strip())
    body = get_t("ticket_reply_body_title", lang, reply_text=reply_text.strip())
    return f"{header}{quote_block}{body}"


def format_direct_message(sender: str, text: str, lang: str = "ru") -> str:
    """Format localized direct message from administrator to student."""
    if lang not in ["ru", "lv", "en"]:
        lang = "ru"
    return get_t("direct_msg_header", lang, sender=sender, text=text.strip())

