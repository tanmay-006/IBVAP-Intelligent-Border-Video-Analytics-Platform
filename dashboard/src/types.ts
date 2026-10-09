// Mirrors the IBVAP event record (docs/schemas/ibvap-event.schema.json).

export type Severity = "informational" | "low" | "medium" | "high" | "critical";

export type AlertStatus =
  | "generated"
  | "delivered"
  | "acknowledged"
  | "verified"
  | "rejected"
  | "escalated"
  | "closed";

export type EventType =
  | "detection"
  | "tripwire_crossing"
  | "restricted_zone_entry"
  | "night_movement"
  | "loitering"
  | "vehicle_stopped"
  | "approach_retreat"
  | "wrong_direction"
  | "group_forming"
  | "plate_read"
  | "face_detected"
  | "camera_health";

export interface JevDecision {
  severity: Severity;
  escalate: boolean;
  false_positive_likelihood: number;
  confidence: number;
  reasoning: string | null;
  latency_ms: number | null;
}

export interface IbvapEvent {
  schema_version: string;
  event_id: string;
  site_id: string;
  camera_id: string;
  event_type: EventType;
  severity: Severity;
  timestamp: string;
  object_type: string | null;
  tracking_id: string | null;
  detection_confidence: number | null;
  zone_id: string | null;
  direction: "inbound" | "outbound" | "along" | "unknown" | null;
  snapshot_ref: string | null;
  clip_ref: string | null;
  plate_text: string | null;
  plate_confidence: number | null;
  plate_needs_review: boolean;
  versions: { model: string | null; rule_id: string | null; rule_version: string | null };
  explanation: { summary: string; parameters: Record<string, unknown> } | null;
  jev_decision: JevDecision | null;
  decision_source: "jev" | "rules_fallback" | "rules_override";
  status: AlertStatus;
  evidence_hash: string | null;
  ledger_tx_id: string | null;
  sync_status: "pending" | "synced" | "failed";
}

export interface Camera {
  camera_id: string;
  name: string;
  lat: number | null;
  lon: number | null;
  live_url: string | null;
  last_event_at: string | null;
}

export interface Health {
  status: string;
  site_id: string;
  site_name: string;
  rules_version: string | null;
  mqtt_enabled: boolean;
  mqtt_connected: boolean;
  ws_clients: number;
}

export interface AuditEntry {
  from_status: AlertStatus;
  to_status: AlertStatus;
  actor: string;
  note: string | null;
  at: string;
}

export type StreamMessage =
  | { type: "snapshot"; events: IbvapEvent[] }
  | { type: "event.created" | "event.updated"; event: IbvapEvent };
