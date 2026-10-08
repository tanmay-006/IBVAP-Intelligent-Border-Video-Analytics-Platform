from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ibvap_core.rules import RulesConfig, RulesEngine, load_rules
from ibvap_core.samples import frigate_message
from ibvap_core.schemas import Direction, EventType, Severity

NIGHT = datetime(2026, 10, 9, 16, 45, tzinfo=UTC).timestamp()  # 22:15 IST
DAY = datetime(2026, 10, 9, 4, 30, tzinfo=UTC).timestamp()  # 10:00 IST

CONFIG = {
    "night": {"start": "18:30", "end": "06:00", "timezone": "Asia/Kolkata"},
    "track_ttl_s": 60,
    "cameras": {
        "cam": {
            "zones": {
                "strip": {"polygon": [[0, 0.45], [1, 0.45], [1, 0.7], [0, 0.7]]},
                "frigate_yard": {"frigate_zone": "yard"},
                "road": {"polygon": [[0.3, 0.0], [0.7, 0.0], [0.7, 1.0], [0.3, 1.0]]},
            },
            "tripwires": {
                "fence": {"points": [[0, 0.4], [0.5, 0.42], [1, 0.4]], "inbound_point": [0.5, 0.9]}
            },
            "rules": [
                {
                    "id": "cross-in",
                    "type": "tripwire",
                    "tripwire": "fence",
                    "direction": "inbound",
                    "min_confidence": 0.6,
                    "night_min_confidence": 0.45,
                    "severity": "high",
                    "night_severity": "critical",
                    "cooldown_s": 30,
                },
                {
                    "id": "strip-entry",
                    "type": "zone_entry",
                    "zone": "strip",
                    "severity": "low",
                    "cooldown_s": 0,
                },
                {"id": "yard-entry", "type": "zone_entry", "zone": "frigate_yard", "severity": "low"},
                {"id": "strip-loiter", "type": "loitering", "zone": "strip", "dwell_s": 45, "cooldown_s": 0},
                {"id": "strip-night", "type": "night_movement", "zone": "strip", "severity": "high"},
                {
                    "id": "strip-approach",
                    "type": "approach_retreat",
                    "zone": "strip",
                    "min_entries": 3,
                    "window_s": 120,
                },
                {"id": "strip-group", "type": "group_forming", "zone": "strip", "min_count": 3},
                {"id": "road-stop", "type": "vehicle_stopped", "zone": "road", "dwell_s": 30},
                {
                    "id": "road-wrong-way",
                    "type": "wrong_direction",
                    "zone": "road",
                    "allowed_direction": [0, -1],
                    "objects": ["car"],
                },
            ],
        }
    },
}


@pytest.fixture
def engine():
    config = RulesConfig.model_validate(CONFIG)
    config._version = "testversion1"
    return RulesEngine(config, "BOP-TEST-01")


class Obj:
    """A synthetic Frigate tracked object that accumulates path_data like Frigate does."""

    def __init__(self, engine, fid="p1", label="person", score=0.9, camera="cam"):
        self.engine, self.fid, self.label, self.score, self.camera = engine, fid, label, score, camera
        self.points: list[tuple[float, float, float]] = []

    def at(self, x, y, t, kind="update", zones=None):
        self.points.append((x, y, t))
        return self.send(t, kind, zones)

    def send(self, t, kind="update", zones=None):
        msg = frigate_message(
            kind,
            frigate_id=self.fid,
            camera=self.camera,
            label=self.label,
            score=self.score,
            zones=zones,
            path=self.points,
            frame_time=t,
            start_time=self.points[0][2] if self.points else t,
        )
        return self.engine.process(msg, t)


def by_rule(alerts):
    return [a.versions.rule_id for a in alerts]


def test_inbound_crossing_at_night_is_critical(engine):
    p = Obj(engine)
    assert p.at(0.5, 0.2, NIGHT, kind="new") == []
    alerts = p.at(0.5, 0.6, NIGHT + 2)
    crossing = [a for a in alerts if a.versions.rule_id == "cross-in"]
    assert len(crossing) == 1
    alert = crossing[0]
    assert alert.event_type is EventType.TRIPWIRE_CROSSING
    assert alert.severity is Severity.CRITICAL
    assert alert.direction is Direction.INBOUND
    assert alert.tracking_id == "p1"
    assert alert.versions.rule_version == "testversion1"
    assert alert.explanation.parameters["night"] is True
    assert "crossed tripwire fence (inbound)" in alert.explanation.summary


