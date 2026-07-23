"""Unit tests for WebSocket event system."""

import pytest

from app.websockets.events import EventType, WebSocketEvent, make_event


def test_make_event_returns_dict():
    event = make_event(EventType.PING)
    assert isinstance(event, dict)
    assert event["event"] == "system.ping"
    assert "payload" in event


def test_make_event_with_payload():
    event = make_event(EventType.CONNECTED, payload={"connection_id": "abc"})
    assert event["payload"]["connection_id"] == "abc"


def test_websocket_event_model():
    evt = WebSocketEvent(event="system.pong", payload={}, room="general")
    assert evt.event == "system.pong"
    assert evt.room == "general"
