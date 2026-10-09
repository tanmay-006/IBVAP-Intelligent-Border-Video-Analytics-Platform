import type { AlertStatus, EventType, IbvapEvent, Severity, StreamMessage } from "./types";

export const SEVERITY_RANK: Record<Severity, number> = {
  informational: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  informational: "Info",
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const EVENT_LABEL: Record<EventType, string> = {
  detection: "Detection",
  tripwire_crossing: "Fence crossing",
  restricted_zone_entry: "Restricted zone entry",
  night_movement: "Night movement",
  loitering: "Loitering",
  vehicle_stopped: "Vehicle stopped",
  approach_retreat: "Approach and retreat",
  wrong_direction: "Wrong direction",
  group_forming: "Group forming",
  plate_read: "Plate read",
  face_detected: "Face detected",
  camera_health: "Camera health",
};

export const STATUS_LABEL: Record<AlertStatus, string> = {
  generated: "New",
  delivered: "New",
  acknowledged: "Acknowledged",
  verified: "Verified",
  rejected: "Rejected",
  escalated: "Escalated",
  closed: "Closed",
};

export type Action = "ack" | "verify" | "reject" | "escalate" | "close";

export const ACTION_LABEL: Record<Action, string> = {
  ack: "Acknowledge",
  verify: "Verify",
  reject: "Reject as false alarm",
  escalate: "Escalate",
  close: "Close",
};

// Same lifecycle the backend enforces; the backend remains the authority.
export function availableActions(status: AlertStatus): Action[] {
  switch (status) {
    case "generated":
    case "delivered":
      return ["ack"];
    case "acknowledged":
      return ["verify", "reject"];
    case "verified":
      return ["escalate", "close"];
    case "rejected":
    case "escalated":
      return ["close"];
    case "closed":
      return [];
  }
}

export function isOpen(status: AlertStatus): boolean {
  return status !== "closed" && status !== "rejected";
}

export function needsAttention(status: AlertStatus): boolean {
  return status === "generated" || status === "delivered";
}

export type EventMap = Record<string, IbvapEvent>;

export function applyMessage(events: EventMap, msg: StreamMessage): EventMap {
  if (msg.type === "snapshot") {
    const next = { ...events };
    for (const e of msg.events) next[e.event_id] = e;
    return next;
  }
  return { ...events, [msg.event.event_id]: msg.event };
}

export interface QueueOptions {
  showDetections: boolean;
  showClosed: boolean;
  cameraId: string | null;
}

export function buildQueue(events: EventMap, opts: QueueOptions): IbvapEvent[] {
  return Object.values(events)
    .filter((e) => opts.showDetections || e.event_type !== "detection")
    .filter((e) => opts.showClosed || isOpen(e.status))
    .filter((e) => !opts.cameraId || e.camera_id === opts.cameraId)
    .sort(
      (a, b) =>
        SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] ||
        Date.parse(b.timestamp) - Date.parse(a.timestamp),
    );
}

export function highestOpenSeverity(events: IbvapEvent[], cameraId: string): Severity | null {
  let best: Severity | null = null;
  for (const e of events) {
    if (e.camera_id !== cameraId || e.event_type === "detection" || !isOpen(e.status)) continue;
    if (best === null || SEVERITY_RANK[e.severity] > SEVERITY_RANK[best]) best = e.severity;
  }
  return best;
}

const istTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const istDateTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export function formatIstTime(iso: string | Date): string {
  return istTime.format(typeof iso === "string" ? new Date(iso) : iso);
}

export function formatIstDateTime(iso: string): string {
  return `${istDateTime.format(new Date(iso))} IST`;
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function humanize(key: string): string {
  const s = key.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** Config names like `border_fence` read better as words in the console. */
export function readable(text: string): string {
  return text.replace(/_/g, " ");
}
