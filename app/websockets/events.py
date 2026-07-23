"""
WebSocket event type definitions.

Provides a typed event envelope that all WebSocket messages must
conform to, making the protocol explicit and easy to extend.

Event shape (JSON)::

    {
        "event":   "chat.message",
        "payload": { ... },
        "room":    "general",         // optional
        "sender":  "conn-uuid"        // optional
    }
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """
    Catalogue of all WebSocket event names.

    Naming convention: ``<domain>.<action>``
    Add new events here as features are built in later phases.
    """

    # System / lifecycle
    CONNECTED = "system.connected"
    DISCONNECTED = "system.disconnected"
    PING = "system.ping"
    PONG = "system.pong"
    ERROR = "system.error"

    # Broadcast (placeholder)
    BROADCAST = "system.broadcast"

    # Procurement — Phase 3
    PO_CREATED = "procurement.po_created"
    PO_SUBMITTED = "procurement.po_submitted"
    PO_APPROVED = "procurement.po_approved"
    PO_REJECTED = "procurement.po_rejected"
    PO_CANCELLED = "procurement.po_cancelled"
    PO_EMAILED = "procurement.po_emailed"
    GRN_CREATED = "procurement.grn_created"
    GRN_APPROVED = "procurement.grn_approved"
    GRN_CANCELLED = "procurement.grn_cancelled"

    # Inventory — Phase 4
    INVENTORY_INCREASED = "inventory.increased"
    INVENTORY_DECREASED = "inventory.decreased"
    INVENTORY_LOW_STOCK = "inventory.low_stock"
    INVENTORY_OUT_OF_STOCK = "inventory.out_of_stock"
    STOCK_ADJUSTMENT_CREATED = "inventory.adjustment_created"
    STOCK_ADJUSTMENT_SUBMITTED = "inventory.adjustment_submitted"
    STOCK_ADJUSTMENT_APPROVED = "inventory.adjustment_approved"
    STOCK_ADJUSTMENT_CANCELLED = "inventory.adjustment_cancelled"

    # Stock Release — Phase 5
    STOCK_RELEASE_CREATED = "stock_release.created"
    STOCK_RELEASE_SUBMITTED = "stock_release.submitted"
    STOCK_RELEASE_APPROVED = "stock_release.approved"
    STOCK_RELEASE_CANCELLED = "stock_release.cancelled"


class WebSocketEvent(BaseModel):
    """Typed envelope for every WebSocket message."""

    event: str = Field(..., description="Event type identifier (e.g. 'system.ping')")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary event-specific data",
    )
    room: str | None = Field(
        default=None, description="Target room / channel name"
    )
    sender: str | None = Field(
        default=None, description="Connection ID of the sender"
    )


def make_event(
    event: str | EventType,
    payload: dict[str, Any] | None = None,
    *,
    room: str | None = None,
    sender: str | None = None,
) -> dict[str, Any]:
    """Convenience factory that returns a serialisable event dict."""
    return WebSocketEvent(
        event=str(event),
        payload=payload or {},
        room=room,
        sender=sender,
    ).model_dump()
