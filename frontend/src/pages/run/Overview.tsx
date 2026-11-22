import { useEffect, useState } from "react";
import { api, fileUrl } from "../../api";
import type { FullMetrics, RunDetail } from "../../types";
import ResultsMap from "../../components/ResultsMap";
import { Link } from "react-router-dom";
import SwipeMap, { type Mode } from "../../components/SwipeMap";
import { Kpi, Note, Section, fmtHa } from "../../components/ui";

export default function Overview({ run, onSelect }: { run: RunDetail; onSelect: (id: string) => void }) {
  const m = run.full_metrics!;
  const [layers, setLayers] = useState<{ bounds: [[number, number], [number, number]] | null; layers: string[] } | null>(null);
  const [polys, setPolys] = useState<GeoJSON.FeatureCollection | null>(null);
  const [statusById, setStatusById] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(0);
  const [pair, setPair] = useState("radar");
  const [mode, setMode] = useState<Mode>("swipe");
  useEffect(() => {
    api.layers(run.id).then(setLayers);
    api.polygons(run.id).then(setPolys);
    api.alerts(run.id).then((a) => {
      setStatusById(Object.fromEntries(a.map((x) => [x.alert_id, x.status])));
      setOpen(a.filter((x) => x.status === "new" || x.status === "under_review").length);
    });
  }, [run.id]);
  const cal = m.calibration_check;
  const opt = m.validation?.optical_auto;
  const has = (l: string) => layers?.layers.includes(l);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <Kpi label="Water → land" value={fmtHa(m.area_ha.water_to_land)} sub={`${m.polygons.water_to_land} polygons`} accent="#E69F00" />
        <Kpi label="Land → water" value={fmtHa(m.area_ha.land_to_water)} sub={`${m.polygons.land_to_water} polygons`} accent="#0072B2" />
        <Kpi label="Alerts" value={m.polygons.total} sub={`${m.polygons.high} high · ${m.polygons.medium} medium · ${m.polygons.low} low`} />
        <Kpi label="Awaiting review" value={open} sub="new or under review" />
        <Kpi label="Optical cross-check" value={opt ? `${opt.polygons_agree}/${opt.polygons_checked}` : "–"} sub={opt ? "polygons confirmed by Sentinel-2" : "no Sentinel-2 reference"} />
      </div>
      <Section title="Map" right={<span className="text-xs text-slate-500">Click a polygon to open its alert</span>}>
        {layers?.bounds ? (
          <ResultsMap runId={run.id} bounds={layers.bounds} layers={layers.layers} polygons={polys} statusById={statusById} onSelect={onSelect} />
        ) : <Note tone="warn">No map layers for this analysis.</Note>}
        <p className="mt-2 text-xs text-slate-500">
          Contains modified Copernicus Sentinel data. The basemap is for orientation only. No international boundary is shown unless a
          Survey of India boundary file is supplied.
        </p>
      </Section>
      {layers?.bounds && has("before") && has("after") && (
        <Section title="Compare before and after" right={
          <div className="flex flex-wrap items-center gap-2">
            <Seg value={pair} set={setPair} options={[["radar", "Radar"], ...(has("optical_before") ? [["optical", "Optical"]] : []), ["water", "Water frequency"]] as [string, string][]} />
            <Seg value={mode} set={(v) => setMode(v as Mode)} options={[["swipe", "Swipe"], ["side", "Side by side"], ["single", "Toggle"]]} />
            <Link to={`/explore?run=${run.id}`} className="btn-secondary py-1.5">Compare with recent imagery</Link>
          </div>}>
          <SwipeMap mode={mode} bounds={layers.bounds} polygons={polys} onSelect={onSelect} height="h-[560px]"
            left={{ kind: "image", url: fileUrl(run.id, `quicklooks/${PAIRS[pair][0]}.png`), bounds: layers.bounds, label: `Before · ${run.periods.before.label ?? run.periods.before.start}` }}
            right={{ kind: "image", url: fileUrl(run.id, `quicklooks/${PAIRS[pair][1]}.png`), bounds: layers.bounds, label: `After · ${run.periods.after.label ?? run.periods.after.start}` }} />
          <p className="mt-2 text-xs text-slate-500">Drag the handle to compare. Outlines show the detected changes; click one to open its alert.</p>
        </Section>
      )}
      <Section title="Quality checks"><Checks cal={cal} m={m} /></Section>
    </div>
  );
}

const PAIRS: Record<string, [string, string]> = {
  radar: ["before", "after"], optical: ["optical_before", "optical_after"], water: ["water_before", "water_after"],
};

function Seg({ value, set, options }: { value: string; set: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex overflow-hidden rounded-lg border border-slate-300 text-xs">
      {options.map(([k, l]) => (
        <button key={k} type="button" onClick={() => set(k)} className={`px-2.5 py-1.5 ${value === k ? "bg-navy-700 text-white" : "bg-white text-slate-700 hover:bg-slate-50"}`}>{l}</button>
      ))}
    </div>
  );
}

function Checks({ cal, m }: { cal: FullMetrics["calibration_check"]; m: FullMetrics }) {
  const ok = cal.status === "pass";
  return (
    <dl className="grid gap-4 text-sm sm:grid-cols-3">
      <div>
        <dt className="label">Calibration</dt>
        <dd className={ok ? "text-emerald-700" : "text-red-700"}>
          {cal.status === "insufficient" ? "Not enough stable land" : `${ok ? "Pass" : "Check"}: ${cal.difference_db} dB difference (limit ${cal.limit_db} dB)`}
        </dd>
      </div>
      <div>
        <dt className="label">Water thresholds</dt>
        <dd>{m.thresholds_db.min.toFixed(2)} to {m.thresholds_db.max.toFixed(2)} dB {m.thresholds_db.all_in_expected_range ? "" : "(some outside expected range)"}</dd>
      </div>
      <div>
        <dt className="label">Satellites · version</dt>
        <dd>{m.satellites.join(", ")} · <span className="text-xs text-slate-500">{m.model_version}</span></dd>
      </div>
    </dl>
  );
}
