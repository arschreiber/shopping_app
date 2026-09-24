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

LOG = logging.getLogger(__name__)


def fetch_offers_job(settings: Settings) -> None:
    from ..integrations.offers.korbunio import KorbunioOfferSource
    from ..services.offers import fetch_all

    if not settings.korbunio_url:
        LOG.info("Kein Korbunio konfiguriert - Angebots-Abruf übersprungen")
        return
    source = KorbunioOfferSource(settings.korbunio_url)
    with session_scope() as session:
        snapshots = fetch_all(session, source)
    LOG.info("Angebots-Abruf fertig: %s Snapshots", len(snapshots))


def start_scheduler(settings: Settings) -> BackgroundScheduler:
    monday_hour, thursday_hour = settings.offer_fetch_hours
    scheduler = BackgroundScheduler(timezone="Europe/Berlin")
    scheduler.add_job(
        fetch_offers_job,
        CronTrigger(day_of_week="mon", hour=monday_hour),
        args=[settings],
        id="offers_monday",
        replace_existing=True,
    )
    scheduler.add_job(
        fetch_offers_job,
        CronTrigger(day_of_week="thu", hour=thursday_hour),
        args=[settings],
        id="offers_thursday",
        replace_existing=True,
    )
    scheduler.start()
    LOG.info("Scheduler läuft: Mo %s:00 und Do %s:00", monday_hour, thursday_hour)
    return scheduler
