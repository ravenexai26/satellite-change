import type { Acquisition, Alert, Defaults, RunDetail, RunSummary, Scene, Threshold, VRow, Validation } from "./types";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch { /* keep status text */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  defaults: () => req<Defaults>("/api/defaults"),
  runs: () => req<RunSummary[]>("/api/runs"),
  run: (id: string) => req<RunDetail>(`/api/runs/${id}`),
  create: (body: unknown) => req<RunSummary>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
  stop: (id: string) => req<{ ok: boolean }>(`/api/runs/${id}/stop`, { method: "POST" }),
  log: (id: string) => req<{ file: string; lines: string[] }[]>(`/api/runs/${id}/log`),
  scenes: (id: string) => req<Scene[]>(`/api/runs/${id}/scenes`),
  thresholds: (id: string) => req<Threshold[]>(`/api/runs/${id}/thresholds`),
  alerts: (id: string) => req<Alert[]>(`/api/runs/${id}/alerts`),
  statuses: () => req<Record<string, string>>("/api/review-statuses"),
  review: (id: string, aid: string, body: { status: string; actor: string; note: string }) =>
    req<Alert>(`/api/runs/${id}/alerts/${aid}/review`, { method: "POST", body: JSON.stringify(body) }),
  polygons: (id: string) => req<GeoJSON.FeatureCollection>(`/api/runs/${id}/polygons`),
  layers: (id: string) => req<{ bounds: [[number, number], [number, number]] | null; layers: string[] }>(`/api/runs/${id}/layers`),
  validation: (id: string) => req<{ rows: VRow[]; sheets: string[]; result: Validation }>(`/api/runs/${id}/validation`),
  saveLabels: (id: string, labels: Record<string, { label: string; notes: string }>) =>
    req<Validation["manual"]>(`/api/runs/${id}/validation`, { method: "PUT", body: JSON.stringify({ labels }) }),
  method: () => req<Record<string, string>>("/api/method"),
  credentials: () => req<{ connected: boolean; from_environment: boolean }>("/api/credentials"),
  connect: (client_id: string, client_secret: string) =>
    req<{ connected: boolean }>("/api/credentials", { method: "POST", body: JSON.stringify({ client_id, client_secret }) }),
  disconnect: () => req<{ connected: boolean }>("/api/credentials", { method: "DELETE" }),
  acquisitions: (bbox: number[], day: string, window: number, sensor: string) =>
    req<Acquisition[]>(`/api/acquisitions?bbox=${bbox.map((v) => v.toFixed(4)).join(",")}&day=${day}&window=${window}&sensor=${sensor}`),
  quickCompare: (body: unknown) => req<RunSummary>("/api/quick-compare", { method: "POST", body: JSON.stringify(body) }),
};

export const fileUrl = (id: string, rel: string) => `/api/runs/${id}/files/${rel}`;

export const tileUrl = (sensor: string, day: string, window: number, cloud = 30) =>
  `/api/tiles/${sensor}/${day}/{z}/{x}/{y}.png?window=${window}&cloud=${cloud}`;
