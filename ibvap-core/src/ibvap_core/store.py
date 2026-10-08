"""Event store: persistence, Frigate update merging, alert lifecycle and audit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ibvap_core.db import AuditRow, CameraRow, EventRow
from ibvap_core.schemas import AlertStatus, EventType, IBVAPEvent, Severity, can_transition

CLOSED_STATUSES = {AlertStatus.CLOSED.value, AlertStatus.REJECTED.value}


class EventNotFound(LookupError):
    pass


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class UpsertResult:
    event: IBVAPEvent
    created: bool
    changed: bool


@dataclass(frozen=True)
class EventFilter:
    camera_id: str | None = None
    event_type: EventType | None = None
    severity: Severity | None = None
    status: AlertStatus | None = None
    plate_text: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    open_only: bool = False
    order: str = "time"  # time | severity
    limit: int = 100
    offset: int = 0


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _apply(row: EventRow, event: IBVAPEvent) -> None:
    row.site_id = event.site_id
    row.camera_id = event.camera_id
    row.event_type = event.event_type.value
    row.severity = event.severity.value
    row.severity_rank = event.severity.rank
    row.timestamp = _naive_utc(event.timestamp)
    row.object_type = event.object_type.value if event.object_type else None
    row.tracking_id = event.tracking_id
    row.plate_text = event.plate_text
    row.status = event.status.value
    row.sync_status = event.sync_status.value
    row.payload = event.model_dump(mode="json")


def _merge_update(stored: IBVAPEvent, incoming: IBVAPEvent) -> IBVAPEvent:
    """Fold a later Frigate update into the stored event without touching lifecycle state."""
    changes: dict[str, Any] = {}
    if incoming.detection_confidence is not None and (
        stored.detection_confidence is None or incoming.detection_confidence > stored.detection_confidence
    ):
        changes["detection_confidence"] = incoming.detection_confidence
    for field in ("zone_id", "snapshot_ref", "clip_ref"):
        value = getattr(incoming, field)
        if value is not None and value != getattr(stored, field):
            changes[field] = value
    if incoming.plate_text and incoming.plate_text != stored.plate_text:
        changes.update(
            plate_text=incoming.plate_text,
            plate_confidence=incoming.plate_confidence,
            plate_needs_review=incoming.plate_needs_review,
        )
    if not changes:
        return stored
    if incoming.explanation is not None:
        changes["explanation"] = incoming.explanation
    return stored.model_copy(update=changes)


class EventStore:
    def __init__(self, sessions: sessionmaker[Session]):
        self._sessions = sessions

    def upsert_event(
        self, event: IBVAPEvent, frame_ts: float | None, received_ts: float | None
    ) -> UpsertResult:
        with self._sessions.begin() as session:
            self._touch_camera(session, event)
            row = session.get(EventRow, str(event.event_id))
            if row is None:
                row = EventRow(
                    event_id=str(event.event_id),
                    frame_ts=frame_ts,
                    received_ts=received_ts,
                    stored_ts=datetime.now(UTC).timestamp(),
                )
                _apply(row, event)
                session.add(row)
                return UpsertResult(event=event, created=True, changed=True)

            stored = IBVAPEvent.model_validate(row.payload)
            merged = _merge_update(stored, event)
            if merged is stored:
                return UpsertResult(event=stored, created=False, changed=False)
            _apply(row, merged)
            return UpsertResult(event=merged, created=False, changed=True)

    def propagate_media(self, source: IBVAPEvent) -> list[IBVAPEvent]:
        """Copy snapshot/clip refs from a detection onto rule alerts raised for the same tracked object.

        Frigate only confirms a clip once the object ends, usually after the alert fired.
        """
        if not source.tracking_id or not (source.snapshot_ref or source.clip_ref):
            return []
        stmt = select(EventRow).where(
            EventRow.camera_id == source.camera_id,
            EventRow.tracking_id == source.tracking_id,
            EventRow.event_type != EventType.DETECTION.value,
        )
        updated: list[IBVAPEvent] = []
        with self._sessions.begin() as session:
            for row in session.scalars(stmt):
                alert = IBVAPEvent.model_validate(row.payload)
                changes = {
                    f: getattr(source, f)
                    for f in ("snapshot_ref", "clip_ref")
                    if getattr(source, f) and getattr(alert, f) is None
                }
                if changes:
                    alert = alert.model_copy(update=changes)
                    _apply(row, alert)
                    updated.append(alert)
        return updated

    def mark_broadcast(self, event_id: str, ts: float) -> None:
        with self._sessions.begin() as session:
            row = session.get(EventRow, event_id)
            if row is not None and row.broadcast_ts is None:
                row.broadcast_ts = ts

    def get(self, event_id: str) -> IBVAPEvent:
        with self._sessions() as session:
            row = session.get(EventRow, event_id)
            if row is None:
                raise EventNotFound(event_id)
            return IBVAPEvent.model_validate(row.payload)

    def list(self, f: EventFilter) -> list[IBVAPEvent]:
        stmt = select(EventRow.payload)
        if f.camera_id:
            stmt = stmt.where(EventRow.camera_id == f.camera_id)
        if f.event_type:
            stmt = stmt.where(EventRow.event_type == f.event_type.value)
        if f.severity:
            stmt = stmt.where(EventRow.severity == f.severity.value)
        if f.status:
            stmt = stmt.where(EventRow.status == f.status.value)
        if f.plate_text:
            stmt = stmt.where(EventRow.plate_text.contains(f.plate_text.upper()))
        if f.since:
            stmt = stmt.where(EventRow.timestamp >= _naive_utc(f.since))
        if f.until:
            stmt = stmt.where(EventRow.timestamp < _naive_utc(f.until))
        if f.open_only:
            stmt = stmt.where(EventRow.status.not_in(CLOSED_STATUSES))
        if f.order == "severity":
            stmt = stmt.order_by(EventRow.severity_rank.desc(), EventRow.timestamp.desc())
        else:
            stmt = stmt.order_by(EventRow.timestamp.desc())
        stmt = stmt.limit(f.limit).offset(f.offset)
        with self._sessions() as session:
            return [IBVAPEvent.model_validate(p) for p in session.scalars(stmt)]

    def transition(self, event_id: str, to: AlertStatus, actor: str, note: str | None = None) -> IBVAPEvent:
        """Apply a lifecycle transition and audit it.

        Acknowledging an alert that was never pushed to a console (e.g. opened via
        search) records the implicit Delivered step first, so the trail stays complete.
        """
        with self._sessions.begin() as session:
            row = session.get(EventRow, event_id, with_for_update=True)
            if row is None:
                raise EventNotFound(event_id)
            event = IBVAPEvent.model_validate(row.payload)
            steps = [to]
            if event.status is AlertStatus.GENERATED and to is AlertStatus.ACKNOWLEDGED:
                steps = [AlertStatus.DELIVERED, to]
            for step in steps:
                if not can_transition(event.status, step):
                    raise InvalidTransition(f"{event.status.value} -> {step.value} is not allowed")
                session.add(
                    AuditRow(
                        event_id=event_id,
                        from_status=event.status.value,
                        to_status=step.value,
                        actor=actor if step is to else "system",
                        note=note if step is to else "implicit delivery on acknowledge",
                        at=_now(),
                    )
                )
                event = event.model_copy(update={"status": step})
            _apply(row, event)
            return event

    def audit(self, event_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            if session.get(EventRow, event_id) is None:
                raise EventNotFound(event_id)
            rows = session.scalars(
                select(AuditRow).where(AuditRow.event_id == event_id).order_by(AuditRow.id)
            )
            return [
                {
                    "from_status": r.from_status,
                    "to_status": r.to_status,
                    "actor": r.actor,
                    "note": r.note,
                    "at": r.at.replace(tzinfo=UTC).isoformat(),
                }
                for r in rows
            ]

    def cameras(self) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = session.scalars(select(CameraRow).order_by(CameraRow.camera_id))
            return [
                {
                    "camera_id": r.camera_id,
                    "site_id": r.site_id,
                    "last_event_at": r.last_event_at.replace(tzinfo=UTC).isoformat()
                    if r.last_event_at
                    else None,
                }
                for r in rows
            ]

    def latency_samples(self, limit: int = 500) -> list[tuple[float, float, float, float]]:
        """(frame, received, stored, broadcast) timestamps of the most recent delivered events."""
        stmt = (
            select(EventRow.frame_ts, EventRow.received_ts, EventRow.stored_ts, EventRow.broadcast_ts)
            .where(EventRow.frame_ts.is_not(None), EventRow.broadcast_ts.is_not(None))
            .order_by(EventRow.broadcast_ts.desc())
            .limit(limit)
        )
        with self._sessions() as session:
            return [tuple(r) for r in session.execute(stmt)]

    @staticmethod
    def _touch_camera(session: Session, event: IBVAPEvent) -> None:
        camera = session.get(CameraRow, event.camera_id)
        if camera is None:
            camera = CameraRow(camera_id=event.camera_id, site_id=event.site_id)
            session.add(camera)
        camera.last_event_at = _now()
