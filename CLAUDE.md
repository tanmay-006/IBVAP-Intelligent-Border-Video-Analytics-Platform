# IBVAP — Intelligent Border Video Analytics Platform

Project context for Claude Code. Read this fully before making changes. It describes what we are building, why, the architecture, the decisions already made, and the rules to follow.

---

## 1. Hackathon context

| Item | Value |
|---|---|
| Event | Smart India Hackathon (SIH) 2026 |
| Problem Statement ID | 26187 |
| PS title | AI-Based Intelligent Video Analytics Platform for Border Surveillance using existing CCTV Infrastructure |
| Organisation | Ministry of Home Affairs (MHA) |
| Department | Sashastra Seema Bal (SSB), Police II Division |
| Category | Software |
| Theme | Blockchain & Cybersecurity |
| Team name | LUNATIQ22719 |
| Team ID | 122202 |
| Our repo | github.com/tanmay-006/IBVAP-Intelligent-Border-Video-Analytics-Platform |

### What the PS asks for
Border forces already have IP CCTV cameras at Border Out Posts (BOPs), check posts and border roads, but these only record and display video, and someone has to watch them all the time. Advanced features (face recognition, ANPR, intrusion detection, tracking) normally need expensive proprietary hardware. The PS wants a **software-only platform** that ingests live streams from standard IP cameras and adds AI analytics on top.

Required capabilities (all must be demonstrable):
1. Human detection and tracking
2. Vehicle detection and classification
3. Face detection
4. Automatic Number Plate Recognition (ANPR)
5. Virtual fence intrusion detection
6. Suspicious activity detection
7. Night-time movement detection
8. Real-time alert generation and event logging

Expected qualities: no dependence on dedicated surveillance hardware; real-time alerts; face, vehicle and behaviour analytics in software; integration with existing command-and-control (C2) systems; cost-effective, scalable, suitable for remote border sites.

