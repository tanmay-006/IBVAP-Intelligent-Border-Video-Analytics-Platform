"""REST + WebSocket API for operator consoles and C2 integration.

Run: uv run uvicorn ibvap_core.api:create_app --factory
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import statistics
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ibvap_core.config import Settings, get_settings
from ibvap_core.db import make_engine, make_sessionmaker
from ibvap_core.mqtt_consumer import MqttConsumer
from ibvap_core.pipeline import Broadcaster, EventPipeline, event_message
from ibvap_core.rules import RulesEngine, load_rules
from ibvap_core.schemas import AlertStatus, EventType, IBVAPEvent, Severity
from ibvap_core.site import load_site
from ibvap_core.store import EventFilter, EventNotFound, EventStore, InvalidTransition

log = logging.getLogger(__name__)

ACTIONS: dict[str, AlertStatus] = {
    "ack": AlertStatus.ACKNOWLEDGED,
    "verify": AlertStatus.VERIFIED,
    "reject": AlertStatus.REJECTED,
    "escalate": AlertStatus.ESCALATED,
    "close": AlertStatus.CLOSED,
}

WS_SNAPSHOT_LIMIT = 200


class TransitionRequest(BaseModel):
    # Free text until role-based login lands (Phase 9).
    actor: str = Field(min_length=1, max_length=128)
    note: str | None = Field(None, max_length=2000)


def _pipeline(request: Request) -> EventPipeline:
    return request.app.state.pipeline


def _store(request: Request) -> EventStore:
    return request.app.state.pipeline.store


Store = Annotated[EventStore, Depends(_store)]
Pipeline = Annotated[EventPipeline, Depends(_pipeline)]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(pct) - 1]


def _stage_summary(values: list[float]) -> dict[str, float | None]:
    ms = [v * 1000 for v in values]
    return {
        "p50_ms": _percentile(ms, 50),
        "p95_ms": _percentile(ms, 95),
        "max_ms": max(ms) if ms else None,
    }


def _load_rules_engine(settings: Settings) -> RulesEngine | None:
    path = Path(settings.rules_path)
    if not path.exists():
        log.warning("no rules file at %s; only raw detections will be recorded", path)
        return None
    config = load_rules(path)
    log.info("loaded %d camera rule sets from %s (version %s)", len(config.cameras), path, config.version)
    return RulesEngine(config, settings.site_id)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        store = EventStore(make_sessionmaker(engine))
        pipeline = EventPipeline(settings, store, Broadcaster(), _load_rules_engine(settings))
        app.state.pipeline = pipeline
        app.state.mqtt = None
        app.state.http_transport = None  # tests inject a mock transport for Frigate
        tasks = [asyncio.create_task(pipeline.run_rule_timer())]
        if settings.mqtt_enabled:
            app.state.mqtt = MqttConsumer(settings, pipeline)
            tasks.append(asyncio.create_task(app.state.mqtt.run()))
        yield
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        engine.dispose()

    app = FastAPI(title="IBVAP Core", version="0.1.0", lifespan=lifespan)
    site = load_site(settings.site_path)

    def live_url(stream: str) -> str:
        # WebRTC first for the lowest delay, MSE as fallback.
        return f"{settings.live_view_url.rstrip('/')}/stream.html?src={quote(stream)}&mode=webrtc,mse"

    dashboard = Path(settings.dashboard_dir)
    has_dashboard = (dashboard / "index.html").exists()
    if has_dashboard:
        app.mount("/ui", StaticFiles(directory=dashboard, html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse("/ui/" if has_dashboard else "/docs")

    @app.get("/health")
    async def health(request: Request) -> dict:
        mqtt = request.app.state.mqtt
        rules = request.app.state.pipeline.rules
        return {
            "status": "ok",
            "rules_version": rules.config.version if rules else None,
            "site_id": settings.site_id,
            "site_name": site.site.name,
            "mqtt_enabled": settings.mqtt_enabled,
            "mqtt_connected": bool(mqtt and mqtt.connected),
            "ws_clients": request.app.state.pipeline.broadcaster.client_count,
        }

    @app.get("/events", response_model=list[IBVAPEvent])
    async def list_events(
        store: Store,
        camera_id: str | None = None,
        event_type: EventType | None = None,
        severity: Severity | None = None,
        status: AlertStatus | None = None,
        plate: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        order: Literal["time", "severity"] = "time",
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ) -> list[IBVAPEvent]:
        f = EventFilter(
            camera_id=camera_id,
            event_type=event_type,
            severity=severity,
            status=status,
            plate_text=plate,
            since=since,
            until=until,
            open_only=open_only,
            order=order,
            limit=limit,
            offset=offset,
        )
        return await asyncio.to_thread(store.list, f)

    @app.get("/events/{event_id}", response_model=IBVAPEvent)
    async def get_event(event_id: UUID, store: Store) -> IBVAPEvent:
        try:
            return await asyncio.to_thread(store.get, str(event_id))
        except EventNotFound:
            raise HTTPException(404, "event not found") from None

    @app.get("/events/{event_id}/audit")
    async def get_audit(event_id: UUID, store: Store) -> list[dict]:
        try:
            return await asyncio.to_thread(store.audit, str(event_id))
        except EventNotFound:
            raise HTTPException(404, "event not found") from None

    @app.post("/alerts/{event_id}/{action}", response_model=IBVAPEvent)
    async def transition_alert(
        event_id: UUID,
        action: Literal["ack", "verify", "reject", "escalate", "close"],
        body: TransitionRequest,
        pipeline: Pipeline,
    ) -> IBVAPEvent:
        try:
            event = await asyncio.to_thread(
                pipeline.store.transition, str(event_id), ACTIONS[action], body.actor, body.note
            )
        except EventNotFound:
            raise HTTPException(404, "event not found") from None
        except InvalidTransition as exc:
            raise HTTPException(409, str(exc)) from None
        await pipeline.broadcaster.broadcast(event_message("event.updated", event))
        return event

    @app.get("/cameras")
    async def list_cameras(store: Store) -> list[dict]:
        """Configured cameras (with map position) merged with every camera that has sent events."""
        seen = {c["camera_id"]: c for c in await asyncio.to_thread(store.cameras)}
        cameras = []
        for camera_id in sorted(set(site.cameras) | set(seen)):
            info = site.cameras.get(camera_id)
            cameras.append(
                {
                    "camera_id": camera_id,
                    "name": info.name if info else camera_id,
                    "lat": info.lat if info else None,
                    "lon": info.lon if info else None,
                    "live_url": live_url(info.live_stream) if info and info.live_stream else None,
                    "last_event_at": seen.get(camera_id, {}).get("last_event_at"),
                }
            )
        return cameras

    @app.get("/media/{event_id}/{kind}")
    async def media(
        event_id: UUID, kind: Literal["snapshot", "clip"], store: Store, request: Request
    ) -> StreamingResponse:
        """Stream an event's snapshot or clip from Frigate, so consoles never talk to Frigate directly."""
        try:
            event = await asyncio.to_thread(store.get, str(event_id))
        except EventNotFound:
            raise HTTPException(404, "event not found") from None
        ref = event.snapshot_ref if kind == "snapshot" else event.clip_ref
        if not ref or not ref.startswith("frigate:"):
            raise HTTPException(404, f"no {kind} recorded for this event")
        url = settings.frigate_api_url.rstrip("/") + ref.removeprefix("frigate:")
        client = httpx.AsyncClient(
            transport=request.app.state.http_transport, timeout=httpx.Timeout(10.0, read=60.0)
        )
        try:
            upstream = await client.send(client.build_request("GET", url), stream=True)
        except httpx.HTTPError:
            await client.aclose()
            raise HTTPException(502, "Frigate is not reachable, so this media cannot be shown") from None
        if upstream.status_code != 200:
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(404, f"Frigate has no {kind} for this event")

        async def body() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        media_type = upstream.headers.get("content-type", "image/jpeg" if kind == "snapshot" else "video/mp4")
        return StreamingResponse(body(), media_type=media_type)

    @app.get("/metrics/latency")
    async def latency(store: Store, limit: int = Query(500, ge=1, le=5000)) -> dict:
        """Frame-to-console latency over recent delivered events (target < 2 s at the edge)."""
        samples = await asyncio.to_thread(store.latency_samples, limit)
        return {
            "count": len(samples),
            "frame_to_console": _stage_summary([b - f for f, _, _, b in samples]),
            "frame_to_received": _stage_summary([r - f for f, r, _, _ in samples]),
            "received_to_stored": _stage_summary([s - r for _, r, s, _ in samples]),
            "stored_to_console": _stage_summary([b - s for _, _, s, b in samples]),
        }

    @app.websocket("/ws/alerts")
    async def alerts_ws(ws: WebSocket) -> None:
        pipeline: EventPipeline = ws.app.state.pipeline
        await ws.accept()
        open_events = await asyncio.to_thread(
            pipeline.store.list, EventFilter(open_only=True, order="severity", limit=WS_SNAPSHOT_LIMIT)
        )
        await ws.send_json({"type": "snapshot", "events": [e.model_dump(mode="json") for e in open_events]})
        pipeline.broadcaster.add(ws)
        try:
            for event in open_events:
                await pipeline.mark_delivered(event)
            while True:
                await ws.receive_text()  # consoles don't send yet; this detects disconnect
        except WebSocketDisconnect:
            pass
        finally:
            pipeline.broadcaster.remove(ws)

    return app
