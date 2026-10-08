"""Per-camera border rule configuration (CLAUDE.md §4), loaded from YAML.

Geometry is in normalised image coordinates (0..1, origin top-left), the same
space as Frigate's `path_data`, so it does not depend on the detect resolution.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, time
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from ibvap_core.rules.geometry import Point
from ibvap_core.schemas import ObjectType, Severity

NormPoint = Annotated[tuple[float, float], Field(description="(x, y), each 0..1")]
VEHICLES = [ObjectType.CAR, ObjectType.MOTORCYCLE, ObjectType.BUS, ObjectType.TRUCK, ObjectType.BICYCLE]


def _check_points(points: list[Point]) -> list[Point]:
    for x, y in points:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"point ({x}, {y}) is outside the 0..1 normalised frame")
    return points


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NightWindow(Strict):
    start: time = time(18, 30)
    end: time = time(6, 0)
    timezone: str = "Asia/Kolkata"

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    def is_night(self, at: datetime) -> bool:
        local = at.astimezone(ZoneInfo(self.timezone)).time()
        if self.start <= self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end


class ZoneConfig(Strict):
    """Either our own polygon, or a zone already defined in Frigate's config."""

    polygon: list[NormPoint] | None = None
    frigate_zone: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> ZoneConfig:
        if (self.polygon is None) == (self.frigate_zone is None):
            raise ValueError("a zone needs exactly one of `polygon` or `frigate_zone`")
        if self.polygon is not None:
            if len(self.polygon) < 3:
                raise ValueError("a polygon needs at least 3 points")
            _check_points(self.polygon)
        return self


class TripwireConfig(Strict):
    points: list[NormPoint] = Field(min_length=2, description="Polyline, e.g. along the fence")
    inbound_point: NormPoint = Field(description="Any point on the Indian (protected) side of the line")

    @model_validator(mode="after")
    def _validate(self) -> TripwireConfig:
        _check_points([*self.points, self.inbound_point])
        return self


class RuleBase(Strict):
    id: str = Field(min_length=1)
    enabled: bool = True
    objects: list[ObjectType] = Field(default_factory=lambda: [ObjectType.PERSON, *VEHICLES])
    min_confidence: float = Field(0.5, ge=0, le=1)
    night_min_confidence: float | None = Field(None, ge=0, le=1, description="Higher sensitivity at night")
    severity: Severity = Severity.MEDIUM
    night_severity: Severity | None = None
    schedule: Literal["always", "night", "day"] = "always"
    cooldown_s: float = Field(60, ge=0)


class TripwireRule(RuleBase):
    type: Literal["tripwire"]
    tripwire: str
    direction: Literal["inbound", "outbound", "any"] = "inbound"


class ZoneEntryRule(RuleBase):
    type: Literal["zone_entry"]
    zone: str


class LoiteringRule(RuleBase):
    type: Literal["loitering"]
    zone: str
    dwell_s: float = Field(30, gt=0)
    objects: list[ObjectType] = Field(default_factory=lambda: [ObjectType.PERSON])


class NightMovementRule(RuleBase):
    type: Literal["night_movement"]
    zone: str | None = Field(None, description="None = anywhere in the frame")
    schedule: Literal["night"] = "night"


class VehicleStoppedRule(RuleBase):
    type: Literal["vehicle_stopped"]
    zone: str
    dwell_s: float = Field(20, gt=0, description="Seconds without moving (no new Frigate path point)")
    objects: list[ObjectType] = Field(default_factory=lambda: list(VEHICLES))


class ApproachRetreatRule(RuleBase):
    type: Literal["approach_retreat"]
    zone: str
    min_entries: int = Field(3, ge=2)
    window_s: float = Field(120, gt=0)
    objects: list[ObjectType] = Field(default_factory=lambda: [ObjectType.PERSON])


class WrongDirectionRule(RuleBase):
    type: Literal["wrong_direction"]
    zone: str
    allowed_direction: NormPoint = Field(description="Permitted travel direction as an image-space vector")
    tolerance_deg: float = Field(100, gt=0, lt=180)
    min_distance: float = Field(0.08, gt=0)

    @field_validator("allowed_direction")
    @classmethod
    def _non_zero(cls, value: Point) -> Point:
        if value == (0, 0):
            raise ValueError("allowed_direction must be non-zero")
        return value


class GroupFormingRule(RuleBase):
    type: Literal["group_forming"]
    zone: str
    min_count: int = Field(3, ge=2)
    objects: list[ObjectType] = Field(default_factory=lambda: [ObjectType.PERSON])


Rule = Annotated[
    TripwireRule
    | ZoneEntryRule
    | LoiteringRule
    | NightMovementRule
    | VehicleStoppedRule
    | ApproachRetreatRule
    | WrongDirectionRule
    | GroupFormingRule,
    Field(discriminator="type"),
]


class CameraRules(Strict):
    zones: dict[str, ZoneConfig] = Field(default_factory=dict)
    tripwires: dict[str, TripwireConfig] = Field(default_factory=dict)
    rules: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _references_exist(self) -> CameraRules:
        for rule in self.rules:
            zone = getattr(rule, "zone", None)
            if zone is not None and zone not in self.zones:
                raise ValueError(f"rule {rule.id!r} refers to unknown zone {zone!r}")
            if isinstance(rule, TripwireRule) and rule.tripwire not in self.tripwires:
                raise ValueError(f"rule {rule.id!r} refers to unknown tripwire {rule.tripwire!r}")
        return self


class RulesConfig(Strict):
    night: NightWindow = Field(default_factory=NightWindow)
    track_ttl_s: float = Field(120, gt=0, description="Forget tracks with no update for this long")
    cameras: dict[str, CameraRules] = Field(default_factory=dict)

    _version: str = PrivateAttr("unversioned")

    @model_validator(mode="after")
    def _unique_rule_ids(self) -> RulesConfig:
        seen: set[str] = set()
        for cam in self.cameras.values():
            for rule in cam.rules:
                if rule.id in seen:
                    raise ValueError(f"duplicate rule id {rule.id!r}")
                seen.add(rule.id)
        return self

    @property
    def version(self) -> str:
        """Short SHA-256 of the source file; recorded on every alert and later anchored on the ledger."""
        return self._version


def load_rules(path: str | Path) -> RulesConfig:
    raw = Path(path).read_bytes()
    config = RulesConfig.model_validate(yaml.safe_load(raw) or {})
    config._version = hashlib.sha256(raw).hexdigest()[:12]
    return config
