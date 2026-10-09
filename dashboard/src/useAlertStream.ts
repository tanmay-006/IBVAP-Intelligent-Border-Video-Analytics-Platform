import { useEffect, useReducer, useRef, useState } from "react";
import { applyMessage, type EventMap } from "./alerts";
import type { IbvapEvent, StreamMessage } from "./types";

export type StreamStatus = "connecting" | "live" | "offline";

type Action = StreamMessage | { type: "merge"; events: IbvapEvent[] };

function reducer(state: EventMap, action: Action): EventMap {
  if (action.type === "merge") return applyMessage(state, { type: "snapshot", events: action.events });
  return applyMessage(state, action);
}

/** Live alerts over /ws/alerts, reconnecting with backoff. `fresh` holds ids of critical alerts that just arrived. */
export function useAlertStream() {
  const [events, dispatch] = useReducer(reducer, {});
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const retry = useRef(1000);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = () => {
      setStatus("connecting");
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${scheme}://${location.host}/ws/alerts`);
      ws.onopen = () => {
        retry.current = 1000;
        setStatus("live");
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as StreamMessage;
        dispatch(msg);
        if (msg.type === "event.created" && msg.event.severity === "critical") {
          const id = msg.event.event_id;
          setFresh((s) => new Set(s).add(id));
          setTimeout(() => setFresh((s) => { const n = new Set(s); n.delete(id); return n; }), 4000);
        }
      };
      ws.onclose = () => {
        if (stopped) return;
        setStatus("offline");
        timer = setTimeout(connect, retry.current);
        retry.current = Math.min(retry.current * 2, 15000);
      };
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      ws?.close();
    };
  }, []);

  const merge = (list: IbvapEvent[]) => dispatch({ type: "merge", events: list });
  return { events, status, fresh, merge };
}
