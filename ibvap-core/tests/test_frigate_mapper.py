import pytest

from ibvap_core.frigate_mapper import detection_event_id, map_label, normalise_plate, parse_frigate_event
from ibvap_core.samples import frigate_message
from ibvap_core.schemas import EventType, ObjectType, Severity


def parse(message, threshold=0.8):
    return parse_frigate_event(message, "BOP-TEST-01", threshold)


def test_new_person_detection():
    msg = frigate_message(kind="new", zones=["fence_strip"], start_time=1760047800.0)
    parsed = parse(msg)
    event = parsed.event
    assert parsed.kind == "new"
    assert event.event_type is EventType.DETECTION
    assert event.severity is Severity.INFORMATIONAL
    assert event.object_type is ObjectType.PERSON
    assert event.camera_id == "cam-gate-north"
    assert event.zone_id == "fence_strip"
    assert event.detection_confidence == pytest.approx(0.87)
    assert event.timestamp.timestamp() == 1760047800.0
    assert event.snapshot_ref == "frigate:/api/events/1760047800.123456-abc123/snapshot.jpg"
    assert event.clip_ref is None
    assert "fence_strip" in event.explanation.summary


def test_event_id_is_stable_across_messages():
    a = parse(frigate_message(kind="new")).event
    b = parse(frigate_message(kind="end")).event
    assert (
        a.event_id
        == b.event_id
        == detection_event_id("BOP-TEST-01", "cam-gate-north", "1760047800.123456-abc123")
    )


def test_plate_read_and_review_flag():
    low = parse(frigate_message(label="car", plate=("mh 12-ab 1234", 0.62))).event
    assert low.object_type is ObjectType.CAR
    assert low.plate_text == "MH12AB1234"
    assert low.plate_confidence == pytest.approx(0.62)
    assert low.plate_needs_review is True

    high = parse(frigate_message(label="car", plate=("MH12AB1234", 0.93))).event
    assert high.plate_needs_review is False


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("dog", ObjectType.ANIMAL),
        ("cow", ObjectType.ANIMAL),
        ("truck", ObjectType.TRUCK),
        ("umbrella", ObjectType.OTHER),
    ],
)
def test_label_mapping(label, expected):
    assert map_label(label) is expected


def test_unknown_message_type_rejected():
    with pytest.raises(ValueError):
        parse({"type": "bogus", "after": {}})


def test_normalise_plate():
    assert normalise_plate(" dl 3c-ab 1234 ") == "DL3CAB1234"
