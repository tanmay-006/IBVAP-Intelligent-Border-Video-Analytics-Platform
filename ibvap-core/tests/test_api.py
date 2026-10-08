import json

from ibvap_core.samples import frigate_message


def ingest(client, **kw):
    pipeline = client.app.state.pipeline
    client.portal.call(pipeline.handle_frigate_payload, json.dumps(frigate_message(**kw)))


def first_event_id(client):
    return client.get("/events").json()[0]["event_id"]


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["site_id"] == "BOP-TEST-01"
    assert body["mqtt_connected"] is False


def test_ingest_list_get(client):
    ingest(client, label="car", plate=("MH12AB1234", 0.95))
    events = client.get("/events").json()
    assert len(events) == 1
    assert events[0]["plate_text"] == "MH12AB1234"
    assert client.get(f"/events/{events[0]['event_id']}").status_code == 200
    assert client.get("/events", params={"plate": "zz"}).json() == []
    assert client.get("/cameras").json()[0]["camera_id"] == "cam-gate-north"


def test_malformed_payload_is_ignored(client):
    client.portal.call(client.app.state.pipeline.handle_frigate_payload, b"not json")
    client.portal.call(client.app.state.pipeline.handle_frigate_payload, b'{"type": "new"}')
    assert client.get("/events").json() == []


def test_lifecycle_endpoints(client):
    ingest(client)
    eid = first_event_id(client)
    assert client.post(f"/alerts/{eid}/escalate", json={"actor": "op1"}).status_code == 409
    assert client.post(f"/alerts/{eid}/ack", json={"actor": "op1"}).json()["status"] == "acknowledged"
    assert (
        client.post(f"/alerts/{eid}/verify", json={"actor": "sup1", "note": "confirmed on clip"}).status_code
        == 200
    )
    assert client.post(f"/alerts/{eid}/escalate", json={"actor": "sup1"}).json()["status"] == "escalated"
    trail = client.get(f"/events/{eid}/audit").json()
    assert [t["to_status"] for t in trail] == ["delivered", "acknowledged", "verified", "escalated"]
    assert client.post(f"/alerts/{eid}/ack", json={"actor": ""}).status_code == 422
    assert (
        client.post("/alerts/00000000-0000-0000-0000-000000000000/ack", json={"actor": "x"}).status_code
        == 404
    )


def test_websocket_live_push_marks_delivered_and_records_latency(client):
    with client.websocket_connect("/ws/alerts") as ws:
        assert ws.receive_json() == {"type": "snapshot", "events": []}
        ingest(client, label="person", zones=["fence_strip"])
        created = ws.receive_json()
        assert created["type"] == "event.created"
        assert created["event"]["zone_id"] == "fence_strip"
        updated = ws.receive_json()
        assert updated["type"] == "event.updated"
        assert updated["event"]["status"] == "delivered"

    latency = client.get("/metrics/latency").json()
    assert latency["count"] == 1
    assert 0 <= latency["frame_to_console"]["p50_ms"] < 2000


def test_websocket_snapshot_delivers_backlog(client):
    ingest(client, frigate_id="backlog-1")
    eid = first_event_id(client)
    with client.websocket_connect("/ws/alerts") as ws:
        snapshot = ws.receive_json()
        assert [e["event_id"] for e in snapshot["events"]] == [eid]
        assert ws.receive_json()["event"]["status"] == "delivered"
    assert client.get(f"/events/{eid}").json()["status"] == "delivered"


def test_no_console_means_not_delivered(client):
    ingest(client)
    assert client.get("/events").json()[0]["status"] == "generated"
    assert client.get("/metrics/latency").json()["count"] == 0


def test_rules_alert_flows_through_pipeline(settings, tmp_path):
    import shutil

    from fastapi.testclient import TestClient

    from ibvap_core.api import create_app

    shutil.copy("config/rules.yaml", tmp_path / "rules.yaml")
    settings = settings.model_copy(update={"rules_path": str(tmp_path / "rules.yaml")})
    from datetime import UTC, datetime

    day = datetime(2026, 10, 10, 6, 20, tzinfo=UTC).timestamp()  # 11:50 IST: crossing is High, not Critical
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["rules_version"]
        path = [(0.5, 0.2, day)]
        msg = frigate_message("new", camera="cam-fence-east", path=path, frame_time=day, start_time=day)
        client.portal.call(client.app.state.pipeline.handle_frigate_payload, json.dumps(msg))
        path.append((0.5, 0.6, day + 2))
        msg = frigate_message(
            "update", camera="cam-fence-east", path=path, frame_time=day + 2, start_time=day
        )
        client.portal.call(client.app.state.pipeline.handle_frigate_payload, json.dumps(msg))

        alerts = client.get("/events", params={"event_type": "tripwire_crossing"}).json()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["clip_ref"] is None

        # Clip confirmed when the object ends → copied onto the alert.
        msg = frigate_message(
            "end", camera="cam-fence-east", path=path, frame_time=day + 5, start_time=day, has_clip=True
        )
        client.portal.call(client.app.state.pipeline.handle_frigate_payload, json.dumps(msg))
        alert = client.get(f"/events/{alerts[0]['event_id']}").json()
        assert alert["clip_ref"].endswith("/clip.mp4")
