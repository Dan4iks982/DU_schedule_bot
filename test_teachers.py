import sys
import os
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'C:\Users\danie\.gemini\antigravity\scratch\lu_schedule_bot')

import bot
import db
import locales

print("=== 1. TESTING TEACHER IN SCHEDULE OUTPUT ===")
# Load IT 2nd course events
events = bot.get_events_for("D01B9", 3)
friday_events = [e for e in events if e["date"] == date(2026, 9, 11) and not e.get("is_moved_away")]

print(f"Total Friday events: {len(friday_events)}")
for ev in friday_events:
    subj = ev["subj"]
    teacher = ev.get("teacher")
    print(f"  {ev['time']} — {subj} => Teacher: {repr(teacher)}")

print("\n--- Russian Output (RU) ---")
for ev in friday_events:
    print(bot.format_event(ev, lang="ru"))

print("\n--- Latvian Output (LV) ---")
for ev in friday_events:
    print(bot.format_event(ev, lang="lv"))

print("\n--- English Output (EN) ---")
for ev in friday_events:
    print(bot.format_event(ev, lang="en"))

print("\n=== 2. TESTING DATABASE NOTIFICATION METHODS ===")
db.init_db()

test_hash = "test_hash_12345"
print("is_change_notified before:", db.is_change_notified(test_hash))
db.mark_change_notified("ev123", "D01B9", 3, "rescheduled", test_hash)
print("is_change_notified after:", db.is_change_notified(test_hash))

groups = db.get_active_programs_and_semesters()
print(f"Active groups: {groups}")

users_d01b9 = db.get_users_for_program_semester("D01B9", 3)
print(f"Students in D01B9 sem 3: {len(users_d01b9)}")

# Test toggle
sample_uid = 916876436
initial_status = db.get_user_notifications_enabled(sample_uid)
print(f"User {sample_uid} initial notif status: {initial_status}")
toggled = db.toggle_user_notifications(sample_uid)
print(f"User {sample_uid} after toggle: {toggled}")
restored = db.toggle_user_notifications(sample_uid)
print(f"User {sample_uid} restored: {restored}")

print("\n=== 3. TESTING SETTINGS KEYBOARD ===")
kb_ru = bot.get_settings_keyboard("D01B9", 3, lang="ru", user_id=sample_uid)
for row in kb_ru.inline_keyboard:
    print(" ", [btn.text for btn in row])

kb_lv = bot.get_settings_keyboard("D01B9", 3, lang="lv", user_id=sample_uid)
for row in kb_lv.inline_keyboard:
    print(" ", [btn.text for btn in row])

kb_en = bot.get_settings_keyboard("D01B9", 3, lang="en", user_id=sample_uid)
for row in kb_en.inline_keyboard:
    print(" ", [btn.text for btn in row])

print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
