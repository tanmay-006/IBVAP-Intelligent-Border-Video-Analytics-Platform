"""Border rules engine (Zone B): turns Frigate tracked-object updates into explainable alerts.

Inputs are Frigate `frigate/events` messages. Positions come from `path_data`:
Frigate appends the object's bottom-centre (normalised 0..1) each time it moves
~5% of the frame, so consecutive points form the segments we test against
tripwires and zones, even though MQTT updates themselves are sparse.

Dwell-type rules (loitering, vehicle stopped) are also re-checked by `tick()`,
because a stationary object produces almost no MQTT updates.

The engine is deterministic and never depends on Jev or the network.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ibvap_core.frigate_mapper import map_label
from ibvap_core.rules.config import (
    ApproachRetreatRule,
    CameraRules,
    GroupFormingRule,
    LoiteringRule,
    NightMovementRule,
    RuleBase,
    RulesConfig,
    TripwireConfig,
    TripwireRule,
    VehicleStoppedRule,
    WrongDirectionRule,
    ZoneEntryRule,
)
from ibvap_core.rules.geometry import (
    Point,
    angle_between_deg,
    distance_to_segment,
    point_in_polygon,
    segments_intersect,
    side,
)
from ibvap_core.schemas import Direction, EventType, Explanation, IBVAPEvent, ObjectType, Versions

log = logging.getLogger(__name__)

ALERT_ID_NAMESPACE = uuid.UUID("a3c1f0d2-7b4e-4e8a-9c55-2d1e0f3b6a71")
MAX_POINTS = 300

EVENT_TYPES: dict[str, EventType] = {
    "tripwire": EventType.TRIPWIRE_CROSSING,
    "zone_entry": EventType.RESTRICTED_ZONE_ENTRY,
    "loitering": EventType.LOITERING,
    "night_movement": EventType.NIGHT_MOVEMENT,
    "vehicle_stopped": EventType.VEHICLE_STOPPED,
    "approach_retreat": EventType.APPROACH_RETREAT,
    "wrong_direction": EventType.WRONG_DIRECTION,
    "group_forming": EventType.GROUP_FORMING,
}


@dataclass
class Track:
    camera: str
    track_id: str
    label: str = "unknown"
    object_type: ObjectType = ObjectType.OTHER
    confidence: float = 0.0
    has_snapshot: bool = False
    has_clip: bool = False
    points: deque[tuple[float, Point]] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    last_seen: float = 0.0
    still_since: float | None = None
    frigate_zones: set[str] = field(default_factory=set)
    zones: dict[str, float] = field(default_factory=dict)  # zone -> entered at
    entries: dict[str, deque[float]] = field(default_factory=dict)
    fired: set[tuple[Any, ...]] = field(default_factory=set)  # once-per-visit keys
    wire_side: dict[str, tuple[int, Point]] = field(default_factory=dict)  # tripwire -> confirmed side, point
    wire_touched: set[str] = field(default_factory=set)  # tripwires the path crossed since the last confirm

    @property
    def last_t(self) -> float:
        return self.points[-1][0] if self.points else float("-inf")


def _utc(t: float) -> datetime:
    return datetime.fromtimestamp(t, tz=UTC)


class RulesEngine:
    def __init__(self, config: RulesConfig, site_id: str):
        self.config = config
        self.site_id = site_id
        self.tracks: dict[tuple[str, str], Track] = {}
        # (camera, cooldown group, track id or "*") -> (time, severity rank) of the last alert
        self._last_fire: dict[tuple[str, str, str], tuple[float, int]] = {}

    # ------------------------------------------------------------------ inputs

    def process(self, message: dict[str, Any], seen_at: float) -> list[IBVAPEvent]:
        after = message["after"]
        camera = str(after["camera"])
        cam = self.config.cameras.get(camera)
        if cam is None or not cam.rules:
            return []

        key = (camera, str(after["id"]))
        track = self.tracks.get(key) or Track(camera=camera, track_id=key[1])
        self.tracks[key] = track
        track.label = str(after["label"])
        track.object_type = map_label(track.label)
        track.confidence = float(after.get("top_score") or after.get("score") or 0.0)
        track.has_snapshot = bool(after.get("has_snapshot"))
        track.has_clip = bool(after.get("has_clip"))
        track.frigate_zones = set(after.get("current_zones") or [])
        track.last_seen = seen_at

        alerts: list[IBVAPEvent] = []
        new_points = sorted(
            (float(t), (float(p[0]), float(p[1])))
            for p, t in (after.get("path_data") or [])
            if float(t) > track.last_t
        )
        for t, p in new_points:
            alerts += self._advance(cam, track, t, p)

        now = float(after.get("frame_time") or (track.last_t if track.points else seen_at))
        alerts += self._sync_frigate_zones(cam, track, now)
        alerts += self._evaluate_track(cam, track, now)
        alerts += self._evaluate_camera(camera, cam, now)

        if message.get("type") == "end":
            self._drop(key)
        return alerts

    def tick(self, now: float) -> list[IBVAPEvent]:
        """Re-check time-based rules and expire tracks Frigate stopped reporting."""
        alerts: list[IBVAPEvent] = []
        for key, track in list(self.tracks.items()):
            if now - track.last_seen > self.config.track_ttl_s:
                self._drop(key)
                continue
            alerts += self._evaluate_track(self.config.cameras[track.camera], track, now)
        return alerts

    def _drop(self, key: tuple[str, str]) -> None:
        del self.tracks[key]
        for cooldown_key in [k for k in self._last_fire if k[0] == key[0] and k[2] == key[1]]:
            del self._last_fire[cooldown_key]

    # --------------------------------------------------------------- movement

    def _advance(self, cam: CameraRules, track: Track, t: float, p: Point) -> list[IBVAPEvent]:
        alerts: list[IBVAPEvent] = []
        prev = track.points[-1][1] if track.points else None
        track.points.append((t, p))
        track.still_since = t  # a new path point means the object moved

        for name, wire in cam.tripwires.items():
            crossing = self._wire_crossing(wire, name, track, prev, p)
            if crossing is None:
                continue
            direction, start = crossing
            for rule in cam.rules:
                if isinstance(rule, TripwireRule) and rule.tripwire == name:
                    alert = self._tripwire_alert(rule, track, direction, start, p, t)
                    if alert:
                        alerts.append(alert)

        for name, zone in cam.zones.items():
            if zone.polygon is not None:
                alerts += self._set_zone(cam, track, name, point_in_polygon(p, zone.polygon), t)
        return alerts

    def _sync_frigate_zones(self, cam: CameraRules, track: Track, t: float) -> list[IBVAPEvent]:
        alerts: list[IBVAPEvent] = []
        for name, zone in cam.zones.items():
            if zone.frigate_zone is not None:
                alerts += self._set_zone(cam, track, name, zone.frigate_zone in track.frigate_zones, t)
        return alerts

    def _set_zone(
        self, cam: CameraRules, track: Track, zone: str, inside: bool, t: float
    ) -> list[IBVAPEvent]:
        was_inside = zone in track.zones
        if inside == was_inside:
            return []
        if not inside:
            del track.zones[zone]
            return []
        track.zones[zone] = t
        track.entries.setdefault(zone, deque(maxlen=50)).append(t)
        alerts = []
        for rule in cam.rules:
            if isinstance(rule, ZoneEntryRule) and rule.zone == zone and self._passes(rule, track, t):
                alert = self._fire(
                    rule,
                    track,
                    t,
                    zone_id=zone,
                    summary=f"{track.label} entered restricted zone {zone}",
                    params={},
                )
                if alert:
                    alerts.append(alert)
        return alerts

    @staticmethod
    def _wire_crossing(
        wire: TripwireConfig, name: str, track: Track, prev: Point | None, p: Point
    ) -> tuple[Direction, Point] | None:
        """Detect a crossing of `wire` with hysteresis.

        A track's side of the line is only confirmed once it is more than `dead_zone`
        away from it. A crossing is a change of confirmed side whose path actually
        intersected the (finite) line, so wobbling around the line raises nothing.
        """
        segments = list(zip(wire.points, wire.points[1:], strict=False))
        if prev is not None and any(segments_intersect(prev, p, q1, q2) for q1, q2 in segments):
            track.wire_touched.add(name)

        q1, q2 = min(segments, key=lambda seg: distance_to_segment(p, *seg))
        if distance_to_segment(p, q1, q2) < wire.dead_zone:
            return None
        here = side(q1, q2, p)
        inbound = side(q1, q2, wire.inbound_point)
        if here == 0 or inbound == 0:
            return None
        current = 1 if here == inbound else -1  # +1 = protected (inbound) side

        confirmed = track.wire_side.get(name)
        track.wire_side[name] = (current, p)
        touched = name in track.wire_touched
        track.wire_touched.discard(name)
        if not touched or (confirmed is not None and confirmed[0] == current):
            return None
        # Side changed, or the track was first seen on the line and has now moved clear through it.
        start = confirmed[1] if confirmed else (prev or p)
        return (Direction.INBOUND if current == 1 else Direction.OUTBOUND), start

    def _tripwire_alert(
        self, rule: TripwireRule, track: Track, direction: Direction, a: Point, b: Point, t: float
    ) -> IBVAPEvent | None:
        if rule.direction != "any" and direction.value != rule.direction:
            return None
        if not self._passes(rule, track, t):
            return None
        return self._fire(
            rule,
            track,
            t,
            direction=direction,
            summary=f"{track.label} crossed tripwire {rule.tripwire} ({direction.value})",
            params={"tripwire": rule.tripwire, "from": a, "to": b},
        )

    # ------------------------------------------------------- state-based rules

    def _evaluate_track(self, cam: CameraRules, track: Track, t: float) -> list[IBVAPEvent]:
        alerts: list[IBVAPEvent] = []
        for rule in cam.rules:
            alert = None
            if isinstance(rule, LoiteringRule):
                alert = self._loitering(rule, track, t)
            elif isinstance(rule, VehicleStoppedRule):
                alert = self._vehicle_stopped(rule, track, t)
            elif isinstance(rule, NightMovementRule):
                alert = self._night_movement(rule, track, t)
            elif isinstance(rule, ApproachRetreatRule):
                alert = self._approach_retreat(rule, track, t)
            elif isinstance(rule, WrongDirectionRule):
                alert = self._wrong_direction(rule, track, t)
            if alert:
                alerts.append(alert)
        return alerts

    def _loitering(self, rule: LoiteringRule, track: Track, t: float) -> IBVAPEvent | None:
        entered = track.zones.get(rule.zone)
        if entered is None or t - entered < rule.dwell_s:
            return None
        once = (rule.id, rule.zone, entered)
        if once in track.fired or not self._passes(rule, track, t):
            return None
        alert = self._fire(
            rule,
            track,
            t,
            zone_id=rule.zone,
            summary=(
                f"{track.label} loitering in {rule.zone} for {t - entered:.0f}s (limit {rule.dwell_s:.0f}s)"
            ),
            params={"dwell_s": round(t - entered, 1), "limit_s": rule.dwell_s},
        )
        if alert:
            track.fired.add(once)
        return alert

    def _vehicle_stopped(self, rule: VehicleStoppedRule, track: Track, t: float) -> IBVAPEvent | None:
        entered = track.zones.get(rule.zone)
        if entered is None or track.still_since is None:
            return None
        stopped_since = max(entered, track.still_since)
        if t - stopped_since < rule.dwell_s:
            return None
        once = (rule.id, stopped_since)
        if once in track.fired or not self._passes(rule, track, t):
            return None
        alert = self._fire(
            rule,
            track,
            t,
            zone_id=rule.zone,
            summary=(
                f"{track.label} stopped in {rule.zone} for {t - stopped_since:.0f}s "
                f"(limit {rule.dwell_s:.0f}s)"
            ),
            params={"stopped_s": round(t - stopped_since, 1), "limit_s": rule.dwell_s},
        )
        if alert:
            track.fired.add(once)
        return alert

    def _night_movement(self, rule: NightMovementRule, track: Track, t: float) -> IBVAPEvent | None:
        if rule.zone is not None and rule.zone not in track.zones:
            return None
        once = (rule.id, track.zones.get(rule.zone) if rule.zone else None)
        if once in track.fired or not self._passes(rule, track, t):
            return None
        where = f"in {rule.zone}" if rule.zone else "in camera view"
        alert = self._fire(
            rule,
            track,
            t,
            zone_id=rule.zone,
            summary=f"{track.label} moving {where} during night window",
            params={
                "night_start": self.config.night.start.isoformat(),
                "night_end": self.config.night.end.isoformat(),
            },
        )
        if alert:
            track.fired.add(once)
        return alert

    def _approach_retreat(self, rule: ApproachRetreatRule, track: Track, t: float) -> IBVAPEvent | None:
        entries = track.entries.get(rule.zone)
        if not entries:
            return None
        recent = [e for e in entries if t - e <= rule.window_s]
        once = (rule.id, recent[-1] if recent else None)  # re-fire only on a further approach
        if len(recent) < rule.min_entries or once in track.fired or not self._passes(rule, track, t):
            return None
        alert = self._fire(
            rule,
            track,
            t,
            zone_id=rule.zone,
            summary=(
                f"{track.label} approached {rule.zone} {len(recent)} times in {rule.window_s:.0f}s "
                f"(limit {rule.min_entries})"
            ),
            params={"entries": len(recent), "window_s": rule.window_s},
        )
        if alert:
            track.fired.add(once)
        return alert

    def _wrong_direction(self, rule: WrongDirectionRule, track: Track, t: float) -> IBVAPEvent | None:
        entered = track.zones.get(rule.zone)
        if entered is None:
            return None
        once = (rule.id, entered)
        if once in track.fired:
            return None
        inside = [p for pt, p in track.points if pt >= entered]
        if len(inside) < 2:
            return None
        start, end = inside[0], inside[-1]
        motion = (end[0] - start[0], end[1] - start[1])
        if (motion[0] ** 2 + motion[1] ** 2) ** 0.5 < rule.min_distance:
            return None
        angle = angle_between_deg(motion, rule.allowed_direction)
        if angle <= rule.tolerance_deg or not self._passes(rule, track, t):
            return None
        alert = self._fire(
            rule,
            track,
            t,
            zone_id=rule.zone,
            summary=f"{track.label} moving against permitted direction in {rule.zone} ({angle:.0f}° off)",
            params={"angle_deg": round(angle, 1), "tolerance_deg": rule.tolerance_deg},
        )
        if alert:
            track.fired.add(once)
        return alert

    def _evaluate_camera(self, camera: str, cam: CameraRules, t: float) -> list[IBVAPEvent]:
        alerts: list[IBVAPEvent] = []
        for rule in cam.rules:
            if not isinstance(rule, GroupFormingRule):
                continue
            members = [
                tr
                for tr in self.tracks.values()
                if tr.camera == camera and rule.zone in tr.zones and self._passes(rule, tr, t)
            ]
            if len(members) < rule.min_count:
                continue
            alert = self._fire(
                rule,
                None,
                t,
                camera=camera,
                zone_id=rule.zone,
                summary=(
                    f"{len(members)} {rule.objects[0].value}s gathered in {rule.zone} "
                    f"(limit {rule.min_count})"
                ),
                params={"count": len(members), "tracking_ids": sorted(m.track_id for m in members)},
            )
            if alert:
                alerts.append(alert)
        return alerts

    # ---------------------------------------------------------------- helpers

    def is_night(self, t: float) -> bool:
        return self.config.night.is_night(_utc(t))

    def _passes(self, rule: RuleBase, track: Track, t: float) -> bool:
        if not rule.enabled or track.object_type not in rule.objects:
            return False
        night = self.is_night(t)
        if (rule.schedule == "night" and not night) or (rule.schedule == "day" and night):
            return False
        threshold = (
            rule.night_min_confidence
            if night and rule.night_min_confidence is not None
            else rule.min_confidence
        )
        return track.confidence >= threshold

    def _fire(
        self,
        rule: RuleBase,
        track: Track | None,
        t: float,
        *,
        summary: str,
        params: dict[str, Any],
        camera: str | None = None,
        zone_id: str | None = None,
        direction: Direction | None = None,
    ) -> IBVAPEvent | None:
        track_key = track.track_id if track else "*"
        camera = track.camera if track else camera
        night = self.is_night(t)
        severity = rule.night_severity if night and rule.night_severity else rule.severity

        # Cooldown: within it, only a more severe alert for the same group gets through
        # (e.g. stepping out then straight back in still raises the inbound alert).
        group = rule.cooldown_group or (
            f"tripwire:{rule.tripwire}" if isinstance(rule, TripwireRule) else rule.id
        )
        scope = "*" if rule.cooldown_scope == "camera" else track_key
        cooldown_key = (str(camera), group, scope)
        last = self._last_fire.get(cooldown_key)
        if last is not None and t - last[0] < rule.cooldown_s and severity.rank <= last[1]:
            return None
        self._last_fire[cooldown_key] = (t, severity.rank)
        explanation_params = {
            "rule_type": rule.type,  # type: ignore[attr-defined]
            "night": night,
            "min_confidence": rule.min_confidence,
            **params,
        }
        if track:
            explanation_params["frigate_event_id"] = track.track_id

        return IBVAPEvent(
            event_id=uuid.uuid5(
                ALERT_ID_NAMESPACE, f"{self.site_id}:{camera}:{rule.id}:{track_key}:{round(t * 1000)}"
            ),
            site_id=self.site_id,
            camera_id=camera,
            event_type=EVENT_TYPES[rule.type],  # type: ignore[attr-defined]
            severity=severity,
            timestamp=_utc(t),
            object_type=track.object_type if track else rule.objects[0],
            tracking_id=track.track_id if track else None,
            detection_confidence=track.confidence if track else None,
            zone_id=zone_id,
            direction=direction,
            versions=Versions(rule_id=rule.id, rule_version=self.config.version),
            explanation=Explanation(summary=summary, parameters=explanation_params),
        )
