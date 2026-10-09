# IBVAP Development Plan

Ten phases, ordered by dependency. The ingestion → events → rules → dashboard path comes first so a working demo exists early. The two highest-risk items (Fabric, Jev) start early in parallel rather than at the end.

Durations are in weeks from start, assuming ~8 weeks and 4–6 people. Convert to real dates once the finale date is fixed.

Zone references (A/B/C, Trust Layer) follow the architecture in `CLAUDE.md` §3.

---

## Phase 0 — Foundations (week 1, days 1–2)
**Zone:** cross-cutting

- Repo layout: `frigate/`, `ibvap-core/`, `trust-layer/`, `dashboard/`, `deploy/`, `docs/`, `samples/`.
- `.gitignore`, `deploy/.env.example` (no real secrets), `docs/LICENSES.md`.
- Shared **IBVAP event schema** (all `CLAUDE.md` §4 fields) as a Pydantic model plus exported JSON Schema. Every component codes against it.
- CI skeleton: Python lint + tests (TypeScript added with the dashboard).

**Done when:** repo scaffolded; event schema reviewed and merged.

## Phase 1 — Ingestion & detection (week 1)
**Zone:** B — stream gateway + inference

- Docker Compose: Frigate (official image) + Mosquitto + local RTSP server (MediaMTX, MIT — approved) looping test videos.
- 2–3 test streams: day, night and road/vehicle clips from `samples/`, plus one phone IP-camera stream.
- Frigate config: person, car, motorcycle, bus, truck; basic zones; recordings and snapshots on.

**Done when:** `mosquitto_sub -t 'frigate/events'` shows person/vehicle events from every camera.

## Phase 2 — ibvap-core foundation (weeks 1–2)
**Zone:** B — event intelligence base

- FastAPI service; MQTT consumer for `frigate/events` → IBVAP events (`frigate/reviews` deferred until a rule needs it).
- Storage via SQLAlchemy: SQLite at the edge, PostgreSQL at the centre, same models.
- Alert lifecycle state machine: Generated → Delivered → Acknowledged → Verified/Rejected → Escalated/Closed; every transition written to an audit table.
- REST: `/events`, `/alerts/{id}/ack|verify|reject|escalate`, `/cameras`. WebSocket: `/ws/alerts`.
- Latency timestamps at each stage (frame → MQTT → rule → alert → WebSocket) from day one.

**Done when:** a Frigate detection appears on `/ws/alerts` with measured latency.

## Phase 3 — Rules engine (weeks 2–3)
**Zone:** B — rules engine (core original work)

- Per-camera YAML rules: object type, zone, schedule, min confidence, dwell time, direction, severity, cooldown.
- Rules:
  1. Virtual fence / directional tripwire (line crossing with direction; own geometry, no extra dependency)
  2. Restricted zone entry
  3. Night-time movement (fixed window or sunrise/sunset), higher sensitivity
  4. Loitering (dwell time in zone)
  5. Vehicle stopped in sensitive area
  6. Repeated approach and retreat
  7. Wrong-direction movement
  8. Group forming (N+ persons in zone)
- Every alert records why it fired: rule id/version, zone, confidence, parameters.
- Unit tests with synthetic track sequences (no Frigate needed).

**Done when:** demo scenarios 1 and 2 fire correctly from test videos; rule tests pass.

## Phase 4 — Operator dashboard v1 (weeks 2–4, parallel with Phase 3)
**Zone:** C

