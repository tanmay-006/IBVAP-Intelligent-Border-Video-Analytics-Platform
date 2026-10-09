# Third-party components and licences

Every third-party component used by IBVAP is listed here. Add a row before introducing a new dependency.

| Component | Used for | Licence | How we use it |
|---|---|---|---|
| Frigate | Camera ingestion, detection, face/LPR enrichments, recording | MIT | Official Docker image; config only, no source copied |
| Pydantic | Event schema and validation (ibvap-core) | MIT | Python dependency |
| FastAPI | REST + WebSocket API (ibvap-core) | MIT | Python dependency |
| Uvicorn (+ standard extras: uvloop, httptools, websockets, watchfiles, python-dotenv) | ASGI server | BSD-3-Clause (extras: MIT / Apache-2.0 / BSD) | Python dependency |
| SQLAlchemy | Event storage (SQLite edge / PostgreSQL centre) | MIT | Python dependency |
| aiomqtt | Async MQTT client for Frigate events | BSD-3-Clause | Python dependency |
| paho-mqtt | MQTT protocol (via aiomqtt) | EPL-2.0 / EDL-1.0 (dual) | Transitive dependency, used under EDL-1.0 |
| pydantic-settings | Environment configuration | MIT | Python dependency |
| PyYAML | Rules configuration files | MIT | Python dependency |
| tzdata | IANA time zones for the night window (slim containers) | Apache-2.0 | Python dependency |
| Eclipse Mosquitto | MQTT broker | EPL-2.0 / EDL-1.0 (dual) | Official Docker image `eclipse-mosquitto` |
| MediaMTX | RTSP server for looped test footage (development only) | MIT | Approved; added in Phase 1 |
| HTTPX | Proxying Frigate snapshots/clips to the dashboard; API test client | BSD-3-Clause | Python dependency |
| React, React DOM | Operator dashboard UI | MIT | npm dependency |
| MapLibre GL JS | Camera map | BSD-3-Clause | npm dependency |
| Barlow, Barlow Semi Condensed (via Fontsource) | Dashboard typefaces, bundled so they work offline | SIL OFL-1.1 | npm dependency |
| OpenStreetMap tiles | Map background when online | Data: ODbL; attribution shown on the map | Fetched at runtime; markers still work offline |
| Vite, @vitejs/plugin-react | Dashboard build and dev server (dev only) | MIT | Dev dependency |
| TypeScript | Type checking (dev only) | Apache-2.0 | Dev dependency |
| Vitest | Dashboard unit tests (dev only) | MIT | Dev dependency |
| pytest | Tests (dev only) | MIT | Dev dependency |
| Ruff | Linting (dev only) | MIT | Dev dependency |

Planned (added when the relevant phase lands): Hyperledger Fabric (Apache-2.0). Jev / TypeSafe AI is a commercial API, used under its terms of service.

Ultralytics YOLO packages are AGPL-3.0 and are not used.
