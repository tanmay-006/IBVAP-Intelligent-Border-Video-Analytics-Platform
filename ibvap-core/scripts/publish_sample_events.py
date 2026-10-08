"""Publish Frigate-shaped sample events to MQTT, to exercise ibvap-core without cameras.

uv run python scripts/publish_sample_events.py --host localhost
"""

import argparse
import asyncio
import json
import time
import uuid

import aiomqtt

from ibvap_core.samples import frigate_message


async def main(host: str, port: int, prefix: str) -> None:
    topic = f"{prefix}/events"
    person = f"{time.time():.6f}-{uuid.uuid4().hex[:6]}"
    car = f"{time.time():.6f}-{uuid.uuid4().hex[:6]}"
    t0 = time.time()
    # Person walks from beyond the fence (top) across it into the fence strip: fence-crossing-inbound.
    walk = [(0.5, 0.2, t0), (0.5, 0.35, t0 + 1), (0.5, 0.55, t0 + 2)]
    fence = {"frigate_id": person, "camera": "cam-fence-east", "start_time": t0}
    road = {"frigate_id": car, "camera": "cam-bop-road", "label": "car", "start_time": t0}
    messages = [
        frigate_message("new", **fence, path=walk[:1]),
        frigate_message("new", **road, path=[(0.5, 0.8, t0)]),
        frigate_message("update", **fence, path=walk[:2]),
        frigate_message("update", **fence, path=walk, zones=["fence_strip"]),
        # Fictional plate, low confidence → flagged for review.
        frigate_message("update", **road, path=[(0.5, 0.8, t0)], plate=("MH12ZZ0001", 0.64)),
        frigate_message("end", **fence, path=walk, has_clip=True),
    ]
    async with aiomqtt.Client(hostname=host, port=port) as client:
        for msg in messages:
            # Replay the scripted timeline relative to now, so latency figures stay meaningful.
            msg["after"]["frame_time"] = time.time()
            await client.publish(topic, json.dumps(msg), qos=1)
            print(f"published {msg['type']:<6} {msg['after']['label']:<6} {msg['after']['id']}")
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--prefix", default="frigate")
    args = parser.parse_args()
    try:
        asyncio.run(main(args.host, args.port, args.prefix))
    except aiomqtt.MqttError as exc:
        raise SystemExit(
            f"Cannot reach MQTT broker at {args.host}:{args.port} ({exc}). Is Mosquitto running?"
        ) from None
