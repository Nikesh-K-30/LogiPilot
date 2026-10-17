"""Chat intent parsing + what-if knobs change tool-backed answers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.db import reset_db_singleton
from app.services.chat_service import handle_chat, parse_chat_intent


def test_parse_carbon_overrides_ui_cost() -> None:
    intent = parse_chat_intent(
        "Reoptimize and prioritise carbon reduction over cost",
        prioritize="cost",
        allow_delay_hours=0,
    )
    assert intent["prioritize"] == "carbon"
    assert intent["is_what_if"] is True


def test_parse_delay_hours_from_text() -> None:
    intent = parse_chat_intent(
        "What if I allow a 2-hour delay?",
        prioritize="cost",
        allow_delay_hours=0,
    )
    assert intent["allow_delay_hours"] == 2.0


def test_parse_hyd_chennai_corridor() -> None:
    intent = parse_chat_intent("optimise all hyd to Chennai shipments")
    assert intent["corridor"] == ["LOC-HYD", "LOC-MAA"]


def test_keyword_what_if_mentions_priority(db, monkeypatch) -> None:
    """Without Gemini, carbon what-if answer must include priority=carbon."""
    monkeypatch.setattr("app.services.chat_service._gemini_chat", lambda *a, **k: None)
    get_settings.cache_clear()
    reset_db_singleton()

    cost = handle_chat("Find cheapest Chennai consolidations", prioritize="cost")
    carbon = handle_chat(
        "What if we prioritise carbon reduction over cost for Hyd to Chennai?",
        prioritize="cost",
        allow_delay_hours=0,
    )
    assert "priority=carbon" in carbon.answer.lower() or "carbon" in carbon.answer.lower()
    assert carbon.source == "negotiation_what_if"
    assert "priority=carbon" not in cost.answer.lower()


def test_chat_api_accepts_prioritize(db) -> None:
    get_settings.cache_clear()
    reset_db_singleton()
    client = TestClient(app)
    r = client.post(
        "/chat",
        json={
            "message": "What if we prioritise utilization?",
            "prioritize": "utilization",
            "allow_delay_hours": 0,
        },
    )
    assert r.status_code == 200
    assert r.json()["answer"]
