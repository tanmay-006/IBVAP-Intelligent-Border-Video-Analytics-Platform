import type { Action } from "./alerts";
import type { AuditEntry, Camera, Health, IbvapEvent } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the status text
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  cameras: () => request<Camera[]>("/cameras"),
  event: (id: string) => request<IbvapEvent>(`/events/${id}`),
  audit: (id: string) => request<AuditEntry[]>(`/events/${id}/audit`),
  search: (params: Record<string, string>) =>
    request<IbvapEvent[]>(`/events?${new URLSearchParams(params).toString()}`),
  transition: (id: string, action: Action, actor: string, note: string) =>
    request<IbvapEvent>(`/alerts/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ actor, note: note || null }),
    }),
};

export const mediaUrl = (id: string, kind: "snapshot" | "clip") => `/media/${id}/${kind}`;
