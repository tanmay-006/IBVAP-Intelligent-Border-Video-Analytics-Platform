import { describe, expect, it } from "vitest";
import { applyMessage, availableActions, buildQueue, highestOpenSeverity, timeAgo, type EventMap } from "./alerts";
import type { IbvapEvent } from "./types";

function ev(id: string, over: Partial<IbvapEvent> = {}): IbvapEvent {
  return {
    schema_version: "1.0.0",
    event_id: id,
    site_id: "BOP-TEST",
    camera_id: "cam-1",
    event_type: "tripwire_crossing",
    severity: "medium",
    timestamp: "2026-10-09T10:00:00Z",
    object_type: "person",
    tracking_id: "t",
    detection_confidence: 0.9,
    zone_id: null,
    direction: null,
    snapshot_ref: null,
    clip_ref: null,
    plate_text: null,
    plate_confidence: null,
    plate_needs_review: false,
    versions: { model: null, rule_id: "r", rule_version: "v" },
    explanation: { summary: "s", parameters: {} },
    jev_decision: null,
    decision_source: "rules_fallback",
    status: "delivered",
    evidence_hash: null,
    ledger_tx_id: null,
    sync_status: "pending",
    ...over,
  };
}

const opts = { showDetections: false, showClosed: false, cameraId: null };

describe("buildQueue", () => {
  const events: EventMap = {
    a: ev("a", { severity: "high", timestamp: "2026-10-09T10:00:00Z" }),
    b: ev("b", { severity: "critical", timestamp: "2026-10-09T09:00:00Z" }),
    c: ev("c", { severity: "high", timestamp: "2026-10-09T11:00:00Z" }),
    d: ev("d", { event_type: "detection", severity: "informational" }),
    e: ev("e", { severity: "critical", status: "closed" }),
    f: ev("f", { severity: "low", camera_id: "cam-2" }),
  };

  it("ranks by severity, then newest first", () => {
    expect(buildQueue(events, opts).map((e) => e.event_id)).toEqual(["b", "c", "a", "f"]);
  });

  it("hides raw detections and closed alerts unless asked", () => {
    const ids = buildQueue(events, { ...opts, showDetections: true, showClosed: true }).map((e) => e.event_id);
    expect(ids).toContain("d");
    expect(ids).toContain("e");
  });

  it("filters by camera", () => {
    expect(buildQueue(events, { ...opts, cameraId: "cam-2" }).map((e) => e.event_id)).toEqual(["f"]);
  });
});

describe("applyMessage", () => {
  it("merges a snapshot and replaces updated events", () => {
    let state = applyMessage({}, { type: "snapshot", events: [ev("a"), ev("b")] });
    state = applyMessage(state, { type: "event.updated", event: ev("a", { status: "acknowledged" }) });
    expect(Object.keys(state).sort()).toEqual(["a", "b"]);
    expect(state.a.status).toBe("acknowledged");
  });
});

describe("lifecycle", () => {
  it("offers only the actions the backend allows", () => {
    expect(availableActions("delivered")).toEqual(["ack"]);
    expect(availableActions("acknowledged")).toEqual(["verify", "reject"]);
    expect(availableActions("verified")).toEqual(["escalate", "close"]);
    expect(availableActions("closed")).toEqual([]);
  });
});

describe("helpers", () => {
  it("picks the worst open severity per camera, ignoring detections and closed", () => {
    const list = [
      ev("a", { severity: "medium" }),
      ev("b", { severity: "critical", status: "rejected" }),
      ev("c", { severity: "high", event_type: "detection" }),
    ];
    expect(highestOpenSeverity(list, "cam-1")).toBe("medium");
    expect(highestOpenSeverity(list, "cam-9")).toBeNull();
  });

  it("formats relative time", () => {
    const now = Date.parse("2026-10-09T10:05:00Z");
    expect(timeAgo("2026-10-09T10:04:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-10-09T10:00:00Z", now)).toBe("5 min ago");
  });
});
