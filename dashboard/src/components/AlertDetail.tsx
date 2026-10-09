import { useEffect, useState, type ReactNode } from "react";
import {
  ACTION_LABEL,
  EVENT_LABEL,
  SEVERITY_LABEL,
  STATUS_LABEL,
  availableActions,
  formatIstDateTime,
  humanize,
  readable,
  type Action,
} from "../alerts";
import { api, mediaUrl } from "../api";
import type { AuditEntry, Camera, IbvapEvent } from "../types";

const OPERATOR_KEY = "ibvap.operator";

function readOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) ?? "";
  } catch {
    return "";
  }
}

// Parameters already shown elsewhere in the panel.
const HIDDEN_PARAMS = new Set(["rule_type", "frigate_event_id", "frigate_label", "from", "to", "zones"]);

function formatParam(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number" && key.includes("confidence")) return `${Math.round(value * 100)}%`;
  if (typeof value === "string") return readable(value);
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}

function decisionText(e: IbvapEvent): string {
  if (e.decision_source === "jev" && e.jev_decision) {
    return `Jev triage, ${Math.round(e.jev_decision.confidence * 100)}% confidence`;
  }
  if (e.decision_source === "rules_override") return "Border rule (kept over Jev for a critical condition)";
  return "Border rule only (Jev triage not connected)";
}

interface Props {
  event: IbvapEvent | null;
  camera: Camera | undefined;
  onUpdated: (e: IbvapEvent) => void;
}

export function AlertDetail({ event, camera, onUpdated }: Props) {
  const [operator, setOperator] = useState(readOperator);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [snapshotFailed, setSnapshotFailed] = useState(false);
  const [showClip, setShowClip] = useState(false);

  const id = event?.event_id;
  const status = event?.status;
  useEffect(() => {
    setNote("");
    setError(null);
    setSnapshotFailed(false);
    setShowClip(false);
  }, [id]);
  useEffect(() => {
    if (!id) return;
    api.audit(id).then(setAudit).catch(() => setAudit([]));
  }, [id, status]);

  if (!event) {
    return (
      <section className="detail empty-detail" aria-label="Alert detail">
        <p>Select an alert to see the evidence, why it fired, and what to do next.</p>
      </section>
    );
  }

  const act = async (action: Action) => {
    if (!operator.trim()) {
      setError("Enter your name or service number first, so the action is recorded against you.");
      return;
    }
    setBusy(action);
    setError(null);
    try {
      const updated = await api.transition(event.event_id, action, operator.trim(), note.trim());
      onUpdated(updated);
      setNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const saveOperator = (value: string) => {
    setOperator(value);
    try {
      localStorage.setItem(OPERATOR_KEY, value);
    } catch {
      // storage unavailable; keep it for this session only
    }
  };

  const params = Object.entries(event.explanation?.parameters ?? {}).filter(([k]) => !HIDDEN_PARAMS.has(k));
  const actions = availableActions(event.status);

  const rows: [string, ReactNode][] = [];
  if (event.object_type) rows.push(["Object", humanize(event.object_type)]);
  if (event.detection_confidence !== null)
    rows.push(["Detection confidence", `${Math.round(event.detection_confidence * 100)}%`]);
  if (event.direction) rows.push(["Direction", humanize(event.direction)]);
  if (event.zone_id) rows.push(["Zone", event.zone_id.replace(/_/g, " ")]);
  if (event.plate_text)
    rows.push([
      "Number plate",
      <>
        <span className="plate">{event.plate_text}</span>
        {event.plate_needs_review && (
          <span className="review">
            Low confidence ({Math.round((event.plate_confidence ?? 0) * 100)}%), check against the clip
          </span>
        )}
      </>,
    ]);
  for (const [k, v] of params) rows.push([humanize(k), formatParam(k, v)]);
  if (event.versions.rule_id)
    rows.push([
      "Rule",
      <>
        {event.versions.rule_id} <small>(rules version {event.versions.rule_version})</small>
      </>,
    ]);
  rows.push(["Decided by", decisionText(event)]);
  if (event.tracking_id)
    rows.push(["Track", <small>{event.tracking_id} (a tracking number, not an identity)</small>]);

  return (
    <section className={`detail sev-${event.severity}`} aria-label="Alert detail">
      <header className="detail-head">
        <span className="sev-badge">{SEVERITY_LABEL[event.severity]}</span>
        <h2>{EVENT_LABEL[event.event_type]}</h2>
        <p className="detail-where">
          {camera?.name ?? event.camera_id} at {formatIstDateTime(event.timestamp)}
        </p>
        <p className="detail-status">Status: {STATUS_LABEL[event.status]}</p>
      </header>

      <div className="evidence">
        {event.snapshot_ref && !snapshotFailed ? (
          <img
            src={mediaUrl(event.event_id, "snapshot")}
            alt={`Snapshot of ${event.object_type ?? "object"} on ${camera?.name ?? event.camera_id}`}
            onError={() => setSnapshotFailed(true)}
          />
        ) : (
          <div className="no-media">
            {event.snapshot_ref
              ? "Snapshot could not be loaded. Check that Frigate is running at the BOP."
              : "No snapshot was recorded for this event."}
          </div>
        )}
        {event.clip_ref &&
          (showClip ? (
            <video src={mediaUrl(event.event_id, "clip")} controls autoPlay />
          ) : (
            <button className="secondary" onClick={() => setShowClip(true)}>
              Play clip
            </button>
          ))}
      </div>

      <div className="why">
        <h3>Why this alert fired</h3>
        <p className="why-summary">{event.explanation ? readable(event.explanation.summary) : "No explanation recorded."}</p>
        <dl>
          {rows.map(([label, value]) => (
            <div key={label} className="dl-row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="act">
        <h3>Your decision</h3>
        {actions.length === 0 ? (
          <p className="muted">This alert is closed. No further action is possible.</p>
        ) : (
          <>
            <div className="act-fields">
              <label>
                Your name or service number
                <input value={operator} onChange={(e) => saveOperator(e.target.value)} autoComplete="name" />
              </label>
              <label>
                Note (optional)
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} />
              </label>
            </div>
            <div className="act-buttons">
              {actions.map((a) => (
                <button
                  key={a}
                  className={a === "reject" || a === "close" ? "secondary" : "primary"}
                  disabled={busy !== null}
                  onClick={() => act(a)}
                >
                  {busy === a ? `${ACTION_LABEL[a]}…` : ACTION_LABEL[a]}
                </button>
              ))}
            </div>
          </>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="audit">
        <h3>History</h3>
        {audit.length === 0 ? (
          <p className="muted">No actions yet.</p>
        ) : (
          <ol>
            {audit.map((a, i) => (
              <li key={i}>
                <time dateTime={a.at}>{formatIstDateTime(a.at)}</time>
                <span>
                  {STATUS_LABEL[a.to_status] === STATUS_LABEL[a.from_status]
                    ? "Shown on console"
                    : STATUS_LABEL[a.to_status]}{" "}
                  by {a.actor === "system:ws" || a.actor === "system" ? "system" : a.actor}
                </span>
                {a.note && <q>{a.note}</q>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
