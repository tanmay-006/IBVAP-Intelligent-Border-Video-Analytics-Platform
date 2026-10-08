"""Subscribes to Frigate's MQTT event topic and feeds the pipeline. Reconnects forever."""

from __future__ import annotations

import asyncio
import logging
import time

import aiomqtt

from ibvap_core.config import Settings
from ibvap_core.pipeline import EventPipeline

log = logging.getLogger(__name__)

MAX_BACKOFF_S = 30


class MqttConsumer:
    def __init__(self, settings: Settings, pipeline: EventPipeline):
        self.settings = settings
        self.pipeline = pipeline
        self.connected = False

    @property
    def topic(self) -> str:
        return f"{self.settings.frigate_topic_prefix}/events"

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.settings.mqtt_host,
                    port=self.settings.mqtt_port,
                    username=self.settings.mqtt_user,
                    password=self.settings.mqtt_password,
                    identifier=f"ibvap-core-{self.settings.site_id}",
                ) as client:
                    await client.subscribe(self.topic, qos=1)
                    self.connected = True
                    backoff = 1
                    log.info("subscribed to %s on %s", self.topic, self.settings.mqtt_host)
                    async for message in client.messages:
                        received = time.time()
                        try:
                            await self.pipeline.handle_frigate_payload(message.payload, received)
                        except Exception:
                            log.exception("failed to process message on %s", message.topic)
            except aiomqtt.MqttError as exc:
                log.warning(
                    "MQTT broker %s:%s unavailable (%s); retrying in %ss",
                    self.settings.mqtt_host,
                    self.settings.mqtt_port,
                    exc,
                    backoff,
                )
            finally:
                self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_S)
