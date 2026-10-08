# Third-party components and licences

Every third-party component used by IBVAP is listed here. Add a row before introducing a new dependency.

| Component | Used for | Licence | How we use it |
|---|---|---|---|
| Frigate | Camera ingestion, detection, face/LPR enrichments, recording | MIT | Official Docker image; config only, no source copied |
| Pydantic | Event schema and validation (ibvap-core) | MIT | Python dependency |
| pytest | Tests (dev only) | MIT | Dev dependency |
| Ruff | Linting (dev only) | MIT | Dev dependency |

Planned (added when the relevant phase lands): Eclipse Mosquitto (EPL-2.0/EDL-1.0), FastAPI (MIT), SQLAlchemy (MIT), Roboflow supervision (MIT), Hyperledger Fabric (Apache-2.0), React (MIT), MapLibre GL JS (BSD-3-Clause), MediaMTX (MIT, pending approval). Jev / TypeSafe AI is a commercial API, used under its terms of service.

Ultralytics YOLO packages are AGPL-3.0 and are not used.
