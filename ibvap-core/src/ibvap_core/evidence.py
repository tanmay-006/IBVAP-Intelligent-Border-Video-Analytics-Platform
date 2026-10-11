"""Evidence store (Zone B): per-alert snapshot and clip, captured at the alert's own time.

- Snapshot: the camera's current frame from Frigate, grabbed as soon as the alert fires.
- Clip: Frigate's recordings from `pre_s` before to `post_s` after the alert, fetched
  once that window has been written to disk.

Files are kept locally with their SHA-256, so they stay stable when Frigate's own
retention removes the recordings, and so the Trust Layer (Phase 5) can anchor them.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from ibvap_core.schemas import IBVAPEvent

log = logging.getLogger(__name__)

PREFIX = "evidence:"
MIN_CLIP_BYTES = 10_000  # smaller responses are empty or incomplete clips


@dataclass(frozen=True)
class Captured:
    ref: str
    sha256: str


@dataclass(frozen=True)
class CapturedClip(Captured):
    start: datetime
    end: datetime


class EvidenceStore:
    def __init__(
        self,
        root: str | Path,
        frigate_url: str,
        *,
        pre_s: float = 5,
        post_s: float = 10,
        ready_delay_s: float = 15,
        retry_s: float = 10,
        attempts: int = 6,
        max_mb: float = 1500,
        retention_days: float = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.root = Path(root)
        self.frigate_url = frigate_url.rstrip("/")
        self.pre_s = pre_s
        self.post_s = post_s
        self.ready_delay_s = ready_delay_s
        self.retry_s = retry_s
        self.attempts = attempts
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.retention = timedelta(days=retention_days)
        self.transport = transport

    # ----------------------------------------------------------------- paths

    def path(self, ref: str) -> Path | None:
        """Local file for an `evidence:` ref; None for anything outside the store."""
        if not ref.startswith(PREFIX):
            return None
        name = ref.removeprefix(PREFIX)
        candidate = (self.root / name).resolve()
        if self.root.resolve() not in candidate.parents or not candidate.is_file():
            return None
        return candidate

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(10.0, read=60.0))

    async def _save(self, name: str, data: bytes) -> Captured:
        def write() -> str:
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(data)
            return hashlib.sha256(data).hexdigest()

        return Captured(ref=PREFIX + name, sha256=await asyncio.to_thread(write))

    # --------------------------------------------------------------- capture

    async def snapshot(self, event: IBVAPEvent) -> Captured | None:
        """The camera's current frame, with detection boxes and Frigate's timestamp burned in."""
        url = f"{self.frigate_url}/api/{event.camera_id}/latest.jpg?bbox=1&timestamp=1&quality=85"
        try:
            async with self._client() as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            log.warning("snapshot for alert %s failed: %s", event.event_id, exc)
            return None
        if resp.status_code != 200 or not resp.content:
            log.warning("snapshot for alert %s: Frigate answered %s", event.event_id, resp.status_code)
            return None
        return await self._save(f"{event.event_id}.jpg", resp.content)

    def clip_window(self, event: IBVAPEvent) -> tuple[float, float]:
        t = event.timestamp.timestamp()
        return t - self.pre_s, t + self.post_s

    async def clip(self, event: IBVAPEvent) -> CapturedClip | None:
        """Wait until the clip window is recorded, then fetch it; retries while Frigate finishes writing."""
        start, end = self.clip_window(event)
        wait = end + self.ready_delay_s - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        url = f"{self.frigate_url}/api/{event.camera_id}/start/{start:.3f}/end/{end:.3f}/clip.mp4"
        for attempt in range(1, self.attempts + 1):
            try:
                async with self._client() as client:
                    resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) >= MIN_CLIP_BYTES:
                    saved = await self._save(f"{event.event_id}.mp4", resp.content)
                    return CapturedClip(
                        ref=saved.ref,
                        sha256=saved.sha256,
                        start=datetime.fromtimestamp(start, UTC),
                        end=datetime.fromtimestamp(end, UTC),
                    )
                log.info(
                    "clip for alert %s not ready (HTTP %s, %d bytes), attempt %d/%d",
                    event.event_id,
                    resp.status_code,
                    len(resp.content),
                    attempt,
                    self.attempts,
                )
            except httpx.HTTPError as exc:
                log.info("clip for alert %s: %s, attempt %d/%d", event.event_id, exc, attempt, self.attempts)
            if attempt < self.attempts:
                await asyncio.sleep(self.retry_s)
        log.warning("clip for alert %s unavailable after %d attempts", event.event_id, self.attempts)
        return None

    # ------------------------------------------------------------- retention

    def cleanup(self, now: float | None = None) -> int:
        """Delete files past retention, then the oldest while over the size cap; returns files removed."""
        if not self.root.is_dir():
            return 0
        now = now or time.time()
        files = sorted((p for p in self.root.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime)
        removed = 0
        cutoff = now - self.retention.total_seconds()
        keep = []
        for f in files:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
            else:
                keep.append(f)
        total = sum(f.stat().st_size for f in keep)
        for f in keep:
            if total <= self.max_bytes:
                break
            total -= f.stat().st_size
            f.unlink(missing_ok=True)
            removed += 1
        return removed
