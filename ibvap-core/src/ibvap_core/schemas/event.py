"""IBVAP event record: the shared contract between ibvap-core, the dashboard,
the sync queue and the Trust Layer (CLAUDE.md §4).

Every IBVAP event carries these fields. Components must not invent their own
event shapes; extend this model instead and re-export the JSON Schema.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "1.0.0"


class Severity(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Ordering for alert queues: higher is more severe."""
        return list(Severity).index(self)


class EventType(StrEnum):
    DETECTION = "detection"
    TRIPWIRE_CROSSING = "tripwire_crossing"
    RESTRICTED_ZONE_ENTRY = "restricted_zone_entry"
    NIGHT_MOVEMENT = "night_movement"
    LOITERING = "loitering"
    VEHICLE_STOPPED = "vehicle_stopped"
    APPROACH_RETREAT = "approach_retreat"
    WRONG_DIRECTION = "wrong_direction"
    GROUP_FORMING = "group_forming"
    PLATE_READ = "plate_read"
    FACE_DETECTED = "face_detected"
    CAMERA_HEALTH = "camera_health"


class ObjectType(StrEnum):
    PERSON = "person"
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    BUS = "bus"
    TRUCK = "truck"
    ANIMAL = "animal"
    FACE = "face"
    LICENSE_PLATE = "license_plate"
    OTHER = "other"


class Direction(StrEnum):
    """Direction relative to the border, as configured per tripwire."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    ALONG = "along"
    UNKNOWN = "unknown"


class DecisionSource(StrEnum):
    JEV = "jev"
    RULES_FALLBACK = "rules_fallback"
    RULES_OVERRIDE = "rules_override"  # critical rule kept its severity over Jev


class AlertStatus(StrEnum):
    GENERATED = "generated"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    VERIFIED = "verified"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    CLOSED = "closed"


ALLOWED_TRANSITIONS: dict[AlertStatus, frozenset[AlertStatus]] = {
    AlertStatus.GENERATED: frozenset({AlertStatus.DELIVERED}),
    AlertStatus.DELIVERED: frozenset({AlertStatus.ACKNOWLEDGED}),
    AlertStatus.ACKNOWLEDGED: frozenset({AlertStatus.VERIFIED, AlertStatus.REJECTED}),
    AlertStatus.VERIFIED: frozenset({AlertStatus.ESCALATED, AlertStatus.CLOSED}),
    AlertStatus.REJECTED: frozenset({AlertStatus.CLOSED}),
    AlertStatus.ESCALATED: frozenset({AlertStatus.CLOSED}),
    AlertStatus.CLOSED: frozenset(),
}


def can_transition(current: AlertStatus, new: AlertStatus) -> bool:
    return new in ALLOWED_TRANSITIONS[current]


class SyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class Versions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(None, description="Detector model version that produced the detection")
    rule_id: str | None = Field(None, description="Rule that fired; None for raw detections")
    rule_version: str | None = None


class JevDecision(BaseModel):
    """Triage result from Jev. Built only from text/JSON event descriptions."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    escalate: bool
    false_positive_likelihood: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str | None = None
    latency_ms: float | None = Field(None, ge=0.0)


class Explanation(BaseModel):
    """Why the alert fired, shown to the operator (CLAUDE.md §9)."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class IBVAPEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    event_id: UUID = Field(default_factory=uuid4)
    site_id: str = Field(min_length=1, description="BOP identifier")
    camera_id: str = Field(min_length=1)
    event_type: EventType
    severity: Severity
    timestamp: datetime = Field(description="When the event occurred (UTC); preserved across sync")

    object_type: ObjectType | None = None
    tracking_id: str | None = Field(None, description="Frigate tracked-object id; never a confirmed identity")
    detection_confidence: float | None = Field(None, ge=0.0, le=1.0)
    zone_id: str | None = None
    direction: Direction | None = None

    snapshot_ref: str | None = None
    clip_ref: str | None = None

    plate_text: str | None = None
    plate_confidence: float | None = Field(None, ge=0.0, le=1.0)
    plate_needs_review: bool = False

    versions: Versions = Field(default_factory=Versions)
    explanation: Explanation | None = None

    jev_decision: JevDecision | None = None
    decision_source: DecisionSource = DecisionSource.RULES_FALLBACK

    status: AlertStatus = AlertStatus.GENERATED
    evidence_hash: str | None = Field(None, pattern=r"^[0-9a-f]{64}$", description="SHA-256, lowercase hex")
    ledger_tx_id: str | None = None
    sync_status: SyncStatus = SyncStatus.PENDING

    @field_validator("timestamp")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
