import { useEffect, useState } from "react";
import { formatIstTime } from "../alerts";
import type { Health } from "../types";
import type { StreamStatus } from "../useAlertStream";

const STREAM_TEXT: Record<StreamStatus, string> = {
  live: "Live",
  connecting: "Connecting",
  offline: "Console offline, retrying",
};

interface Props {
  health: Health | null;
  stream: StreamStatus;
  counts: { critical: number; high: number; waiting: number };
  view: "live" | "search";
  onView: (v: "live" | "search") => void;
}

export function Header({ health, stream, counts, view, onView }: Props) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const feed = !health
    ? { cls: "warn", text: "Backend unreachable" }
    : health.mqtt_connected
      ? { cls: "ok", text: "Camera feed connected" }
      : { cls: "warn", text: "Camera feed not connected" };

  return (
    <header className="topbar">
      <div className="brand">
        <span className="wordmark">IBVAP</span>
        <span className="site">{health?.site_name ?? "Operator console"}</span>
      </div>

      <nav className="views" aria-label="Views">
        <button aria-pressed={view === "live"} onClick={() => onView("live")}>
          Live alerts
        </button>
        <button aria-pressed={view === "search"} onClick={() => onView("search")}>
          Search events
        </button>
      </nav>

      <div className="tally" aria-label="Open alerts">
        <span className="tally-item sev-critical">
          <b>{counts.critical}</b> critical
        </span>
        <span className="tally-item sev-high">
          <b>{counts.high}</b> high
        </span>
        <span className="tally-item">
          <b>{counts.waiting}</b> awaiting acknowledgement
        </span>
      </div>

      <div className="status">
        <span className={`pill ${stream === "live" ? "ok" : "warn"}`}>{STREAM_TEXT[stream]}</span>
        <span className={`pill ${feed.cls}`}>{feed.text}</span>
        <time className="clock" dateTime={now.toISOString()}>
          {formatIstTime(now)} <small>IST</small>
        </time>
      </div>
    </header>
  );
}