- React + TypeScript (Vite). Live alert queue ranked by severity, then time.
- Alert detail: snapshot + clip (proxied through ibvap-core from Frigate's API), explainability panel, lifecycle buttons.
- MapLibre map of cameras and alerts (fictional BOP coordinates).
- Event search by time, camera, type, plate, severity.

**Done when:** an operator can see an alert arrive, open its clip, and acknowledge → verify → escalate it.

## Phase 5 — Evidence & Trust Layer (weeks 2–5; start early, highest risk)
**Zone:** Trust Layer (cross-cutting)

- Evidence service: copy clips/snapshots into our evidence store, compute SHA-256, encrypt at rest (AES-GCM; keys from env/file outside git).
- Hyperledger Fabric test network (2 orgs: BOP, HQ). Chaincode: `AnchorHash(type, refId, hash, meta)`, `GetHash(refId)`. Language: Go or TypeScript (team decision).
- Anchoring worker with retry queue. Anchors: event hash, evidence hash, status changes, rule config changes, model versions. Stores the ledger tx id on the event.
- `/evidence/{id}/verify` endpoint + dashboard button: recompute hash → compare with ledger → match / mismatch.
- Tamper demo script: modify a clip, show verification failing.
- Anchoring sits behind an interface so other work is not blocked while Fabric is being set up.

**Done when:** demo scenario 5 works end to end.

## Phase 6 — Jev triage (weeks 4–5)
**Zone:** B — event intelligence

- Week 1 action: obtain API access, read docs.typesafe.ai, confirm request format, pricing and latency.
- Client sends **text/JSON only** (event type, zone, time, object, dwell, recent history at that camera) and receives severity, escalate flag, false-positive likelihood, reasoning.
- Hard timeout budget (~500 ms). On timeout or error, fall back to rule severity; `decision_source` records which was used.
- Deterministic override: Jev can never downgrade a critical rule.
- False-positive merge/suppression (scenario 3), with reasoning shown on the dashboard.
- Measure real Jev latency for the presentation.

**Done when:** scenario 3 works; cutting the network shows "rules fallback" on alerts.

## Phase 7 — Offline edge & centre sync (weeks 5–6)
**Zone:** B → C

- Split Compose into **edge** (Frigate, Mosquitto, ibvap-core edge, SQLite, local console) and **centre** (ibvap-core centre, PostgreSQL, dashboard, Fabric).
- Edge outbox: events and hashes queued and pushed when the WAN is up. Idempotent by event id (no duplicates); original timestamps preserved; video pulled only on request.
- mTLS between edge and centre (self-signed demo CA).
- Network-cut demo: disconnect the edge network → local alerts continue → reconnect → backlog syncs.

**Done when:** scenario 4 works fully; sync status visible per event.

## Phase 8 — Enrichments: ANPR, face, night (weeks 4–6, parallel)
**Zone:** B — inference

- Frigate LPR on; normalise plates to Indian formats (state series, BH series); low-confidence reads flagged for review.
- Face detection on; recognition behind an "authorised" toggle, off by default; watchlist changes audited and anchored; every match human-verified.
- Faces blurred in general dashboard views.
- Night: test on IR/low-light clips and tune thresholds. Low-light enhancement (Zero-DCE) only if time allows.
- Demo data: fictional plates; faces only of consenting team members.

## Phase 9 — Security hardening & nice-to-haves (weeks 6–7)

- Roles: operator / supervisor / auditor (JWT).
- Anchor model and config version hashes on deploy.
- Secrets audit, including git history.
- If time allows: siren/relay webhook, evidence package export, cross-camera plate search, analytics charts.

## Phase 10 — Measure, document, rehearse (weeks 7–8)

- Measure real numbers: frame-to-alert latency (p50/p95), Jev latency, sync catch-up time, CPU/GPU per stream. **Update the deck if any target is not met.**
- README: architecture diagram, setup, credits and licences (Frigate, supervision, MediaMTX, Hyperledger Fabric, Jev).
- `docs/DEMO_SCRIPT.md`: all 5 scenarios scripted and timed, with backup recordings.
- At least 3 full offline dry runs on the demo laptop.

---

## Workstreams (team of 5–6)

| Stream | Phases |
|---|---|
| Edge / DevOps | 0, 1, 7, 9 |
| Backend core + rules | 2, 3 |
| Dashboard | 4 |
| Trust Layer | 5 |
| Jev + enrichments | 6, 8 |
| Everyone | 10 |

## Top risks

| Risk | Mitigation |
|---|---|
| Fabric setup complexity | Start in week 2; anchoring behind an interface |
| Jev access, cost or latency unknown | Confirm in week 1; rules fallback is always complete on its own |
| LPR / face recognition slow on laptops without GPU | Test early on the actual demo hardware |
| Footage rights | Record our own clips (incl. night) early |
| < 2 s alert latency claim | Instrument from Phase 2 |

## Open decisions

- Finale / submission date and team size (to convert weeks to dates).
- Fabric chaincode language: Go or TypeScript?

## Status

| Phase | Status |
|---|---|
| 0 — Foundations | Done |
| 1 — Ingestion & detection | Waiting on test footage + GPU info (MediaMTX approved) |
| 2 — ibvap-core foundation | Done — verified against a real Mosquitto broker with Frigate-shaped sample events; not yet against live Frigate |
| 3 — Rules engine | Done — all 8 rules unit-tested with synthetic tracks; verified over real MQTT with sample events, not yet on live video |
| 4 — Operator dashboard | Done — live queue, alert detail with lifecycle, camera map, search; verified in a browser against sample events (snapshots/clips need Frigate) |
| 5–10 | Not started |