def test_inbound_crossing_by_day_is_high(engine):
    p = Obj(engine)
    p.at(0.5, 0.2, DAY, kind="new")
    (alert,) = [a for a in p.at(0.5, 0.6, DAY + 2) if a.versions.rule_id == "cross-in"]
    assert alert.severity is Severity.HIGH


def test_outbound_crossing_does_not_fire_inbound_rule(engine):
    p = Obj(engine)
    p.at(0.5, 0.9, DAY, kind="new")
    assert "cross-in" not in by_rule(p.at(0.5, 0.1, DAY + 2))


def test_sparse_points_still_cross_polyline(engine):
    p = Obj(engine)
    p.at(0.9, 0.05, DAY, kind="new")
    assert "cross-in" in by_rule(p.at(0.1, 0.95, DAY + 1))


def test_night_lowers_confidence_threshold(engine):
    day = Obj(engine, fid="d", score=0.5)
    day.at(0.5, 0.2, DAY, kind="new")
    assert "cross-in" not in by_rule(day.at(0.5, 0.6, DAY + 2))

    night = Obj(engine, fid="n", score=0.5)
    night.at(0.5, 0.2, NIGHT, kind="new")
    assert "cross-in" in by_rule(night.at(0.5, 0.6, NIGHT + 2))


def test_animals_do_not_trigger_person_rules(engine):
    dog = Obj(engine, label="dog")
    dog.at(0.5, 0.2, NIGHT, kind="new")
    assert dog.at(0.5, 0.6, NIGHT + 2) == []


def test_cooldown_suppresses_repeat_crossings(engine):
    p = Obj(engine)
    p.at(0.5, 0.2, DAY, kind="new")
    first = by_rule(p.at(0.5, 0.6, DAY + 2))
    p.at(0.5, 0.2, DAY + 5)
    second = by_rule(p.at(0.5, 0.6, DAY + 8))
    p.at(0.5, 0.2, DAY + 40)
    third = by_rule(p.at(0.5, 0.6, DAY + 45))
    assert "cross-in" in first and "cross-in" not in second and "cross-in" in third


def test_zone_entry_fires_on_each_entry(engine):
    p = Obj(engine)
    p.at(0.1, 0.9, DAY, kind="new")
    assert by_rule(p.at(0.1, 0.5, DAY + 1)).count("strip-entry") == 1
    assert "strip-entry" not in by_rule(p.at(0.15, 0.55, DAY + 2))
    p.at(0.1, 0.9, DAY + 3)
    assert "strip-entry" in by_rule(p.at(0.1, 0.5, DAY + 4))


def test_frigate_zone_membership(engine):
    p = Obj(engine)
    assert "yard-entry" in by_rule(p.at(0.1, 0.9, DAY, kind="new", zones=["yard"]))


def test_loitering_via_timer(engine):
    p = Obj(engine)
    p.at(0.1, 0.9, DAY, kind="new")
    p.at(0.1, 0.5, DAY + 1)  # enters strip
    assert "strip-loiter" not in by_rule(engine.tick(DAY + 40))
    (alert,) = [a for a in engine.tick(DAY + 47) if a.versions.rule_id == "strip-loiter"]
    assert alert.event_type is EventType.LOITERING
    assert alert.explanation.parameters["dwell_s"] == pytest.approx(46, abs=0.5)
    assert "strip-loiter" not in by_rule(engine.tick(DAY + 60))


def test_night_movement_only_at_night_once_per_visit(engine):
    p = Obj(engine)
    p.at(0.1, 0.9, DAY, kind="new")
    assert "strip-night" not in by_rule(p.at(0.1, 0.5, DAY + 1))

    n = Obj(engine, fid="n")
    n.at(0.1, 0.9, NIGHT, kind="new")
    assert "strip-night" in by_rule(n.at(0.1, 0.5, NIGHT + 1))
    assert "strip-night" not in by_rule(n.at(0.2, 0.55, NIGHT + 2))


