"""In-Process-Scheduler (ARCHITECTURE.md §1, §5).

Zwei Angebots-Abrufe pro Woche (Mo + Do frueh) - dafuer ist ein Broker oder ein
separater Worker reiner Overhead. APScheduler läuft im FastAPI-Prozess.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Settings
from ..db.session import session_scope
from ..ports import OfferSource

LOG = logging.getLogger(__name__)

# Lief der Server um 5 Uhr nicht (Stromausfall, Neubau), holt er den Abruf bis mittags
# nach - einmal, nicht für jeden verpassten Termin.
MISFIRE_GRACE_SECONDS = 7 * 3600


def fetch_offers_job(source: OfferSource) -> None:
    from ..services.articles import ValidationError
    from ..services.offers import fetch_all

    try:
        with session_scope() as session:
            snapshots = fetch_all(session, source)
    except ValidationError as exc:  # läuft schon (Knopf gedrückt)
        LOG.info("Angebots-Abruf übersprungen: %s", exc)
        return
    LOG.info("Angebots-Abruf fertig: %s Snapshots", len(snapshots))


def start_scheduler(settings: Settings, source: OfferSource) -> BackgroundScheduler:
    monday_hour, thursday_hour = settings.offer_fetch_hours
    scheduler = BackgroundScheduler(timezone="Europe/Berlin")
    for job_id, day, hour in (
        ("offers_monday", "mon", monday_hour),
        ("offers_thursday", "thu", thursday_hour),
    ):
        scheduler.add_job(
            fetch_offers_job,
            CronTrigger(day_of_week=day, hour=hour),
            args=[source],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
            coalesce=True,
        )
    scheduler.start()
    LOG.info("Scheduler läuft: Mo %s:00 und Do %s:00", monday_hour, thursday_hour)
    return scheduler
