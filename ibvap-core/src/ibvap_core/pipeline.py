"""Ingestion pipeline: Frigate MQTT message → stored IBVAP event → live push to consoles."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

from ibvap_core.config import Settings
from ibvap_core.frigate_mapper import parse_frigate_event
from ibvap_core.rules import RulesEngine
from ibvap_core.schemas import AlertStatus, IBVAPEvent
from ibvap_core.store import EventStore, InvalidTransition

log = logging.getLogger(__name__)

DELIVERY_ACTOR = "system:ws"


class Broadcaster:
    """Fan-out of live messages to connected operator consoles."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._clients.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: dict[str, Any]) -> int:
        """Send to every client; returns how many received it."""
        text = json.dumps(message)
        delivered = 0
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
                delivered += 1
            except Exception:
                self.remove(ws)
        return delivered


def event_message(kind: str, event: IBVAPEvent) -> dict[str, Any]:
    return {"type": kind, "event": event.model_dump(mode="json")}


class EventPipeline:
    def __init__(
        self,
        settings: Settings,
        store: EventStore,
        broadcaster: Broadcaster,
        rules: RulesEngine | None = None,
    ):
        self.settings = settings
        self.store = store
        self.broadcaster = broadcaster
        self.rules = rules

    async def handle_frigate_payload(self, payload: bytes | str, received_ts: float | None = None) -> None:
        received_ts = received_ts or time.time()
        try:
            message = json.loads(payload)
            parsed = parse_frigate_event(message, self.settings.site_id, self.settings.plate_review_threshold)
        except (ValueError, KeyError, TypeError) as exc:
            log.warning("skipping malformed Frigate event: %s", exc)
            return

        # Rule alerts first: they are the latency-critical path.
        if self.rules is not None:
            try:
                alerts = self.rules.process(message, received_ts)
            except Exception:
                log.exception("rules engine failed on Frigate event %s", parsed.event.tracking_id)
                alerts = []
            for alert in alerts:
                await self.store_and_publish(alert, parsed.frame_time, received_ts)

        result = await asyncio.to_thread(
            self.store.upsert_event, parsed.event, parsed.frame_time, received_ts
        )
        if result.created:
            await self.publish_new(result.event)
        elif result.changed:
            await self.broadcaster.broadcast(event_message("event.updated", result.event))
        if result.changed:
            for alert in await asyncio.to_thread(self.store.propagate_media, result.event):
                await self.broadcaster.broadcast(event_message("event.updated", alert))

    async def run_rule_timer(self, interval_s: float = 1.0) -> None:
        """Re-check dwell-time rules; stationary objects send few MQTT updates."""
        while True:
            await asyncio.sleep(interval_s)
            if self.rules is None:
                continue
            try:
                alerts = self.rules.tick(time.time())
            except Exception:
                log.exception("rules engine tick failed")
                continue
            for alert in alerts:
                await self.store_and_publish(alert, None, None)

    async def store_and_publish(
        self, event: IBVAPEvent, frame_ts: float | None, received_ts: float | None
    ) -> None:
        result = await asyncio.to_thread(self.store.upsert_event, event, frame_ts, received_ts)
        if result.created:
            log.info(
                "alert %s %s on %s: %s",
                event.severity.value,
                event.event_type.value,
                event.camera_id,
                event.explanation.summary if event.explanation else "",
            )
            await self.publish_new(result.event)

    async def publish_new(self, event: IBVAPEvent) -> None:
        sent = await self.broadcaster.broadcast(event_message("event.created", event))
        if sent:
            await asyncio.to_thread(self.store.mark_broadcast, str(event.event_id), time.time())
            await self.mark_delivered(event)

    async def mark_delivered(self, event: IBVAPEvent) -> None:
        if event.status is not AlertStatus.GENERATED:
            return
        try:
            updated = await asyncio.to_thread(
                self.store.transition, str(event.event_id), AlertStatus.DELIVERED, DELIVERY_ACTOR
            )
        except InvalidTransition:
            return  # already delivered by a concurrent push
        await self.broadcaster.broadcast(event_message("event.updated", updated))
