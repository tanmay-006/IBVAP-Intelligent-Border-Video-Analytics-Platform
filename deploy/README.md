# deploy/ — Edge stack (Docker Compose)

```bash
docker compose -f deploy/docker-compose.yml up -d                  # Mosquitto, MediaMTX (webcam as RTSP), Frigate
docker compose -f deploy/docker-compose.yml --profile core up -d   # also ibvap-core in a container
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f frigate
docker compose -f deploy/docker-compose.yml down                   # stop (data volumes are kept)
```

| Service | Port (127.0.0.1 only) | Role |
|---|---|---|
| mosquitto | 1883 | MQTT broker: Frigate publishes events, ibvap-core subscribes |
| mediamtx | 8554 | Publishes the webcam (and optional looped test clips) as RTSP camera streams |
| frigate | 5000 (internal API), 8971 (UI) | Detection, tracking, snapshots and clips |
| ibvap-core (profile `core`) | 8000 | Rules, alerts, API and dashboard |

Optional overrides go in `deploy/.env` (copy from `.env.example`; git-ignored). Images are pinned: Frigate 0.18.0 by digest, MediaMTX 1.21.2, Mosquitto 2.0.20.

The dev broker allows anonymous connections on the local Docker network. Passwords and TLS between services come in Phase 9.