### What we promised in the idea submission (stay consistent with this)
- Software-only and edge-first: one small computer per BOP; no camera replacement.
- Works fully offline at the BOP; syncs to the command centre when the network returns (events first, video only on request).
- **Jev (TypeSafe AI)** is the decision/triage layer: it turns raw detections into typed, calibrated decisions (severity, escalate or not, likely false positive). It is a paid cloud API, so when offline the rules engine alone must keep critical alerts working.
- **Trust Layer:** SHA-256 hash of every event, evidence clip, rule change and model version, anchored on a permissioned **Hyperledger Fabric** ledger. No video or personal data on-chain.
- Cybersecurity: mTLS between services, network segmentation, signed models, secrets kept out of code.
- Privacy by design: face recognition off by default, enabled only when authorised; every match is human-verified; aligned with India's DPDP Act 2023.
- Design targets shown to judges: 0 new cameras; < 2 s alert latency at the edge; 24×7 monitoring incl. night; Jev decision 70–500 ms (TypeSafe's published range, to be measured by us).

---

## 2. Build strategy (decided)

**Base: Frigate (MIT licence) + our own IBVAP layer on top.**

- **Frigate** (github.com/blakeblackshear/frigate, docs.frigate.video) is our camera ingestion and detection layer: RTSP/ONVIF input, real-time object detection, zones, face recognition, licence plate recognition (LPR), recording/snapshots, review UI, HTTP API and MQTT events. We use it like a library and do not fork-and-rebrand it.
- **Our original work** (what judges should see as ours): the border-specific rules engine, Jev triage, the Trust Layer (hashing + Hyperledger Fabric), offline store-and-forward sync, and the SSB operator dashboard.
- Roboflow **supervision** (MIT) may be used for zone/line-crossing geometry and annotation helpers.

### Originality rules — important
- Many other SIH 2026 teams have public repos for this same PS (e.g. akash-das-37/IBVAP, Mohit427/ibvap-border-surveillance, noshikacodes/IBVAP, BHANUASATI/circuitvision…, tiru-venkatesh/IBVAP, devsp0007/SIH26187-). **Never copy code from them.** Most have no licence, and copying risks disqualification for plagiarism. Reading them for ideas is fine; writing our own implementation is required.
- Only use dependencies with clear licences. Record every third-party component and its licence in the README.
- Note: Ultralytics YOLO packages are AGPL-3.0. Prefer Frigate's own detectors, or flag it before adding Ultralytics directly.

---

## 3. System architecture

Three zones plus a cross-cutting trust layer.

### Zone A — Existing CCTV (not built by us)
IP cameras (RTSP/ONVIF), NVR/DVR feeds, IR/thermal cameras where installed. For development, use phone IP-camera apps, webcams, or looped test videos served as RTSP.

### Zone B — Edge node at each BOP (runs fully offline)
1. **Stream gateway (Frigate):** decodes streams, samples frames, monitors camera health.
2. **AI inference (Frigate + enrichments):** person and vehicle detection, vehicle class, face detection, LPR; low-light handling for night footage.
3. **Rules engine (ours):** subscribes to Frigate MQTT events and applies border rules (see §4). Produces IBVAP events.
4. **Event intelligence (ours, uses Jev):** sends a text/JSON description of each event (never images or faces) to Jev for severity, escalation and false-positive scoring. If Jev is unreachable or slow, falls back to rule-based severity. The deterministic rules always win for critical conditions.
5. **Local alerts (ours):** operator console notifications; optional siren/relay hook.
6. **Evidence store (ours):** keeps clips/snapshots with SHA-256 hashes; encrypted at rest.
7. **Sync queue (ours):** store-and-forward of events and hashes to the command centre when the WAN is up; no duplicates after reconnect; original timestamps preserved.

### Zone C — Regional / national command centre
1. **Operator dashboard (ours):** alert queue ranked by severity, live/recorded clip view, acknowledge → verify/reject → escalate workflow, map of cameras and alerts, evidence verification view.
2. **Event store & search (ours):** all synced events searchable by time, camera, type, plate, severity.
3. **C2 / GIS integration (ours):** open REST + WebSocket (and optionally MQTT) so existing command systems can consume alerts.
Edge-to-centre links use mTLS (4G/satellite in the real deployment).

### Trust Layer (cross-cutting)
- Hyperledger Fabric network with peers representing BOP, regional and national nodes (for the demo, a small local Fabric test network is enough).
- Anchored on-chain: event hash, evidence clip hash, evidence export, incident status changes, rule configuration changes, model version deployments.
- Never on-chain: video, images, face data, plate images, personal data.
- A "verify evidence" feature recomputes a clip's hash and checks it against the ledger to show it is untampered. **This is a key demo moment.**

---

## 4. Analytics and rules (functional detail)

| Capability | How it is delivered |
|---|---|
| Human detection & tracking | Frigate person detection + tracking IDs; tracking ID is never treated as a confirmed identity |
| Vehicle detection & classification | Frigate vehicle classes (car, motorcycle, bus, truck, etc.) |
| Face detection | Frigate face detection; recognition only against an authorised watchlist, off by default, human-verified |
| ANPR | Frigate LPR; plates normalised to Indian formats; low-confidence reads flagged for review |
| Virtual fence intrusion | Ours: zones and directional tripwires per camera; alert when a person/vehicle crosses in the forbidden direction or enters a restricted zone |
| Suspicious activity | Ours, as explainable rules: loitering (dwell time in zone), repeated approach and retreat, wrong-direction movement, vehicle stopping in a sensitive area, group forming in a restricted zone |
| Night-time movement | Ours: schedule-based night window (or sunrise/sunset); any person/vehicle in configured zones at night raises an alert with higher sensitivity |
| Real-time alerts & logging | Ours: every event stored and logged; alerts pushed live to the dashboard |

Each rule is configurable per camera: object type, zone, schedule, minimum confidence, dwell time, direction, severity, cooldown (to stop alert floods).

Severity levels: Informational, Low, Medium, High, Critical.

Alert lifecycle: Generated → Delivered → Acknowledged → Verified or Rejected → Escalated or Closed. Every transition is logged, and the important ones are hashed to the ledger.

### Event record — fields every IBVAP event should carry
event id; site (BOP) id; camera id; event type; severity; timestamp (UTC); object type; tracking id; detection confidence; zone id; direction; snapshot reference; clip reference; plate text (if any); model/rule versions; Jev decision + confidence (if available); decision source (Jev or rules fallback); status; evidence hash; ledger transaction id; sync status.

---

## 5. Technology stack (decided unless noted)

| Layer | Choice |
|---|---|
| Camera & detection | Frigate (Docker), its detectors and face/LPR enrichments |
| Messaging | MQTT (Frigate's event bus; Mosquitto broker) |
| IBVAP backend | Python, FastAPI |
| Database | PostgreSQL (PostGIS optional for maps); SQLite acceptable at the edge for the demo |
| Evidence storage | Local disk at the edge; MinIO/S3-compatible at the centre (optional) |
| Decision layer | Jev System One model via TypeSafe AI API (docs.typesafe.ai) |
| Blockchain | Hyperledger Fabric (test network for demo) |
| Dashboard | React + TypeScript, WebSocket for live alerts, MapLibre for map |
| Deployment | Docker Compose for the whole stack |
| Edge hardware (target) | NVIDIA Jetson Orin or x86 mini PC; dev on laptops |

---

## 6. Proposed repository layout (folders only)

- `frigate/` — Frigate configuration (cameras, zones, detectors, enrichments)
- `ibvap-core/` — our backend: MQTT listener, rules engine, Jev client with fallback, evidence/hash service, sync queue, REST/WebSocket API
- `trust-layer/` — Hyperledger Fabric network setup and chaincode for anchoring hashes
- `dashboard/` — React operator dashboard
- `deploy/` — Docker Compose files, environment templates
- `docs/` — architecture notes, demo script, licences of third-party components
- `samples/` — test videos for demo scenarios (only footage we have rights to use)

---

## 7. MVP scope and milestones

### Must-have for the demo (MVP)
1. Frigate running on 2–3 camera streams (phone/webcam/test video), detecting people and vehicles.
2. IBVAP rules engine: virtual fence/tripwire with direction, night-time rule, loitering.
3. ANPR reads shown on vehicle events.
4. Face detection shown (recognition optional, behind an "authorised" toggle).
5. Jev triage on each event, with visible fallback when the network is cut.
6. Evidence hashing + Fabric anchoring + "verify evidence" button that detects a tampered clip.
7. Dashboard: ranked live alert queue, clip/snapshot view, acknowledge/verify/escalate, simple map.
8. Offline demo: unplug network → alerts continue locally → reconnect → events sync.

### Nice-to-have
Cross-camera search by plate; role-based login (operator / supervisor / auditor); simple analytics charts; siren/relay trigger; export evidence package.

### Out of scope
Training our own detection models from scratch; autonomous enforcement decisions; national-scale deployment.

### Suggested order of work
1. Docker Compose with Frigate + MQTT + test streams.
2. ibvap-core: consume Frigate events, store events, basic REST/WebSocket.
3. Rules engine (fence, direction, night, loitering).
4. Dashboard alert queue and clip view.
5. Evidence hashing, then Fabric anchoring and verification.
6. Jev integration with fallback.
7. Offline/sync behaviour.
8. Polish, demo script, README with architecture and licences.

---

## 8. Demo scenarios to support
1. Person crosses the virtual fence at night → Critical alert in under 2 s, clip saved, hash on ledger.
2. Unknown vehicle stops on a BOP road → ANPR read shown, High alert.
3. Animal or swaying foliage → Jev marks it likely false positive and merges it, showing fewer, better alerts.
4. Network cut → alerts continue at the BOP (rules-only), then sync when restored.
5. Someone edits a stored clip → "verify evidence" shows a hash mismatch against the ledger.

---

## 9. Non-functional requirements and guardrails
- **Human in the loop:** the system recommends; humans decide. No automated enforcement.
- **Privacy:** recognition off by default; watchlist changes are logged; faces blurred in general views where feasible; minimal retention.
- **Security:** no secrets or credentials committed (use environment files excluded from git); mTLS between edge and centre in the design; least-privilege roles.
- **Jev data rule:** send only text/JSON event descriptions to Jev. Never send frames, faces or plate images.
- **Reliability:** edge keeps working without internet; the rules engine never depends on Jev being available.
- **Explainability:** every alert shows why it fired (rule, zone, confidence, Jev reasoning/score).
- **Performance:** target < 2 s from frame to alert at the edge; measure and record real numbers for the final presentation.

---

## 10. Working conventions for Claude Code
- Keep the deck's claims true: if something we said (offline mode, < 2 s, ledger verification) is not working, flag it rather than faking it.
- Prefer small, reviewable changes; explain which zone/component a change belongs to.
- Write clear README sections as features land; credit Frigate, supervision, Hyperledger Fabric and Jev.
- Ask before adding a new major dependency or changing a decided technology.
- Use realistic but fictional data in demos (no real people's faces or real number plates).

---

## 11. Key references
- Frigate docs: docs.frigate.video · licence: MIT
- Roboflow supervision: github.com/roboflow/supervision · licence: MIT
- Hyperledger Fabric: hyperledger-fabric.readthedocs.io
- Jev / TypeSafe AI: typesafe.ai/blog/introducing-system-one-models-and-jev · docs.typesafe.ai
- ONVIF Profile S: onvif.org/profiles/profile-s
- ByteTrack (tracking, background): arxiv.org/abs/2110.06864
- Zero-DCE (low-light, background): arxiv.org/abs/2001.06826
- Digital Personal Data Protection Act 2023 (MeitY)
- Bharatiya Sakshya Adhiniyam 2023, Sec. 63 (electronic records as evidence)
