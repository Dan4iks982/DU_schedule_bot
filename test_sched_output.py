import os
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, '/home/daniel/lu_schedule_bot')
import bot
import locales

now = datetime.now(bot.TIMEZONE)
today = now.date()
tomorrow = today + timedelta(days=1)

print("=== PROGRAM D01BR SEMESTER 3 (TODAY) ===")
print("RU:")
print(bot.get_schedule_for_date(today, "D01BR", 3, lang="ru"))
print("\nLV:")
print(bot.get_schedule_for_date(today, "D01BR", 3, lang="lv"))

print("\n=== PROGRAM D01BR SEMESTER 3 (TOMORROW) ===")
print("RU:")
print(bot.get_schedule_for_date(tomorrow, "D01BR", 3, lang="ru"))
print("\nLV:")
print(bot.get_schedule_for_date(tomorrow, "D01BR", 3, lang="lv"))

print("\n=== PROGRAM D01B9 SEMESTER 3 (TODAY) ===")
print(bot.get_schedule_for_date(today, "D01B9", 3, lang="lv"))
print("\n=== PROGRAM D01B9 SEMESTER 3 (TOMORROW) ===")
print(bot.get_schedule_for_date(tomorrow, "D01B9", 3, lang="lv"))
