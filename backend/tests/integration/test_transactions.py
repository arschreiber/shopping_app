"""Wann eine Antwort rausgeht - und ob die Daten dahinter dann schon stehen."""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from mealplan.services import weeks as weeks_service

ISO = "2026-W45"


def _call(app, method: str, path: str, on_response_start) -> int:
    """Die App direkt über ASGI aufrufen, um den Moment `http.response.start` abzupassen.

    Über den TestClient geht das nicht: der kehrt erst zurück, wenn der ganze Request
    samt Aufräumen durch ist - genau der Unterschied, um den es hier geht, wäre weg.
    """
    status: dict[str, int] = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
            on_response_start()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    asyncio.run(app(scope, receive, send))
    return status["code"]


def test_a_response_goes_out_only_after_the_commit(client, engine):
    """Sonst sieht der nächste Request die Daten der Antwort davor noch nicht.

    So entstand der 500 beim Raster-Speichern einer frisch geöffneten Woche: das GET
    legte die Woche an und antwortete, *bevor* es committet hatte. Das PUT gleich danach
    fand sie nicht, legte sie ein zweites Mal an und scheiterte an UNIQUE(iso_year,
    iso_week). Schlimmer noch: scheitert ein Commit erst nach der Antwort, hat der Client
    schon ein 200 für etwas, das nie gespeichert wurde.
    """
    seen: dict[str, int] = {}

    def count_weeks():
        with engine.connect() as connection:
            seen["weeks"] = connection.execute(
                text("select count(*) from week where iso_year = 2026 and iso_week = 45")
            ).scalar_one()

    status = _call(client.app, "GET", f"/api/weeks/{ISO}", count_weeks)

    assert status == 200
    assert seen["weeks"] == 1, "Antwort war schon unterwegs, die Woche aber noch nicht gespeichert"


def test_two_requests_creating_the_same_week_do_not_collide(engine, monkeypatch):
    """Laptop und Handy öffnen dieselbe neue Woche im selben Moment.

    Beide schauen nach, keiner findet sie, beide legen sie an. Nachgestellt, indem der
    zweite beim ersten Nachschauen noch nichts sieht - obwohl der erste schon committet
    hat. Vorher: IntegrityError und ein 500. Jetzt übernimmt der zweite die Woche des
    ersten.
    """
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as first:
        created = weeks_service.get_or_create_week(first, ISO)
        first.commit()
        created_id = created.id

    real_get_week = weeks_service.get_week
    calls = {"n": 0}

    def blind_on_first_look(session, iso):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_get_week(session, iso)

    monkeypatch.setattr(weeks_service, "get_week", blind_on_first_look)

    with factory() as second:
        week = weeks_service.get_or_create_week(second, ISO)
        second.commit()
        assert week.id == created_id
        assert len(week.slots) == 14

    with engine.connect() as connection:
        rows = connection.execute(text("select count(*) from week")).scalar_one()
        slots = connection.execute(text("select count(*) from slot")).scalar_one()
    assert (rows, slots) == (1, 14), "genau eine Woche mit ihren 14 Slots"
