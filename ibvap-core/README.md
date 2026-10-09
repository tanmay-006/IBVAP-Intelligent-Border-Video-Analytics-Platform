# ibvap-core — Zone B edge backend

Consumes Frigate events over MQTT, applies border rules, stores IBVAP events, runs the alert lifecycle and pushes live alerts to operator consoles. Jev triage (Phase 6), evidence hashing (Phase 5) and sync (Phase 7) build on this.

```
Frigate ──MQTT frigate/events──▶ MqttConsumer ──▶ EventPipeline ──▶ RulesEngine (+1 s timer) ──▶ alerts
                                                        │                                         │
                                                        ├──▶ raw detection ──▶ EventStore ◀────────┘
                                                        └──▶ Broadcaster ──WebSocket /ws/alerts──▶ consoles
```

## Run locally

```bash
uv sync
uv run uvicorn ibvap_core.api:create_app --factory --port 8000
# with a broker on localhost:1883, push sample Frigate-shaped events:
uv run python scripts/publish_sample_events.py
```

Settings come from environment variables (see `../deploy/.env.example`). Set `IBVAP_MQTT_ENABLED=false` to run the API without a broker.

## Border rules

Configured per camera in [`config/rules.yaml`](config/rules.yaml) (path set by `IBVAP_RULES_PATH`). Geometry uses normalised image coordinates (x, y from 0 to 1, origin top-left), the same space as Frigate's `path_data`, so it is independent of camera resolution.

- **Zones:** our own `polygon`, or `frigate_zone: <name>` to reuse a zone defined in Frigate.
- **Tripwires:** a polyline plus an `inbound_point` anywhere on the Indian side; crossing towards that side is *inbound*.

| Rule `type` | Fires when | Key options |
|---|---|---|
| `tripwire` | Track's path crosses the line in the given direction | `tripwire`, `direction: inbound\|outbound\|any` |
| `zone_entry` | Track enters a restricted zone | `zone` |
| `loitering` | Track stays in a zone longer than `dwell_s` | `zone`, `dwell_s` |
| `night_movement` | Any matching object in the zone (or frame) during the night window | `zone` (optional) |
| `vehicle_stopped` | Vehicle in zone without moving for `dwell_s` | `zone`, `dwell_s` |
| `approach_retreat` | Track enters a zone `min_entries` times within `window_s` | `zone`, `min_entries`, `window_s` |
| `wrong_direction` | Movement within a zone deviates from `allowed_direction` by more than `tolerance_deg` | `zone`, `allowed_direction`, `tolerance_deg`, `min_distance` |
| `group_forming` | `min_count` matching objects in a zone at once | `zone`, `min_count` |

Common options on every rule: `objects`, `min_confidence`, `night_min_confidence` (higher sensitivity at night), `severity`, `night_severity`, `schedule: always|night|day`, `cooldown_s`, `enabled`. The night window (`night:` block) defaults to 18:30–06:00 Asia/Kolkata.

Every alert records the rule id, the rules-file version (short SHA-256), and an explanation with the measured values (dwell time, angle, count, direction, night flag), so operators can see why it fired.

How positions are read: Frigate adds a point to `path_data` whenever an object moves about 5% of the frame. The engine tests each new segment against tripwires and zones, so crossings are caught even when MQTT updates are sparse. A stationary object sends few updates, so dwell rules are also re-checked every second. "Stopped" means no new path point. Tracks are dropped on Frigate's `end` message or after `track_ttl_s` without updates.

The rules engine is deterministic and never calls Jev or the network.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Site id, MQTT connection, connected consoles |
| GET | `/events` | Search: `camera_id`, `event_type`, `severity`, `status`, `plate`, `since`, `until`, `open_only`, `order=time\|severity`, `limit`, `offset` |
| GET | `/events/{id}` | One event |
| GET | `/events/{id}/audit` | Lifecycle audit trail |
| POST | `/alerts/{id}/{ack\|verify\|reject\|escalate\|close}` | Lifecycle transition, body `{"actor": "...", "note": "..."}`; 409 if not allowed |
| GET | `/cameras` | Cameras from `config/site.yaml` (name, map position) merged with cameras that have sent events |
| GET | `/media/{id}/{snapshot\|clip}` | Streams the event's snapshot or clip from Frigate (502 if Frigate is unreachable) |
| GET | `/ui/` | The operator dashboard, when `dashboard/dist` has been built |
| GET | `/metrics/latency` | Frame → console latency p50/p95/max, split by stage |
| WS | `/ws/alerts` | `snapshot` of open alerts on connect, then `event.created` / `event.updated` |

## Behaviour notes

- **Event ids** are derived from site + camera + Frigate object id (UUIDv5), so re-delivered MQTT messages and later edge→centre sync cannot create duplicates.
- **Frigate updates** (`update`/`end`) are merged into the existing event: highest confidence, plate reads, zone, snapshot/clip availability. They never change lifecycle status.
- **Delivered** is set only when a console actually received the alert over WebSocket; acknowledging an undelivered alert records the implicit delivery step in the audit trail.
- **Plate reads** below `IBVAP_PLATE_REVIEW_THRESHOLD` (default 0.8) are flagged `plate_needs_review`.
- **Latency** is measured from Frigate's `frame_time` to the WebSocket push. It does not yet include Frigate's own detection/confirmation time before it publishes.
- Raw Frigate detections are stored as `detection` events at `informational` severity; rule alerts are separate events linked by `tracking_id`. When Frigate later confirms a snapshot or clip, it is copied onto the related alerts.
