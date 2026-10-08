import pytest

from ibvap_core.frigate_mapper import parse_frigate_event
from ibvap_core.samples import frigate_message
from ibvap_core.schemas import AlertStatus, Severity
from ibvap_core.store import EventFilter, EventNotFound, InvalidTransition


def event_from(**kw):
    return parse_frigate_event(frigate_message(**kw), "BOP-TEST-01", 0.8).event


def test_insert_then_merge_update(store):
    first = store.upsert_event(event_from(kind="new", label="car", score=0.7), 1.0, 1.1)
    assert first.created

    same = store.upsert_event(event_from(kind="update", label="car", score=0.6), 2.0, 2.1)
    assert not same.created and not same.changed
    assert same.event.detection_confidence == pytest.approx(0.7)

    with_plate = store.upsert_event(
        event_from(kind="update", label="car", score=0.9, plate=("MH12AB1234", 0.95), has_clip=True), 3.0, 3.1
    )
    assert with_plate.changed
    stored = store.get(str(first.event.event_id))
    assert stored.plate_text == "MH12AB1234"
    assert stored.detection_confidence == pytest.approx(0.9)
    assert stored.clip_ref is not None
    assert stored.status is AlertStatus.GENERATED


def test_update_does_not_reset_lifecycle(store):
    event = store.upsert_event(event_from(kind="new"), None, None).event
    store.transition(str(event.event_id), AlertStatus.ACKNOWLEDGED, "op1")
    store.upsert_event(event_from(kind="end", zones=["road"]), None, None)
    assert store.get(str(event.event_id)).status is AlertStatus.ACKNOWLEDGED


def test_ack_from_generated_records_implicit_delivery(store):
    event = store.upsert_event(event_from(), None, None).event
    store.transition(str(event.event_id), AlertStatus.ACKNOWLEDGED, "op1", "seen on wall")
    trail = store.audit(str(event.event_id))
    assert [(a["from_status"], a["to_status"], a["actor"]) for a in trail] == [
        ("generated", "delivered", "system"),
        ("delivered", "acknowledged", "op1"),
    ]


def test_invalid_transition_is_rejected_and_not_audited(store):
    event = store.upsert_event(event_from(), None, None).event
    with pytest.raises(InvalidTransition):
        store.transition(str(event.event_id), AlertStatus.ESCALATED, "op1")
    assert store.audit(str(event.event_id)) == []
    assert store.get(str(event.event_id)).status is AlertStatus.GENERATED


def test_missing_event(store):
    with pytest.raises(EventNotFound):
        store.transition("00000000-0000-0000-0000-000000000000", AlertStatus.ACKNOWLEDGED, "op1")


def test_filters_and_severity_order(store):
    a = event_from(frigate_id="a", camera="cam-1", start_time=100.0)
    b = event_from(frigate_id="b", camera="cam-2", start_time=200.0, label="car", plate=("KA01XY0001", 0.9))
    c = event_from(frigate_id="c", camera="cam-1", start_time=300.0).model_copy(
        update={"severity": Severity.HIGH}
    )
    for e in (a, b, c):
        store.upsert_event(e, None, None)

    assert [e.tracking_id for e in store.list(EventFilter())] == ["c", "b", "a"]
    assert [e.tracking_id for e in store.list(EventFilter(camera_id="cam-1"))] == ["c", "a"]
    assert [e.tracking_id for e in store.list(EventFilter(plate_text="ka01"))] == ["b"]
    assert store.list(EventFilter(order="severity"))[0].tracking_id == "c"
    assert [c["camera_id"] for c in store.cameras()] == ["cam-1", "cam-2"]
