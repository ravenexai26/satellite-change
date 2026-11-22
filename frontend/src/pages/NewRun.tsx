import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import type { Defaults } from "../types";
import AreaPicker from "../components/AreaPicker";
import { ErrorBox, Note, Section, Spinner } from "../components/ui";

type BBox = [number, number, number, number];
type Source = "cdse" | "synthetic" | "local";

const SOURCES: { id: Source; title: string; text: string }[] = [
  { id: "cdse", title: "Sentinel-1 (Copernicus)", text: "Real radar images, downloaded and terrain-corrected by Copernicus. Needs a free account." },
  { id: "synthetic", title: "Simulated demo", text: "A simulated river with known answers. Shows how the system works; it is not a map." },
  { id: "local", title: "My own files", text: "Calibrated SAR GeoTIFFs listed in local_scenes.csv (HyP3, SNAP, ISRO EOS-04)." },
];

function areaKm2(b: BBox) {
  const lat = ((b[1] + b[3]) / 2) * (Math.PI / 180);
  return (b[2] - b[0]) * 111.32 * Math.cos(lat) * (b[3] - b[1]) * 110.57;
}

export default function NewRun() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const from = params.get("from");
  const [d, setD] = useState<Defaults | null>(null);
  const [bbox, setBbox] = useState<BBox>([89.7, 25.75, 90.1, 26.15]);
  const [name, setName] = useState("Dhubri post-monsoon 2025 vs 2026");
  const [before, setBefore] = useState({ start: "", end: "" });
  const [after, setAfter] = useState({ start: "", end: "" });
  const [source, setSource] = useState<Source>("cdse");
  const [cid, setCid] = useState("");
  const [secret, setSecret] = useState("");
  const [adv, setAdv] = useState({ resolution_m: 10, min_area_ha: 0.5, water_before_min: 0.75, water_after_max: 0.25, min_per_period: 3, orbit_direction: "", relative_orbit: "", boundary_file: "" });
  const [showAdv, setShowAdv] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.defaults().then((x) => {
      setD(x); setBbox(x.bbox);
      setBefore({ start: x.periods.before.start, end: x.periods.before.end });
      setAfter({ start: x.periods.after.start, end: x.periods.after.end });
      setAdv((a) => ({ ...a, ...x.change, min_per_period: x.min_per_period }));
      if (from) {
        // continue from a scene search: copy its settings
        return api.run(from).then((r) => {
          const c = r.config;
          setBbox(c.area.bbox); setName(r.name);
          setBefore({ start: c.periods.before.start, end: c.periods.before.end });
          setAfter({ start: c.periods.after.start, end: c.periods.after.end });
          setSource(c.scenes.source);
          setAdv((a) => ({ ...a, ...c.change, resolution_m: c.area.resolution_m, min_per_period: c.scenes.min_per_period,
            orbit_direction: c.scenes.orbit_direction ?? "", relative_orbit: c.scenes.relative_orbit ? String(c.scenes.relative_orbit) : "",
            boundary_file: c.reference.boundary_file ?? "" }));
        });
      }
    }).catch((e) => setErr(e.message));
  }, [from]);

  if (!d) return err ? <ErrorBox msg={err} /> : <Spinner />;

  const km2 = areaKm2(bbox);
  const problems: string[] = [];
  if (!(bbox[0] < bbox[2] && bbox[1] < bbox[3])) problems.push("West must be less than East, and South less than North.");
  if (!(before.start < before.end && after.start < after.end)) problems.push("Each period needs a start date before its end date.");
  if (!(before.end < after.start)) problems.push("The before period must end before the after period starts.");
  if (!name.trim()) problems.push("Give the analysis a name.");
  const needCreds = source === "cdse" && !d.has_env_credentials && !(cid && secret);

  async function submit(stage: "search" | "all") {
    setBusy(true); setErr("");
    try {
      const r = await api.create({
        name, bbox, before, after, source, stage,
        settings: { ...adv, orbit_direction: adv.orbit_direction || null, relative_orbit: adv.relative_orbit ? +adv.relative_orbit : null },
        client_id: cid || null, client_secret: secret || null,
      });
      nav(`/runs/${r.id}`);
    } catch (e) { setErr((e as Error).message); setBusy(false); }
  }

  const coord = (i: number, label: string) => (
    <div>
      <label className="label">{label}</label>
      <input type="number" step="0.01" className="input tabular-nums" value={bbox[i]}
        onChange={(e) => { const b = [...bbox] as BBox; b[i] = +e.target.value; setBbox(b); }} />
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">New analysis</h1>
        <p className="mt-1 text-sm text-slate-600">Choose an area and two periods. The system compares radar images from both periods and maps where water became land and land became water.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-5">
        <Section title="1. Area" className="lg:col-span-3">
          <AreaPicker bbox={bbox} onChange={setBbox} />
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {coord(0, "West (°E)")}{coord(2, "East (°E)")}{coord(1, "South (°N)")}{coord(3, "North (°N)")}
          </div>
          <p className="mt-3 text-xs text-slate-500">
            {km2 > 0 ? `${km2.toLocaleString("en-IN", { maximumFractionDigits: 0 })} km² · about ${(km2 / 100).toFixed(1)} million pixels at 10 m` : ""}
          </p>
          {km2 > 3000 && <div className="mt-2"><Note tone="warn">Large area: downloads and processing will take longer. Under 3,000 km² is recommended.</Note></div>}
        </Section>
        <div className="space-y-6 lg:col-span-2">
          <Section title="2. Periods">
            <p className="mb-3 text-xs text-slate-500">Use the same season in both years, so higher water is not mistaken for change.</p>
            {(["before", "after"] as const).map((k) => {
              const v = k === "before" ? before : after; const set = k === "before" ? setBefore : setAfter;
              return (
                <div key={k} className="mb-3 grid grid-cols-2 gap-3">
                  <div><label className="label">{k} from</label><input type="date" className="input" value={v.start} onChange={(e) => set({ ...v, start: e.target.value })} /></div>
                  <div><label className="label">{k} to</label><input type="date" className="input" value={v.end} onChange={(e) => set({ ...v, end: e.target.value })} /></div>
                </div>
              );
            })}
          </Section>
          <Section title="3. Name">
            <input className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </Section>
        </div>
      </div>

      <Section title="4. Data">
        <div className="grid gap-3 md:grid-cols-3">
          {SOURCES.map((s) => (
            <label key={s.id} className={`cursor-pointer rounded-lg border p-4 transition ${source === s.id ? "border-navy-600 bg-navy-50 ring-2 ring-navy-100" : "border-slate-200 hover:border-slate-300"}`}>
              <input type="radio" name="source" className="sr-only" checked={source === s.id} onChange={() => setSource(s.id)} />
              <div className="font-medium text-slate-900">{s.title}</div>
              <div className="mt-1 text-xs text-slate-600">{s.text}</div>
            </label>
          ))}
        </div>
        {source === "cdse" && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {d.has_env_credentials ? (
              <div className="md:col-span-2"><Note>Copernicus credentials found in this computer's environment; they will be used.</Note></div>
            ) : (
              <>
                <div><label className="label">Copernicus client ID</label><input className="input" value={cid} onChange={(e) => setCid(e.target.value)} autoComplete="off" /></div>
                <div><label className="label">Client secret</label><input type="password" className="input" value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="off" /></div>
                <p className="text-xs text-slate-500 md:col-span-2">
                  Free from dataspace.copernicus.eu → dashboard → OAuth clients. Passed only to this run's process and never saved to disk.
                  Finding scenes needs no account.
                </p>
              </>
            )}
          </div>
        )}
      </Section>

      <section className="card">
        <button type="button" className="flex w-full items-center justify-between px-5 py-4 text-left" onClick={() => setShowAdv(!showAdv)}>
          <span className="text-base font-semibold text-slate-900">Advanced settings</span>
          <span className="text-sm text-slate-500">{showAdv ? "Hide" : "Show"}</span>
        </button>
        {showAdv && (
          <div className="grid gap-4 border-t border-slate-100 px-5 py-5 md:grid-cols-3">
            <div><label className="label">Pixel size (m)</label>
              <select className="input" value={adv.resolution_m} onChange={(e) => setAdv({ ...adv, resolution_m: +e.target.value })}>
                {[10, 20, 30].map((v) => <option key={v}>{v}</option>)}</select></div>
            <div><label className="label">Smallest change reported (ha)</label>
              <input type="number" step="0.1" min="0.1" className="input" value={adv.min_area_ha} onChange={(e) => setAdv({ ...adv, min_area_ha: +e.target.value })} /></div>
            <div><label className="label">Minimum scenes per period</label>
              <input type="number" min="2" max="20" className="input" value={adv.min_per_period} onChange={(e) => setAdv({ ...adv, min_per_period: +e.target.value })} /></div>
            <div><label className="label">Water in at least this share of "before" scenes</label>
              <input type="number" step="0.05" min="0.5" max="1" className="input" value={adv.water_before_min} onChange={(e) => setAdv({ ...adv, water_before_min: +e.target.value })} /></div>
            <div><label className="label">Water in at most this share of "after" scenes</label>
              <input type="number" step="0.05" min="0" max="0.5" className="input" value={adv.water_after_max} onChange={(e) => setAdv({ ...adv, water_after_max: +e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="label">Orbit</label>
                <select className="input" value={adv.orbit_direction} onChange={(e) => setAdv({ ...adv, orbit_direction: e.target.value })}>
                  <option value="">Automatic</option><option>ASCENDING</option><option>DESCENDING</option></select></div>
              <div><label className="label">Relative orbit</label>
                <input type="number" min="1" max="175" placeholder="auto" className="input" value={adv.relative_orbit} onChange={(e) => setAdv({ ...adv, relative_orbit: e.target.value })} /></div>
            </div>
            <div className="md:col-span-3"><label className="label">Survey of India boundary file (optional)</label>
              <input className="input" placeholder="path to GeoJSON, Shapefile or GeoPackage; no boundary is drawn if empty" value={adv.boundary_file} onChange={(e) => setAdv({ ...adv, boundary_file: e.target.value })} /></div>
          </div>
        )}
      </section>

      {problems.map((p) => <ErrorBox key={p} msg={p} />)}
      {err && <ErrorBox msg={err} />}
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-secondary" disabled={busy || problems.length > 0} onClick={() => submit("search")}>Find scenes only</button>
        <button className="btn-primary" disabled={busy || problems.length > 0 || needCreds} onClick={() => submit("all")}>
          {busy ? "Starting…" : "Run full analysis"}
        </button>
        {needCreds && <span className="text-xs text-slate-500">Enter Copernicus credentials to run the full analysis.</span>}
      </div>
    </div>
  );
}
