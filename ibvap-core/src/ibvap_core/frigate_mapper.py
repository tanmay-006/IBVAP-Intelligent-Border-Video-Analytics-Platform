"""Map Frigate `frigate/events` MQTT messages to IBVAP events.

Message shape (Frigate 0.19, frigate/track/object_processing.py):
    {"type": "new" | "update" | "end", "before": {...}, "after": {...}}
`new` is sent once, when a tracked object is first confirmed (no longer a
possible false positive). The `after` object is TrackedObject.to_dict().

Phase 2 produces raw `detection` events only; border rules (Phase 3) build
alerts on top of the same tracked objects.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ibvap_core.schemas import EventType, Explanation, IBVAPEvent, ObjectType, Severity

# Fixed namespace so the same Frigate object always maps to the same event id.
# This keeps re-delivered MQTT messages and later edge→centre sync idempotent.
EVENT_ID_NAMESPACE = uuid.UUID("6f6d2a4e-3c1b-4f53-9a0e-1b2c3d4e5f60")

_ANIMAL_LABELS = {
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "deer",
}


@dataclass(frozen=True)
class FrigateMessage:
    kind: str  # new | update | end
    event: IBVAPEvent
    frame_time: float | None


def map_label(label: str) -> ObjectType:
    if label in _ANIMAL_LABELS:
        return ObjectType.ANIMAL
    try:
        return ObjectType(label)
    except ValueError:
        return ObjectType.OTHER


def detection_event_id(site_id: str, camera: str, frigate_id: str) -> uuid.UUID:
    return uuid.uuid5(EVENT_ID_NAMESPACE, f"{site_id}:{camera}:{frigate_id}:detection")


def normalise_plate(raw: str) -> str:
    """Basic cleanup only; Indian-format normalisation lands in Phase 8."""
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def parse_frigate_event(
    message: dict[str, Any], site_id: str, plate_review_threshold: float
) -> FrigateMessage:
    kind = message.get("type")
    if kind not in {"new", "update", "end"}:
        raise ValueError(f"unknown Frigate event type: {kind!r}")
    after = message["after"]

    frigate_id = str(after["id"])
    camera = str(after["camera"])
    label = str(after["label"])
    confidence = after.get("top_score") or after.get("score")
    zones = after.get("current_zones") or after.get("entered_zones") or []
    zone_id = zones[0] if zones else None

    plate_text = plate_confidence = None
    plate = after.get("recognized_license_plate")
    if plate and plate[0]:
        plate_text = normalise_plate(str(plate[0]))
        plate_confidence = float(plate[1]) if len(plate) > 1 and plate[1] is not None else None

    summary = f"Frigate detected {label}"
    if confidence is not None:
        summary += f" (score {confidence:.2f})"
    if zone_id:
        summary += f" in zone {zone_id}"

    event = IBVAPEvent(
        event_id=detection_event_id(site_id, camera, frigate_id),
        site_id=site_id,
        camera_id=camera,
        event_type=EventType.DETECTION,
        severity=Severity.INFORMATIONAL,
        timestamp=datetime.fromtimestamp(float(after["start_time"]), tz=UTC),
        object_type=map_label(label),
        tracking_id=frigate_id,
        detection_confidence=confidence,
        zone_id=zone_id,
        snapshot_ref=f"frigate:/api/events/{frigate_id}/snapshot.jpg" if after.get("has_snapshot") else None,
        clip_ref=f"frigate:/api/events/{frigate_id}/clip.mp4" if after.get("has_clip") else None,
        plate_text=plate_text,
        plate_confidence=plate_confidence,
        plate_needs_review=plate_text is not None
        and (plate_confidence is None or plate_confidence < plate_review_threshold),
        explanation=Explanation(
            summary=summary,
            parameters={"frigate_label": label, "frigate_event_id": frigate_id, "zones": zones},
        ),
    )
    frame_time = after.get("frame_time")
    return FrigateMessage(kind=kind, event=event, frame_time=float(frame_time) if frame_time else None)
