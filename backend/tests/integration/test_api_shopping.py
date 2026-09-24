"""Einkaufsliste und Push (general_plan.md §5 Phase 1, §8 Nr. 8)."""

from __future__ import annotations

ISO = "2026-W37"


def test_list_aggregates_the_planned_week(client, seeded):
    client.post(f"/api/weeks/{ISO}/propose", json={})
    data = client.get(f"/api/weeks/{ISO}/shopping-list").json()

    assert data["status"] == "DRAFT"
    assert data["items"]
    names = {item["article_name"] for item in data["items"]}
    assert "Salz" not in names, "Grundvorrat gehört nicht auf die Liste"
    rice = next(i for i in data["items"] if i["article_name"] == "Basmatireis")
    assert rice["unit"] == "G"
    assert len(rice["from_dish_ids"]) >= 1, "warum steht das drauf?"
    assert rice["spec_text"].endswith(("g", "kg"))


def test_have_already_survives_a_rebuild(client, seeded):
    client.post(f"/api/weeks/{ISO}/propose", json={})
    data = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    article_id = data["items"][0]["article_id"]

    client.patch(
        f"/api/weeks/{ISO}/shopping-list/have-already",
        json={"article_id": article_id, "have_already": True},
    )
    rebuilt = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    checked = next(i for i in rebuilt["items"] if i["article_id"] == article_id)
    assert checked["have_already"] is True
    assert rebuilt["open_count"] == len(rebuilt["items"]) - 1


def test_manual_items_are_kept_when_the_plan_changes(client, seeded):
    client.post(f"/api/weeks/{ISO}/propose", json={})
    coffee = next(a for a in client.get("/api/articles").json() if a["canonical_name"] == "Kaffee")
    client.post(
        f"/api/weeks/{ISO}/shopping-list/items",
        json={"article_id": coffee["id"], "source": "WATCHLIST"},
    )
    rebuilt = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    entry = next(i for i in rebuilt["items"] if i["article_id"] == coffee["id"])
    assert entry["source"] == "WATCHLIST"


def test_items_can_be_removed(client, seeded):
    client.post(f"/api/weeks/{ISO}/propose", json={})
    data = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    article_id = data["items"][0]["article_id"]
    after = client.delete(f"/api/weeks/{ISO}/shopping-list/items/{article_id}").json()
    assert article_id not in {i["article_id"] for i in after["items"]}


def test_text_export_is_always_available(client, seeded):
    """Der Fallback, wenn Bring! bricht (ARCHITECTURE.md §5)."""
    client.post(f"/api/weeks/{ISO}/propose", json={})
    data = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    assert data["text_export"].startswith("Einkaufsliste")
    assert "Basmatireis" in data["text_export"]


def test_push_marks_the_list_as_sent_and_logs_a_run(client, seeded):
    client.post(f"/api/weeks/{ISO}/propose", json={})
    result = client.post(f"/api/weeks/{ISO}/shopping-list/push").json()

    assert result["ok"] is True
    assert result["adapter"] == "text"
    assert result["items_sent"] > 0
    assert result["text_fallback"]

    data = client.get(f"/api/weeks/{ISO}/shopping-list", params={"rebuild": False}).json()
    assert data["status"] == "SENT"

    runs = client.get("/api/sync-runs").json()
    assert runs[0]["kind"] == "BRING_PUSH"
    assert runs[0]["status"] == "OK"
    assert runs[0]["summary"]["adapter"] == "text"


def test_checked_items_are_not_pushed(client, seeded, db):
    from mealplan.services.bring_sync import build_desired

    client.post(f"/api/weeks/{ISO}/propose", json={})
    data = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    article_id = data["items"][0]["article_id"]
    client.patch(
        f"/api/weeks/{ISO}/shopping-list/have-already",
        json={"article_id": article_id, "have_already": True},
    )
    assert article_id not in {item.article_id for item in build_desired(db, ISO)}


def test_push_uses_the_bring_catalog_name(client, seeded, db):
    """Icon und Kategorie gibt es nur bei exaktem Katalognamen (Plan §8 Nr. 9)."""
    from mealplan.services.bring_sync import build_desired

    client.post(f"/api/weeks/{ISO}/propose", json={})
    client.get(f"/api/weeks/{ISO}/shopping-list")
    names = {item.name for item in build_desired(db, ISO)}
    assert "Reis" in names  # Artikel "Basmatireis" -> Katalogname "Reis"


def test_health_shows_the_integration_state(client, seeded):
    health = client.get("/api/health").json()
    assert health["db"] == "ok"
    assert health["dishes"] == 14
    assert health["sync_adapter"] == "text"
    assert health["last_bring_push"] is None

    client.post(f"/api/weeks/{ISO}/propose", json={})
    client.post(f"/api/weeks/{ISO}/shopping-list/push")
    assert client.get("/api/health").json()["last_bring_push"] is not None


def test_settings_roundtrip_changes_the_planner(client, seeded):
    """Gewichte kommen aus der DB - Spike 4 ohne Deploy (ARCHITECTURE.md §4)."""
    defaults = client.get("/api/settings").json()
    assert defaults["planner_weights"]["rotation_cap"] == 12.0

    updated = client.put(
        "/api/settings", json={"planner_weights": {"rotation_cap": 30.0}}
    ).json()
    assert updated["planner_weights"]["rotation_cap"] == 30.0

    week = client.post(f"/api/weeks/{ISO}/propose", json={}).json()
    contributions = [
        c
        for slot in week["slots"]
        if slot["assignment"] and slot["assignment"]["score"]
        for c in slot["assignment"]["score"]["contributions"]
    ]
    rotation = [c["delta"] for c in contributions if c["rule"] == "rotation"]
    assert not rotation or max(rotation) <= 30.0


def test_sent_status_survives_a_reload(client, seeded):
    """Sonst wäre „an Bring! gesendet“ nie zu sehen - der Rebuild setzt sonst DRAFT."""
    client.post(f"/api/weeks/{ISO}/propose", json={})
    client.post(f"/api/weeks/{ISO}/shopping-list/push")

    reloaded = client.get(f"/api/weeks/{ISO}/shopping-list").json()
    assert reloaded["status"] == "SENT"


def test_a_changed_plan_puts_the_list_back_into_review(client, seeded):
    client.post(f"/api/weeks/{ISO}/propose", json={})
    client.post(f"/api/weeks/{ISO}/shopping-list/push")
    assert client.get(f"/api/weeks/{ISO}/shopping-list").json()["status"] == "SENT"

    # Ein Slot geleert -> andere Zutaten -> die Liste muss wieder geprüft werden.
    week = client.get(f"/api/weeks/{ISO}").json()
    target = next(s for s in week["slots"] if s["assignment"])
    client.delete(f"/api/weeks/{ISO}/slots/{target['day']}/{target['meal']}/assignment")

    assert client.get(f"/api/weeks/{ISO}/shopping-list").json()["status"] == "DRAFT"
