"""Frigate-shaped sample messages for tests and for driving the pipeline without cameras.

Field names follow Frigate 0.19 TrackedObject.to_dict(). Plates are fictional.
"""

from __future__ import annotations

import time
from typing import Any


def frigate_object(
    frigate_id: str = "1760047800.123456-abc123",
    camera: str = "cam-gate-north",
    label: str = "person",
    score: float = 0.87,
    zones: list[str] | None = None,
    plate: tuple[str, float] | None = None,
    start_time: float | None = None,
    frame_time: float | None = None,
    has_snapshot: bool = True,
    has_clip: bool = False,
    path: list[tuple[float, float, float]] | None = None,
) -> dict[str, Any]:
    """`path` is a list of (x, y, t): normalised bottom-centre points, as in Frigate's path_data."""
    now = time.time()
    return {
        "id": frigate_id,
        "camera": camera,
        "frame_time": frame_time if frame_time is not None else now,
        "snapshot": None,
        "label": label,
        "sub_label": None,
        "top_score": score,
        "false_positive": False,
        "start_time": start_time if start_time is not None else now - 1.0,
        "end_time": None,
        "score": score,
        "box": [320, 180, 420, 460],
        "area": 28000,
        "ratio": 0.36,
        "region": [200, 100, 520, 420],
        "active": True,
        "stationary": False,
        "motionless_count": 0,
        "position_changes": 3,
        "current_zones": zones or [],
        "entered_zones": zones or [],
        "has_clip": has_clip,
        "has_snapshot": has_snapshot,
        "attributes": {},
        "current_attributes": [],
        "pending_loitering": False,
        "max_severity": "detection",
        "current_estimated_speed": 0,
        "average_estimated_speed": 0,
        "velocity_angle": 0,
        "path_data": [[[x, y], t] for x, y, t in (path or [])],
        "recognized_license_plate": list(plate) if plate else None,
    }


def frigate_message(kind: str = "new", **object_fields: Any) -> dict[str, Any]:
    after = frigate_object(**object_fields)
    before = {**after, "false_positive": kind == "new"}
    return {"type": kind, "before": before, "after": after}
