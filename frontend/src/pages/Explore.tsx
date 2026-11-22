import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { Map as LMap } from "leaflet";
import { api, tileUrl } from "../api";
import type { Acquisition, Defaults, RunSummary } from "../types";
import SwipeMap, { type Mode } from "../components/SwipeMap";
import { ErrorBox, Note, Spinner } from "../components/ui";

const PRESETS: [string, string, number][] = [["7", "1 week", 7], ["20", "20 days", 20], ["30", "1 month", 30], ["90", "3 months", 91], ["180", "6 months", 182], ["custom", "Custom", 0]];
const SENSORS: [string, string][] = [["radar", "Radar (Sentinel-1), false colour"], ["radar_vv", "Radar (Sentinel-1), grey"], ["optical", "Optical (Sentinel-2), true colour"]];
const iso = (d: Date) => d.toISOString().slice(0, 10);
const minus = (day: string, n: number) => iso(new Date(Date.parse(day) - n * 864e5));
const nice = (day: string) => new Date(day).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

function areaKm2(b: number[]) {
  const lat = ((b[1] + b[3]) / 2) * (Math.PI / 180);
  return (b[2] - b[0]) * 111.32 * Math.cos(lat) * (b[3] - b[1]) * 110.57;
}

export default function Explore() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [d, setD] = useState<Defaults | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [sensor, setSensor] = useState("radar");
  const [dateB, setDateB] = useState(iso(new Date()));
  const [preset, setPreset] = useState("7");
  const [customA, setCustomA] = useState(minus(iso(new Date()), 45));
  const [window_, setWindow] = useState(6);
  const [cloud, setCloud] = useState(30);
  const [mode, setMode] = useState<Mode>("swipe");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [overlayId, setOverlayId] = useState(params.get("run") ?? "");
  const [polys, setPolys] = useState<GeoJSON.FeatureCollection | null>(null);
  const [showPolys, setShowPolys] = useState(true);
  const [view, setView] = useState<number[] | null>(null);
  const [acqA, setAcqA] = useState<Acquisition[] | null>(null);
  const [acqB, setAcqB] = useState<Acquisition[] | null>(null);
  const [acqErr, setAcqErr] = useState("");
  const [cid, setCid] = useState(""); const [sec, setSec] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [simulate, setSimulate] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  const dateA = preset === "custom" ? customA : minus(dateB, PRESETS.find((p) => p[0] === preset)![2]);
  const overlay = runs.find((r) => r.id === overlayId);

  useEffect(() => {
    api.defaults().then(setD);
    api.credentials().then((c) => setConnected(c.connected));
    api.runs().then((r) => setRuns(r.filter((x) => x.metrics)));
  }, []);
  useEffect(() => { setWindow(sensor === "optical" ? 10 : 6); }, [sensor]);
  useEffect(() => {
    if (!overlayId) { setPolys(null); return; }
    api.polygons(overlayId).then(setPolys);
  }, [overlayId]);

  const onView = useCallback((m: LMap) => {
    const b = m.getBounds();
    setView([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
  }, []);

  // which images actually exist for each side (public catalogue)
  useEffect(() => {
    if (!view) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setAcqErr(""); setAcqA(null); setAcqB(null);
      const s = sensor.startsWith("radar") ? "radar" : "optical";
      Promise.all([api.acquisitions(view, dateA, window_, s), api.acquisitions(view, dateB, window_, s)])
        .then(([a, b]) => { setAcqA(a); setAcqB(b); })
        .catch((e) => setAcqErr(e.message));
    }, 700);
  }, [view, dateA, dateB, window_, sensor]);

  const start = useMemo(() => {
    if (overlay) return { bounds: [[overlay.bbox[1], overlay.bbox[0]], [overlay.bbox[3], overlay.bbox[2]]] as [[number, number], [number, number]] };
    if (d) return { bounds: [[d.bbox[1], d.bbox[0]], [d.bbox[3], d.bbox[2]]] as [[number, number], [number, number]] };
    return null;
  }, [d, overlay?.id]); // eslint-disable-line

  if (!d || connected === null || !start) return <Spinner />;

  const left = connected ? { kind: "tiles" as const, url: tileUrl(sensor, dateA, window_, cloud), label: nice(dateA) } : { kind: "basemap" as const, label: nice(dateA) };
  const right = connected ? { kind: "tiles" as const, url: tileUrl(sensor, dateB, window_, cloud), label: nice(dateB) } : { kind: "basemap" as const, label: nice(dateB) };
  const viewKm2 = view ? areaKm2(view) : 0;

  async function connect() {
    setBusy(true); setErr("");
    try { await api.connect(cid, sec); setConnected(true); setCid(""); setSec(""); } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  }
  async function detect() {
    if (!view) return;
    setBusy(true); setErr("");
    try {
      const r = await api.quickCompare({ bbox: view, date_a: dateA, date_b: dateB, window_days: window_, source: simulate ? "synthetic" : "cdse" });
      nav(`/runs/${r.id}`);
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  }

  const acqText = (a: Acquisition[] | null) => {
    if (acqErr) return <span className="text-amber-700">catalogue not reachable</span>;
    if (!a) return <span className="text-slate-400">checking…</span>;
    if (!a.length) return <span className="text-red-700">no image in this window; widen it</span>;
    const x = a[0];
    return <span>newest: <b>{nice(x.date)}</b> · {x.satellite}{x.orbit ? ` · ${x.orbit}` : ""}{x.cloud != null ? ` · ${x.cloud}% cloud` : ""}{a.length > 1 ? ` (+${a.length - 1} more)` : ""}</span>;
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Explore imagery</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          View recent satellite imagery for any date and compare two dates. Sentinel-1 radar sees through cloud and passes about every
          6 days; Sentinel-2 optical passes about every 5 days but is often cloudy. Each side shows the newest image in the chosen
          window up to its date.
        </p>
      </div>

      {!connected && (
        <div className="card space-y-3 p-5">
          <div className="font-semibold text-slate-900">Connect Copernicus to load imagery</div>
          <p className="text-sm text-slate-600">Free account at dataspace.copernicus.eu → dashboard → OAuth clients. The key is kept in this server's memory only and is never written to disk.</p>
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <input className="input" placeholder="Client ID" value={cid} onChange={(e) => setCid(e.target.value)} autoComplete="off" />
            <input className="input" placeholder="Client secret" type="password" value={sec} onChange={(e) => setSec(e.target.value)} autoComplete="off" />
            <button className="btn-primary" disabled={busy || !cid || !sec} onClick={connect}>Connect</button>
          </div>
          {err && <ErrorBox msg={err} />}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <aside className="card space-y-5 p-4">
          <div>
            <label className="label">Imagery</label>
            <select className="input" value={sensor} onChange={(e) => setSensor(e.target.value)}>
              {SENSORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Latest date (right)</label>
            <input type="date" className="input" value={dateB} max={iso(new Date())} onChange={(e) => setDateB(e.target.value)} />
          </div>
          <div>
            <label className="label">Compare with (left)</label>
            <div className="grid grid-cols-3 gap-1.5">
              {PRESETS.map(([k, l]) => (
                <button key={k} type="button" onClick={() => setPreset(k)}
                  className={`rounded-md border px-2 py-1.5 text-xs font-medium ${preset === k ? "border-navy-700 bg-navy-700 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}>{l}</button>
              ))}
            </div>
            {preset === "custom" && <input type="date" className="input mt-2" value={customA} max={minus(dateB, 1)} onChange={(e) => setCustomA(e.target.value)} />}
            <p className="mt-1.5 text-xs text-slate-500">Left date: {nice(dateA)}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Window (days)</label>
              <input type="number" min={1} max={60} className="input" value={window_} onChange={(e) => setWindow(Math.max(1, Math.min(60, +e.target.value)))} />
            </div>
            {sensor === "optical" && (
              <div>
                <label className="label">Max cloud %</label>
                <input type="number" min={0} max={100} className="input" value={cloud} onChange={(e) => setCloud(+e.target.value)} />
              </div>
            )}
          </div>
          <div>
            <label className="label">View</label>
            <div className="flex overflow-hidden rounded-lg border border-slate-300 text-sm">
              {([["swipe", "Swipe"], ["side", "Side by side"], ["single", "Toggle"]] as const).map(([k, l]) => (
                <button key={k} type="button" onClick={() => setMode(k)} className={`flex-1 px-1 py-1.5 text-xs whitespace-nowrap ${mode === k ? "bg-navy-700 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}>{l}</button>
              ))}
            </div>
          </div>
          <div>
            <label className="label">Detections from an analysis</label>
            <select className="input" value={overlayId} onChange={(e) => setOverlayId(e.target.value)}>
              <option value="">None</option>
              {runs.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
            {overlayId && (
              <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={showPolys} onChange={(e) => setShowPolys(e.target.checked)} className="accent-navy-700" /> Show detection outlines
              </label>
            )}
          </div>
          <div className="border-t border-slate-100 pt-4">
            <div className="text-sm font-semibold text-slate-900">Detect changes in this view</div>
            <p className="mt-1 text-xs text-slate-500">
              Compares one radar image per date. Faster than a seasonal analysis, but one windy or wet image can cause false changes.
              View: {viewKm2.toLocaleString("en-IN", { maximumFractionDigits: 0 })} km² (limit {d.max_quick_km2.toLocaleString("en-IN")}).
            </p>
            <label className="mt-2 flex items-center gap-2 text-xs text-slate-600">
              <input type="checkbox" checked={simulate} onChange={(e) => setSimulate(e.target.checked)} className="accent-navy-700" /> Use simulated data (demo)
            </label>
            <button className="btn-primary mt-3 w-full" disabled={busy || !view || viewKm2 > d.max_quick_km2 || (!connected && !simulate)} onClick={detect}>
              {busy ? "Starting…" : viewKm2 > d.max_quick_km2 ? "Zoom in to detect" : `Detect: ${nice(dateA)} → ${nice(dateB)}`}
            </button>
            {err && connected && <div className="mt-2"><ErrorBox msg={err} /></div>}
          </div>
        </aside>

        <div className="space-y-2">
          <div className="grid gap-2 text-xs text-slate-600 md:grid-cols-2">
            <div className="card px-3 py-2"><b>Left · up to {nice(dateA)}</b> · {acqText(acqA)}</div>
            <div className="card px-3 py-2"><b>Right · up to {nice(dateB)}</b> · {acqText(acqB)}</div>
          </div>
          <SwipeMap left={left} right={right} mode={mode} polygons={polys} showPolygons={showPolys} bounds={start.bounds}
            outline={overlay ? [[overlay.bbox[1], overlay.bbox[0]], [overlay.bbox[3], overlay.bbox[2]]] : null}
            onView={onView} onSelect={(id) => overlayId && nav(`/runs/${overlayId}/alerts?alert=${id}`)} height="h-[640px]" />
          <p className="text-xs text-slate-500">
            Imagery: Contains modified Copernicus Sentinel data, processed on request by the Copernicus Data Space Ecosystem. Zoom in to
            level 8 or closer to load imagery. Radar false colour: red = VV, green = VH, blue = VV/VH; water is dark.
          </p>
          {!connected && <Note tone="warn">Imagery tiles stay empty until a Copernicus account is connected.</Note>}
        </div>
      </div>
    </div>
  );
}
