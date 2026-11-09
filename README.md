# 🎓 DU Schedule Assistant & Secretary Bot

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/Telegram-Bot%20API-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Bot" />
  <img src="https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/License-All%20Rights%20Reserved-critical?style=for-the-badge" alt="License" />
</p>

An automated, asynchronous Telegram assistant and administrative dashboard designed for real-time schedule tracking, automated notifications, and academic schedule management.

---

## ⚡ Key Features

- **Automated Schedule Scraping:** Real-time ingestion and synchronization of academic schedule data.
- **Multilingual Support:** Fully localized experience with support for Latvian (LV), Russian (RU), and English (EN).
- **Interactive Web Admin Panel:** Built-in web portal for telemetry, database inspection, and broadcast notifications.
- **Production-Ready Deployment:** Packaged with Docker and Docker Compose for high availability and zero-downtime execution.
- **Intelligent Notification Engine:** Automated reminders for upcoming lectures and schedule shifts.

---

## 🛠 Tech Stack

- **Backend:** Python 3.12, Asyncio, `python-telegram-bot`, `aiohttp`
- **Scraper Pipeline:** Node.js, Headless Browser automation
- **Web Interface:** HTML5, CSS3, Modern JavaScript
- **Storage:** Relational database with connection pooling and automated backups
- **Observability:** Datadog monitoring integration

## Deployment and secrets

Copy `.env.example` to `.env` and replace every placeholder with a newly generated value before starting Compose:

```powershell
Copy-Item .env.example .env
docker compose up -d --build
```

`BOT_TOKEN`, administrator passwords, and bot passcodes are never committed to the repository. The admin API requires the `X-Admin-Token` returned by its login endpoint, and CORS is restricted by `ADMIN_CORS_ORIGINS`. Revoke and regenerate any credentials that were previously exposed in repository history.

Schedule responses use a one-hour stale-while-revalidate cache by default (`SCHEDULE_CACHE_TTL_SECONDS=3600`), with concurrent refreshes deduplicated per program/semester. Scraping is isolated behind `scraper_worker.py` and limited by `SCRAPER_CONCURRENCY` (default `1`) to avoid Chromium memory spikes. High-churn bot state is migrated into SQLite's `app_state` table while legacy JSON files remain available for rollback compatibility. Broadcasts use a bounded, rate-limited queue. The `/health` endpoint is available for liveness checks.

SQLite uses WAL mode and a bounded busy timeout; PostgreSQL pooling is not currently part of this deployment.

---

## 🔒 Copyright & Intellectual Property

**Author & Sole Rights Holder:** Daniels Guzenko © 2026.  
All rights reserved.

> **Legal Notice:**  
> This project is the exclusive personal intellectual property of Daniels Guzenko, created independently without the use of university facilities, grants, or academic sponsorship. No university, institution, or third party holds any rights, claims, or license to appropriate, rebrand, or distribute this software without explicit written authorization.
