"""Bounded scraper worker process.

The worker owns scraper subprocesses so Chromium memory and CPU cannot overlap
with Telegram handlers or multiple background jobs.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

async def run_node(command: dict) -> dict:
    args = [str(command.get("program", "D01B9")), str(command.get("semester", 3))]
    if command.get("teacher_id"):
        args = [str(command["teacher_id"]), str(command.get("teacher_name", ""))]
        script = BASE_DIR / "scraper_teacher.js"
    else:
        script = BASE_DIR / "scraper.js"
    proc = await asyncio.create_subprocess_exec(
        "node", str(script), *args, cwd=str(BASE_DIR),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"success": False, "error": "scraper timeout"}
    lines = stdout.decode("utf-8", errors="ignore").splitlines()
    for line in reversed(lines):
        try:
            result = json.loads(line)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue
    return {"success": False, "error": stderr.decode("utf-8", errors="ignore")[-2000:]}

async def main() -> None:
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            command = json.loads(line)
            result = await run_node(command)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
