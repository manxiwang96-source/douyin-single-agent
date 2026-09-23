from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs import run_hydrate, run_morning_brief


def start_scheduler(runtime) -> BackgroundScheduler:
    timezone = runtime.settings.assistant_timezone
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        lambda: run_morning_brief(runtime),
        CronTrigger(hour=8, minute=0, timezone=timezone),
        id="morning_brief",
        replace_existing=True,
    )
    for hour in (10, 12, 14, 16, 18, 20, 22):
        scheduler.add_job(
            lambda slot=f"{hour:02d}": run_hydrate(runtime, slot),
            CronTrigger(hour=hour, minute=0, timezone=timezone),
            id=f"hydrate_{hour:02d}",
            replace_existing=True,
        )
    scheduler.start()
    return scheduler