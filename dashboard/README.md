# dashboard/ — Zone C: SSB operator console

React + TypeScript console for BOP and command-centre operators. It talks only to ibvap-core (REST + the `/ws/alerts` WebSocket), never to Frigate or cameras directly.

- **Alert queue:** live over WebSocket, ranked by severity, then newest first. Raw detections and closed alerts are hidden unless switched on. A dot marks alerts nobody has acknowledged yet, and a critical alert flashes once when it arrives.
- **Alert detail:** snapshot and clip (proxied through ibvap-core), why the alert fired (rule, measured values, rules version, who decided), number plate with a low-confidence warning, and the lifecycle actions: Acknowledge → Verify or Reject → Escalate or Close. Every action needs the operator's name or service number and is shown in the history.
- **Camera map:** MapLibre, each camera coloured by its most severe open alert; clicking a camera filters the queue. The OpenStreetMap background needs internet; offline, the markers still show.
- **Search:** by camera, type, severity, number plate and time range. Link directly with `/ui/#search`.

Times are shown in IST. Fonts are bundled, so the console works with no internet at the BOP.

## Run

```bash
npm install
npm run build          # ibvap-core then serves it at http://127.0.0.1:8000/ui/
# or, while developing (hot reload, forwards API calls to ibvap-core on :8000):
npm run dev            # http://127.0.0.1:5173
```

Checks: `npm run typecheck`, `npm test`.

Operator names are free text until role-based login (Phase 9).
