import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fileUrl } from "../../api";
import type { Alert, RunDetail } from "../../types";
import ResultsMap from "../../components/ResultsMap";
import { ChangeChip, Empty, ErrorBox, PriorityBadge, Section, Spinner, fmtDate } from "../../components/ui";

const PRI_ORDER = { high: 0, medium: 1, low: 2 } as const;
type SortKey = "priority" | "area_ha" | "confidence" | "alert_id";

export default function AlertsTab({ run }: { run: RunDetail }) {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [layers, setLayers] = useState<{ bounds: [[number, number], [number, number]] | null; layers: string[] } | null>(null);
  const [polys, setPolys] = useState<GeoJSON.FeatureCollection | null>(null);
  const [params, setParams] = useSearchParams();
  const sel = params.get("alert");
  const [fPri, setFPri] = useState<string>("all");
  const [fType, setFType] = useState<string>("all");
  const [fStatus, setFStatus] = useState<string>("all");
  const [minConf, setMinConf] = useState(0);
  const [sort, setSort] = useState<{ k: SortKey; asc: boolean }>({ k: "priority", asc: true });

  useEffect(() => {
    api.alerts(run.id).then(setAlerts); api.statuses().then(setStatuses);
    api.layers(run.id).then(setLayers); api.polygons(run.id).then(setPolys);
  }, [run.id]);

  const view = useMemo(() => {
    if (!alerts) return [];
    const v = alerts.filter((a) => (fPri === "all" || a.priority === fPri) && (fType === "all" || a.type === fType) &&
      (fStatus === "all" || a.status === fStatus) && a.confidence >= minConf);
    const dir = sort.asc ? 1 : -1;
    return v.sort((a, b) => {
      if (sort.k === "priority") return (PRI_ORDER[a.priority] - PRI_ORDER[b.priority]) * dir || b.area_ha - a.area_ha;
      if (sort.k === "alert_id") return a.alert_id.localeCompare(b.alert_id) * dir;
      return (a[sort.k] - b[sort.k]) * dir;
    });
  }, [alerts, fPri, fType, fStatus, minConf, sort]);

  if (!alerts) return <Spinner />;
  if (!alerts.length) return <Empty>No changes above the reporting size in this analysis.</Empty>;
  const current = alerts.find((a) => a.alert_id === sel) ?? null;
  const select = (id: string) => setParams({ alert: id });
  const head = (k: SortKey, label: string, right = false) => (
    <th className={`cursor-pointer px-3 py-2.5 select-none ${right ? "text-right" : ""}`} onClick={() => setSort({ k, asc: sort.k === k ? !sort.asc : k !== "area_ha" && k !== "confidence" })}>
      {label}{sort.k === k ? (sort.asc ? " ↑" : " ↓") : ""}
    </th>
  );
  const csv = () => {
    const rows = [["alert_id", "priority", "type", "area_ha", "confidence", "status", "observed_at"], ...view.map((a) => [a.alert_id, a.priority, a.type, a.area_ha, a.confidence, a.status, a.observed_at])];
    const url = URL.createObjectURL(new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: `${run.id}_alerts.csv` }).click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid gap-6 xl:grid-cols-5">
      <div className="space-y-4 xl:col-span-3">
        <div className="card flex flex-wrap items-end gap-3 p-4">
          <Filter label="Priority" value={fPri} set={setFPri} options={[["all", "All"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]]} />
          <Filter label="Change" value={fType} set={setFType} options={[["all", "All"], ["water_to_land", "Water → land"], ["land_to_water", "Land → water"]]} />
          <Filter label="Status" value={fStatus} set={setFStatus} options={[["all", "All"], ...Object.entries(statuses)]} />
          <div className="w-44">
            <label className="label">Min. confidence {minConf.toFixed(2)}</label>
            <input type="range" min={0} max={1} step={0.05} value={minConf} onChange={(e) => setMinConf(+e.target.value)} className="w-full accent-navy-700" />
          </div>
          <button className="btn-secondary ml-auto" onClick={csv}>Export CSV</button>
        </div>
        <div className="card overflow-hidden">
          <div className="max-h-[620px] overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
                <tr>{head("alert_id", "Alert")}{head("priority", "Priority")}<th className="px-3 py-2.5">Change</th>{head("area_ha", "Area (ha)", true)}{head("confidence", "Confidence", true)}<th className="px-3 py-2.5">Status</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {view.map((a) => (
                  <tr key={a.alert_id} onClick={() => select(a.alert_id)}
                    className={`cursor-pointer ${a.alert_id === sel ? "bg-navy-50" : "hover:bg-slate-50"}`}>
                    <td className="px-3 py-2.5 font-medium whitespace-nowrap text-navy-700">{a.alert_id}</td>
                    <td className="px-3 py-2.5"><PriorityBadge p={a.priority} /></td>
                    <td className="px-3 py-2.5 whitespace-nowrap"><ChangeChip type={a.type} /></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{a.area_ha.toFixed(2)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">
                      <div className="flex items-center justify-end gap-2">
                        <div className="h-1.5 w-16 rounded bg-slate-200"><div className="h-1.5 rounded bg-navy-600" style={{ width: `${a.confidence * 100}%` }} /></div>
                        {a.confidence.toFixed(2)}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-xs">{statuses[a.status] ?? a.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">{view.length} of {alerts.length} alerts</div>
        </div>
      </div>
      <div className="xl:col-span-2">
        {current ? (
          <AlertDetail key={current.alert_id} run={run} a={current} statuses={statuses} layers={layers} polys={polys}
            onSaved={(u) => setAlerts(alerts.map((x) => (x.alert_id === u.alert_id ? u : x)))} />
        ) : <Empty>Select an alert to see its evidence and record a review.</Empty>}
      </div>
    </div>
  );
}

function Filter({ label, value, set, options }: { label: string; value: string; set: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="w-40">
      <label className="label">{label}</label>
      <select className="input" value={value} onChange={(e) => set(e.target.value)}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );
}

function AlertDetail({ run, a, statuses, layers, polys, onSaved }: {
  run: RunDetail; a: Alert; statuses: Record<string, string>;
  layers: { bounds: [[number, number], [number, number]] | null; layers: string[] } | null;
  polys: GeoJSON.FeatureCollection | null; onSaved: (a: Alert) => void;
}) {
  const [actor, setActor] = useState(() => localStorage.getItem("reviewer") ?? "");
  const [status, setStatus] = useState(a.status);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);
  const save = async () => {
    setBusy(true); setErr(""); setOk(false);
    try {
      const u = await api.review(run.id, a.alert_id, { status, actor, note });
      localStorage.setItem("reviewer", actor);
      onSaved(u); setNote(""); setOk(true);
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  };
  const g = a.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
  const ring = g.type === "Polygon" ? g.coordinates[0] : g.coordinates[0][0];
  const lat = ring.reduce((s, c) => s + c[1], 0) / ring.length, lon = ring.reduce((s, c) => s + c[0], 0) / ring.length;
  return (
    <div className="space-y-4">
      <Section title={<span className="flex items-center gap-2">{a.alert_id} <PriorityBadge p={a.priority} /></span>}>
        <p className="text-sm text-slate-700">{a.description}.</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-slate-500">Change</dt><dd><ChangeChip type={a.type} /></dd>
          <dt className="text-slate-500">Area</dt><dd className="tabular-nums">{a.area_ha.toFixed(2)} ha</dd>
          <dt className="text-slate-500">Confidence</dt><dd className="tabular-nums">{a.confidence.toFixed(2)}</dd>
          <dt className="text-slate-500">Observed</dt><dd>{a.observed_at.slice(0, 10)}</dd>
          <dt className="text-slate-500">Centre</dt><dd className="tabular-nums">{lat.toFixed(5)}° N, {lon.toFixed(5)}° E</dd>
          <dt className="text-slate-500">Status</dt><dd>{statuses[a.status] ?? a.status}</dd>
        </dl>
        {a.evidence.image_chip && (
          <figure className="mt-4">
            <img src={fileUrl(run.id, a.evidence.image_chip)} alt={`${a.alert_id} before and after`} className="w-full rounded-lg border border-slate-200" />
            <figcaption className="mt-1 text-xs text-slate-500">Sentinel-1 radar before and after; outline marks the change.</figcaption>
          </figure>
        )}
        {layers?.bounds && (
          <div className="mt-4"><ResultsMap runId={run.id} bounds={layers.bounds} layers={layers.layers} polygons={polys} focus={a.geometry} height="h-72" compact /></div>
        )}
      </Section>
      <Section title="Record a review">
        <div className="space-y-3">
          <div><label className="label">Your name and role</label><input className="input" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="e.g. Duty officer, ASSAC" /></div>
          <div><label className="label">Status</label>
            <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
          <div><label className="label">Note</label><textarea className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></div>
          {err && <ErrorBox msg={err} />}
          {ok && <div className="text-sm text-emerald-700">Saved to the audit log.</div>}
          <button className="btn-primary" disabled={busy || !actor.trim()} onClick={save}>Save review</button>
        </div>
      </Section>
      <Section title="Audit log">
        <ol className="space-y-3">
          {[...a.audit].reverse().map((e, i) => (
            <li key={i} className="border-l-2 border-navy-100 pl-3 text-sm">
              <div className="font-medium text-slate-800">{e.action}</div>
              <div className="text-xs text-slate-500">{e.actor} · {fmtDate(e.at)}</div>
              {e.note && <div className="mt-0.5 text-slate-600">{e.note}</div>}
            </li>
          ))}
        </ol>
        <details className="mt-4 text-xs text-slate-500">
          <summary className="cursor-pointer">Source scenes and model version</summary>
          <div className="mt-2 break-all">Before: {a.evidence.before_scenes.join(", ")}</div>
          <div className="mt-1 break-all">After: {a.evidence.after_scenes.join(", ")}</div>
          <div className="mt-1">Model: {a.model_version} · Confidence method: {a.confidence_method}</div>
        </details>
      </Section>
    </div>
  );
}