def test_approach_and_retreat(engine):
    p = Obj(engine)
    t = DAY
    fired = []
    for _ in range(3):
        fired += by_rule(p.at(0.1, 0.5, t))
        fired += by_rule(p.at(0.1, 0.9, t + 5))
        t += 20
    assert fired.count("strip-approach") == 1
    assert "strip-approach" not in by_rule(engine.tick(t + 100))  # no new approach, no new alert


def test_group_forming(engine):
    alerts = []
    for i in range(3):
        o = Obj(engine, fid=f"g{i}")
        o.at(0.1 + i * 0.2, 0.9, DAY, kind="new")
        alerts += o.at(0.1 + i * 0.2, 0.5, DAY + 1 + i)
    group = [a for a in alerts if a.versions.rule_id == "strip-group"]
    assert len(group) == 1
    assert group[0].tracking_id is None
    assert group[0].explanation.parameters["tracking_ids"] == ["g0", "g1", "g2"]


def test_vehicle_stopped_and_people_ignored(engine):
    car = Obj(engine, fid="c1", label="car")
    car.at(0.5, 0.2, DAY, kind="new")
    car.at(0.5, 0.15, DAY + 2)  # last movement
    assert "road-stop" not in by_rule(engine.tick(DAY + 20))
    assert by_rule(engine.tick(DAY + 33)).count("road-stop") == 1
    assert "road-stop" not in by_rule(engine.tick(DAY + 50))

    person = Obj(engine, fid="p9")
    person.at(0.5, 0.2, DAY, kind="new")
    assert "road-stop" not in by_rule(engine.tick(DAY + 40))


def test_wrong_direction(engine):
    up = Obj(engine, fid="up", label="car")
    up.at(0.5, 0.9, DAY, kind="new")
    assert "road-wrong-way" not in by_rule(up.at(0.5, 0.6, DAY + 2))

    down = Obj(engine, fid="down", label="car")
    down.at(0.5, 0.2, DAY, kind="new")
    alerts = down.at(0.5, 0.5, DAY + 2)
    assert "road-wrong-way" in by_rule(alerts)
    assert "road-wrong-way" not in by_rule(down.at(0.5, 0.7, DAY + 4))


def test_end_and_ttl_drop_tracks(engine):
    a = Obj(engine, fid="a")
    a.at(0.1, 0.9, DAY, kind="new")
    a.send(DAY + 1, kind="end")
    assert ("cam", "a") not in engine.tracks

    b = Obj(engine, fid="b")
    b.at(0.1, 0.9, DAY, kind="new")
    engine.tick(DAY + 61)
    assert ("cam", "b") not in engine.tracks
    assert not [k for k in engine._last_fire if k[1] in {"a", "b"}]


def test_unconfigured_camera_is_ignored(engine):
    assert Obj(engine, camera="other").at(0.5, 0.5, DAY, kind="new") == []


def test_alert_ids_are_deterministic(engine):
    def run():
        e = RulesEngine(engine.config, "BOP-TEST-01")
        p = Obj(e)
        p.at(0.5, 0.2, DAY, kind="new")
        return [a.event_id for a in p.at(0.5, 0.6, DAY + 2)]

    assert run() == run()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["cameras"]["cam"]["rules"].append({"id": "x", "type": "loitering", "zone": "missing"}),
        lambda c: c["cameras"]["cam"]["rules"].append(
            {"id": "cross-in", "type": "zone_entry", "zone": "strip"}
        ),
        lambda c: c["cameras"]["cam"]["zones"].update(bad={"polygon": [[0, 0], [1.5, 0], [1, 1]]}),
        lambda c: c["cameras"]["cam"]["rules"].append({"id": "y", "type": "teleport", "zone": "strip"}),
    ],
)
def test_invalid_config_rejected(mutate):
    import copy

    config = copy.deepcopy(CONFIG)
    mutate(config)
    with pytest.raises(ValidationError):
        RulesConfig.model_validate(config)


def test_demo_rules_file_loads():
    config = load_rules("config/rules.yaml")
    assert len(config.version) == 12
    assert {"cam-fence-east", "cam-bop-road"} <= set(config.cameras)
