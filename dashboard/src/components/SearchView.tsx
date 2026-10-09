import { useState, type FormEvent } from "react";
import { EVENT_LABEL, SEVERITY_LABEL, STATUS_LABEL, formatIstDateTime } from "../alerts";
import { api } from "../api";
import type { Camera, EventType, IbvapEvent, Severity } from "../types";

interface Props {
  cameras: Camera[];
  onOpen: (e: IbvapEvent) => void;
}

const TYPES = Object.keys(EVENT_LABEL) as EventType[];
const SEVERITIES = Object.keys(SEVERITY_LABEL) as Severity[];

export function SearchView({ cameras, onOpen }: Props) {
  const [form, setForm] = useState({ camera_id: "", event_type: "", severity: "", plate: "", since: "", until: "" });
  const [results, setResults] = useState<IbvapEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const search = async (ev: FormEvent) => {
    ev.preventDefault();
    const params: Record<string, string> = { limit: "200" };
    for (const [k, v] of Object.entries(form)) {
      if (!v) continue;
      // datetime-local values are in the browser's time zone; send them as UTC instants.
      params[k] = k === "since" || k === "until" ? new Date(v).toISOString() : v;
    }
    setLoading(true);
    setError(null);
    try {
      setResults(await api.search(params));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="search" aria-label="Search events">
      <form onSubmit={search} className="search-form">
        <label>
          Camera
          <select value={form.camera_id} onChange={set("camera_id")}>
            <option value="">All cameras</option>
            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select value={form.event_type} onChange={set("event_type")}>
            <option value="">All types</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {EVENT_LABEL[t]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Severity
          <select value={form.severity} onChange={set("severity")}>
            <option value="">Any severity</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {SEVERITY_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Number plate contains
          <input value={form.plate} onChange={set("plate")} placeholder="e.g. MH12" />
        </label>
        <label>
          From
          <input type="datetime-local" value={form.since} onChange={set("since")} />
        </label>
        <label>
          To
          <input type="datetime-local" value={form.until} onChange={set("until")} />
        </label>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {results !== null &&
        (results.length === 0 ? (
          <p className="empty">No events match these filters. Widen the time range or clear a filter.</p>
        ) : (
          <table className="results">
            <caption>{results.length === 200 ? "First 200 matches, newest first" : `${results.length} matches, newest first`}</caption>
            <thead>
              <tr>
                <th scope="col">Time (IST)</th>
                <th scope="col">Severity</th>
                <th scope="col">Type</th>
                <th scope="col">Camera</th>
                <th scope="col">Plate</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((e) => (
                <tr key={e.event_id} className={`sev-${e.severity}`}>
                  <td>
                    <button className="link" onClick={() => onOpen(e)}>
                      {formatIstDateTime(e.timestamp).replace(" IST", "")}
                    </button>
                  </td>
                  <td>
                    <span className="sev-text">{SEVERITY_LABEL[e.severity]}</span>
                  </td>
                  <td>{EVENT_LABEL[e.event_type]}</td>
                  <td>{cameras.find((c) => c.camera_id === e.camera_id)?.name ?? e.camera_id}</td>
                  <td>{e.plate_text ?? ""}</td>
                  <td>{STATUS_LABEL[e.status]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </section>
  );
}
