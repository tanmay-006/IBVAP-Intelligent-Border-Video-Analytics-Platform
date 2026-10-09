import { useEffect, useState } from "react";
import { formatIstTime } from "../alerts";
import type { Theme } from "../theme";
import type { Health } from "../types";
import type { StreamStatus } from "../useAlertStream";

const STREAM_TEXT: Record<StreamStatus, string> = {
  live: "Console live",
  connecting: "Connecting",
  offline: "Console offline, retrying",
};

interface Props {
  health: Health | null;
  stream: StreamStatus;
  counts: { critical: number; high: number; waiting: number };
  view: "live" | "search";
  onView: (v: "live" | "search") => void;
  theme: Theme;
  onToggleTheme: () => void;
}

function ThemeIcon({ theme }: { theme: Theme }) {
  // Shows the theme you will switch to.
  return theme === "dark" ? (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <circle cx="12" cy="12" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

export function Header({ health, stream, counts, view, onView, theme, onToggleTheme }: Props) {
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
        <span className="tally-item sev-critical" data-zero={counts.critical === 0}>
          <b>{counts.critical}</b> critical
        </span>
        <span className="tally-item sev-high" data-zero={counts.high === 0}>
          <b>{counts.high}</b> high
        </span>
        <span className="tally-item">
          <b>{counts.waiting}</b> to acknowledge
        </span>
      </div>

      <div className="status">
        <span className={`pill ${stream === "live" ? "ok" : "warn"}`}>{STREAM_TEXT[stream]}</span>
        <span className={`pill ${feed.cls}`}>{feed.text}</span>
        <time className="clock" dateTime={now.toISOString()}>
          {formatIstTime(now)} <small>IST</small>
        </time>
        <button
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={theme === "dark" ? "Light theme" : "Dark theme"}
        >
          <ThemeIcon theme={theme} />
        </button>
      </div>
    </header>
  );
}
