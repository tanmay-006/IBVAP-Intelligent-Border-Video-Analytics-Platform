# IBVAP — Intelligent Border Video Analytics Platform

Software-only AI video analytics on existing border CCTV, built for Smart India Hackathon 2026, PS 26187 (MHA / Sashastra Seema Bal). Team LUNATIQ22719.

IBVAP runs at each Border Out Post (BOP) on one small computer, adds detection, border rules, triage and tamper-evident evidence on top of existing IP cameras, works offline, and syncs to the command centre when the network returns.

## Repository layout

| Folder | Purpose |
|---|---|
| `frigate/` | Frigate configuration (cameras, zones, detectors, enrichments) |
| `ibvap-core/` | Backend: rules engine, Jev client with fallback, evidence/hash service, sync queue, REST/WebSocket API |
| `trust-layer/` | Hyperledger Fabric network and chaincode for anchoring hashes |
| `dashboard/` | React operator dashboard |
| `deploy/` | Docker Compose files, environment templates |
| `docs/` | Development plan, architecture notes, event schema, licences |
| `samples/` | Test footage we have rights to use |

## Status

Phase 0 (foundations) complete: see [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md).

## Event schema

All components share one event record, defined in `ibvap-core/src/ibvap_core/schemas/event.py` and exported as JSON Schema to `docs/schemas/ibvap-event.schema.json`. After changing the model, regenerate it:

```bash
cd ibvap-core
uv run python scripts/export_schema.py
```

## Development

```bash
cd ibvap-core
uv sync
uv run pytest
uv run ruff check .
```

## Credits and licences

IBVAP builds on [Frigate](https://github.com/blakeblackshear/frigate) (MIT), used via its official Docker image. Planned: Roboflow supervision (MIT), Hyperledger Fabric (Apache-2.0), and Jev by TypeSafe AI (commercial API). Full list: [docs/LICENSES.md](docs/LICENSES.md).
