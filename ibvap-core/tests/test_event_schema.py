from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ibvap_core.schemas import (
    AlertStatus,
    EventType,
    IBVAPEvent,
    ObjectType,
    Severity,
    can_transition,
)


def make_event(**overrides):
    fields = {
        "site_id": "BOP-DEMO-01",
        "camera_id": "cam-gate-north",
        "event_type": EventType.TRIPWIRE_CROSSING,
        "severity": Severity.CRITICAL,
        "timestamp": datetime(2026, 10, 9, 22, 15, tzinfo=UTC),
        "object_type": ObjectType.PERSON,
        "detection_confidence": 0.87,
    }
    fields.update(overrides)
    return IBVAPEvent(**fields)


def test_minimal_event_defaults():
    event = make_event()
    assert event.status is AlertStatus.GENERATED
    assert event.sync_status == "pending"
    assert event.decision_source == "rules_fallback"
    assert event.event_id is not None


def test_timestamp_normalised_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    event = make_event(timestamp=datetime(2026, 10, 10, 3, 45, tzinfo=ist))
    assert event.timestamp == datetime(2026, 10, 9, 22, 15, tzinfo=UTC)
    assert event.timestamp.utcoffset() == timedelta(0)


def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError):
        make_event(timestamp=datetime(2026, 10, 9, 22, 15))


def test_evidence_hash_must_be_sha256_hex():
    make_event(evidence_hash="a" * 64)
    with pytest.raises(ValidationError):
        make_event(evidence_hash="not-a-hash")


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        make_event(detection_confidence=1.5)


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        make_event(face_image=b"...")


def test_json_round_trip():
    event = make_event(plate_text="MH12AB1234", plate_confidence=0.62, plate_needs_review=True)
    assert IBVAPEvent.model_validate_json(event.model_dump_json()) == event


def test_severity_rank_order():
    assert Severity.CRITICAL.rank > Severity.HIGH.rank > Severity.INFORMATIONAL.rank


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        (AlertStatus.GENERATED, AlertStatus.DELIVERED, True),
        (AlertStatus.ACKNOWLEDGED, AlertStatus.VERIFIED, True),
        (AlertStatus.ACKNOWLEDGED, AlertStatus.REJECTED, True),
        (AlertStatus.VERIFIED, AlertStatus.ESCALATED, True),
        (AlertStatus.GENERATED, AlertStatus.ESCALATED, False),
        (AlertStatus.REJECTED, AlertStatus.ESCALATED, False),
        (AlertStatus.CLOSED, AlertStatus.GENERATED, False),
    ],
)
def test_lifecycle_transitions(current, new, allowed):
    assert can_transition(current, new) is allowed


def test_settings_paths_do_not_depend_on_cwd(tmp_path, monkeypatch):
    from ibvap_core.config import CORE_DIR, Settings

    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.rules_path == str(CORE_DIR / "config" / "rules.yaml")
    assert s.dashboard_dir == str((CORE_DIR / ".." / "dashboard" / "dist").resolve())
    assert s.database_url == f"sqlite:///{CORE_DIR / 'data' / 'ibvap.db'}"
    assert Settings(database_url="sqlite:////abs/x.db").database_url == "sqlite:////abs/x.db"
    assert Settings(rules_path="/etc/rules.yaml").rules_path == "/etc/rules.yaml"
