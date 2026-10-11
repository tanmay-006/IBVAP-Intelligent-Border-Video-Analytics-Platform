import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from ibvap_core.api import create_app
from ibvap_core.evidence import EvidenceStore
from ibvap_core.schemas import EventType, IBVAPEvent, Severity

JPEG = b"\xff\xd8" + b"j" * 500
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"m" * 20_000


def alert(ts: float) -> IBVAPEvent:
    return IBVAPEvent(
        site_id="BOP-TEST-01",
        camera_id="cam-gate-west",
        event_type=EventType.TRIPWIRE_CROSSING,
        severity=Severity.HIGH,
        timestamp=datetime.fromtimestamp(ts, UTC),
    )


def frigate(clip_ready_after: int = 0):
    calls = {"clip": 0, "urls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["urls"].append(str(request.url))
        if request.url.path.endswith("/latest.jpg"):
            return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
        if request.url.path.endswith("/clip.mp4"):
            calls["clip"] += 1
            if calls["clip"] <= clip_ready_after:
                return httpx.Response(404, json={"message": "No recordings found"})
            return httpx.Response(200, content=MP4, headers={"content-type": "video/mp4"})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


def store(tmp_path, transport, **kw) -> EvidenceStore:
    opts = {"ready_delay_s": 0, "retry_s": 0, "post_s": 0, "pre_s": 5} | kw
    return EvidenceStore(tmp_path / "evidence", "http://frigate.test:5000", transport=transport, **opts)


def test_snapshot_is_the_alert_time_frame_and_is_hashed(tmp_path):
    transport, calls = frigate()
    ev = alert(time.time())
    snap = asyncio.run(store(tmp_path, transport).snapshot(ev))
    assert snap.ref == f"evidence:{ev.event_id}.jpg"
    assert snap.sha256 == hashlib.sha256(JPEG).hexdigest()
    assert "/api/cam-gate-west/latest.jpg" in calls["urls"][0]


def test_clip_covers_the_window_around_the_alert_and_retries_until_recorded(tmp_path):
    transport, calls = frigate(clip_ready_after=2)
    ts = time.time() - 30
    ev = alert(ts)
    clip = asyncio.run(store(tmp_path, transport, post_s=10).clip(ev))
    assert calls["clip"] == 3  # two "not recorded yet" answers, then the clip
    assert f"/start/{ts - 5:.3f}/end/{ts + 10:.3f}/clip.mp4" in calls["urls"][-1]
    assert clip.start.timestamp() == pytest.approx(ts - 5) and clip.end.timestamp() == pytest.approx(ts + 10)
    assert clip.sha256 == hashlib.sha256(MP4).hexdigest()


def test_clip_unavailable_after_all_attempts(tmp_path):
    transport, _ = frigate(clip_ready_after=99)
    assert asyncio.run(store(tmp_path, transport, attempts=3).clip(alert(time.time() - 30))) is None


def test_path_refuses_anything_outside_the_store(tmp_path):
    es = store(tmp_path, frigate()[0])
    (tmp_path / "secret.txt").write_text("x")
    assert es.path("evidence:../secret.txt") is None
    assert es.path("frigate:/api/x") is None


def test_cleanup_applies_retention_then_size_cap(tmp_path):
    es = store(tmp_path, frigate()[0], max_mb=0.0001, retention_days=1)  # cap ~105 bytes
    es.root.mkdir(parents=True)
    now = time.time()
    for name, age, size in (("old.jpg", 2 * 86400, 10), ("a.jpg", 300, 80), ("b.jpg", 100, 80)):
        f = es.root / name
        f.write_bytes(b"x" * size)
        os.utime(f, (now - age, now - age))
    assert es.cleanup(now) == 2
    assert [p.name for p in es.root.iterdir()] == ["b.jpg"]


def test_alert_gets_its_own_evidence_end_to_end(settings, tmp_path):
    import shutil

    from ibvap_core.samples import frigate_message

    shutil.copy("config/rules.yaml", tmp_path / "rules.yaml")
    settings = settings.model_copy(
        update={"rules_path": str(tmp_path / "rules.yaml"), "evidence_enabled": True, "clip_post_s": 0}
    )
    transport, _ = frigate()
    with TestClient(create_app(settings)) as client:
        client.app.state.evidence.transport = transport
        client.app.state.evidence.ready_delay_s = 0
        t0 = time.time() - 20
        path = [(0.5, 0.2, t0), (0.5, 0.6, t0 + 2)]
        for kind, p in (("new", path[:1]), ("update", path)):
            msg = frigate_message(kind, camera="cam-fence-east", path=p, frame_time=t0 + 2, start_time=t0)
            client.portal.call(client.app.state.pipeline.handle_frigate_payload, json.dumps(msg))

        def crossing():
            return client.get("/events", params={"event_type": "tripwire_crossing"}).json()[0]

        deadline = time.time() + 5
        while crossing()["media"] is None or crossing()["media"]["clip_status"] != "ready":
            assert time.time() < deadline, crossing()["media"]
            time.sleep(0.05)
        a = crossing()
        assert a["snapshot_ref"].startswith("evidence:") and a["clip_ref"].startswith("evidence:")
        assert a["evidence_hash"] == a["media"]["clip_sha256"] == hashlib.sha256(MP4).hexdigest()
        assert a["media"]["snapshot_sha256"] == hashlib.sha256(JPEG).hexdigest()

        snap = client.get(f"/media/{a['event_id']}/snapshot")
        assert snap.status_code == 200 and snap.content == JPEG
        part = client.get(f"/media/{a['event_id']}/clip", headers={"Range": "bytes=0-99"})
        assert part.status_code == 206 and len(part.content) == 100  # seekable in the browser
