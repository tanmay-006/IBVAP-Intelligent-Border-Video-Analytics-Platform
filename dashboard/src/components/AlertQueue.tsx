import { EVENT_LABEL, SEVERITY_LABEL, STATUS_LABEL, formatIstTime, needsAttention, readable, timeAgo } from "../alerts";
import type { Camera, IbvapEvent } from "../types";

interface Props {
  queue: IbvapEvent[];
  cameras: Record<string, Camera>;
  selectedId: string | null;
  fresh: Set<string>;
  onSelect: (id: string) => void;
  showDetections: boolean;
  showClosed: boolean;
  cameraFilter: string | null;
  onToggleDetections: () => void;
  onToggleClosed: () => void;
  onClearCamera: () => void;
  now: number;
}

export function AlertQueue(p: Props) {
  return (
    <section className="queue" aria-label="Alert queue">
      <div className="pane-head">
        <h2>Alert queue</h2>
        <div className="filters">
          <label>
            <input type="checkbox" checked={p.showClosed} onChange={p.onToggleClosed} /> Closed
          </label>
          <label>
            <input type="checkbox" checked={p.showDetections} onChange={p.onToggleDetections} /> Raw detections
          </label>
        </div>
      </div>
      {p.cameraFilter && (
        <button className="chip" onClick={p.onClearCamera}>
          Only {p.cameras[p.cameraFilter]?.name ?? p.cameraFilter}. Show all cameras
        </button>
      )}

      {p.queue.length === 0 ? (
        <p className="empty">
          No open alerts. New alerts appear here as soon as a rule fires, most severe first.
        </p>
      ) : (
        <ol className="rows">
          {p.queue.map((e) => (
            <li key={e.event_id}>
              <button
                className={[
                  "row",
                  `sev-${e.severity}`,
                  p.selectedId === e.event_id ? "selected" : "",
                  p.fresh.has(e.event_id) ? "fresh" : "",
                  needsAttention(e.status) ? "unacked" : "",
                ].join(" ")}
                onClick={() => p.onSelect(e.event_id)}
                aria-current={p.selectedId === e.event_id}
              >
                <span className="band" aria-hidden="true" />
                <span className="row-main">
                  <span className="row-title">{EVENT_LABEL[e.event_type]}</span>
                  <span className="row-sub">
                    {p.cameras[e.camera_id]?.name ?? e.camera_id}
                    {e.zone_id ? `, ${e.zone_id.replace(/_/g, " ")}` : ""}
                  </span>
                  <span className="row-why">{e.explanation ? readable(e.explanation.summary) : ""}</span>
                </span>
                <span className="row-meta">
                  <span className="sev-text">{SEVERITY_LABEL[e.severity]}</span>
                  <time dateTime={e.timestamp} title={formatIstTime(e.timestamp) + " IST"}>
                    {timeAgo(e.timestamp, p.now)}
                  </time>
                  <span className="status-text">{STATUS_LABEL[e.status]}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
