import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { api } from "../../api";
import type { Alert, RunDetail, Scene, Threshold } from "../../types";
import { Section, Spinner } from "../../components/ui";

const LAND = "#E69F00", WATER = "#0072B2", GREY = "#94a3b8", NAVY = "#0f4a7a";
const ax = { fontSize: 12, fill: "#64748b" };
const day = (d: string) => Date.parse(d);
const fmtDay = (t: number) => new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "2-digit" });

export default function ChartsTab({ run }: { run: RunDetail }) {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [thr, setThr] = useState<Threshold[]>([]);
  useEffect(() => { api.alerts(run.id).then(setAlerts); api.scenes(run.id).then(setScenes); api.thresholds(run.id).then(setThr); }, [run.id]);
  const m = run.full_metrics!;

  const timeline = useMemo(() => scenes.map((s) => ({ t: day(s.date), orbit: `${s.orbit_direction.slice(0, 3)} ${s.relative_orbit}`, used: s.selected === "True", sat: s.satellite, period: s.period })), [scenes]);
  const byPriority = useMemo(() => ["high", "medium", "low"].map((p) => ({
    priority: p[0].toUpperCase() + p.slice(1),
    "Water → land": alerts?.filter((a) => a.priority === p && a.type === "water_to_land").length ?? 0,
    "Land → water": alerts?.filter((a) => a.priority === p && a.type === "land_to_water").length ?? 0,
  })), [alerts]);
  const confHist = useMemo(() => {
    const bins = Array.from({ length: 10 }, (_, i) => ({ bin: (0.5 + i * 0.05).toFixed(2), n: 0 }));
    alerts?.forEach((a) => { bins[Math.min(9, Math.max(0, Math.floor((a.confidence - 0.5) / 0.05 + 1e-9)))].n++; });
    return bins;
  }, [alerts]);
  const sizeHist = useMemo(() => {
    const edges = [0, 1, 2, 5, 10, 20, 50, 100, 500, Infinity];
    const labels = ["<1", "1–2", "2–5", "5–10", "10–20", "20–50", "50–100", "100–500", "≥500"];
    const bins = labels.map((l) => ({ bin: l, n: 0 }));
    alerts?.forEach((a) => { const i = edges.findIndex((e, k) => a.area_ha >= e && a.area_ha < edges[k + 1]); if (i >= 0) bins[i].n++; });
    return bins;
  }, [alerts]);
  const perScene = useMemo(() => thr.map((t) => ({
    t: day(t.date), date: fmtDay(day(t.date)), sat: t.satellite,
    [`water_${t.period}`]: +(+t.water_share * 100).toFixed(2), [`thr_${t.period}`]: +(+t.threshold_db).toFixed(2),
  })).sort((a, b) => a.t - b.t), [thr]);

  if (!alerts) return <Spinner />;
  const area = [{ k: "Water → land", ha: m.area_ha.water_to_land, c: LAND }, { k: "Land → water", ha: m.area_ha.land_to_water, c: WATER }];

  return (
    <div className="space-y-6">
      <Section title="Radar acquisitions by orbit" right={<span className="text-xs text-slate-500">Used scenes share one orbit geometry, so both periods are viewed from the same angle</span>}>
        <ResponsiveContainer width="100%" height={Math.max(140, 60 + 36 * new Set(timeline.map((x) => x.orbit)).size)}>
          <ScatterChart margin={{ left: 10, right: 20, top: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="t" type="number" scale="time" domain={["dataMin - 864000000", "dataMax + 864000000"]} tickFormatter={fmtDay} tick={ax} />
            <YAxis dataKey="orbit" type="category" tick={ax} width={70} allowDuplicatedCategory={false} />
            <ZAxis range={[70, 70]} />
            <Tooltip cursor={false} formatter={(v, n) => (n === "t" ? fmtDay(v as number) : v)} />
            <Legend />
            <Scatter name="Used" data={timeline.filter((x) => x.used)} fill={WATER} />
            <Scatter name="Not used" data={timeline.filter((x) => !x.used)} fill={GREY} />
          </ScatterChart>
        </ResponsiveContainer>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Area changed (ha)">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={area} layout="vertical" margin={{ left: 20, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
              <XAxis type="number" tick={ax} tickFormatter={(v) => v.toLocaleString("en-IN")} />
              <YAxis type="category" dataKey="k" tick={ax} width={100} />
              <Tooltip formatter={(v) => `${(+(v ?? 0)).toLocaleString("en-IN", { maximumFractionDigits: 1 })} ha`} />
              <Bar dataKey="ha" radius={[0, 4, 4, 0]}>{area.map((a) => <Cell key={a.k} fill={a.c} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Alerts by priority">
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={byPriority} layout="vertical" margin={{ left: 10, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={ax} />
              <YAxis type="category" dataKey="priority" tick={ax} width={70} />
              <Tooltip /><Legend />
              <Bar dataKey="Water → land" stackId="a" fill={LAND} />
              <Bar dataKey="Land → water" stackId="a" fill={WATER} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Confidence of alerts">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={confHist} margin={{ right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="bin" tick={ax} height={30} />
              <YAxis allowDecimals={false} tick={ax} width={40} />
              <Tooltip /><Bar dataKey="n" name="alerts" fill={NAVY} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Size of changes (ha)">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={sizeHist} margin={{ right: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="bin" tick={ax} height={40} />
              <YAxis allowDecimals={false} tick={ax} width={40} />
              <Tooltip /><Bar dataKey="n" name="alerts" fill={NAVY} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>
        <Section title="Water detected in each scene (% of area)">
          <SceneLine data={perScene} keys={["water_before", "water_after"]} unit="%" />
        </Section>
        <Section title="Water threshold per scene (dB)">
          <SceneLine data={perScene} keys={["thr_before", "thr_after"]} unit=" dB" />
        </Section>
      </div>
      <p className="text-xs text-slate-500">A scene whose water share or threshold stands apart from the others may be affected by wind or rain. The frequency rule limits its influence.</p>
    </div>
  );
}

function SceneLine({ data, keys, unit }: { data: Record<string, number | string>[]; keys: [string, string]; unit: string }) {
  const vals = data.flatMap((d) => keys.map((k) => d[k])).filter((v): v is number => typeof v === "number");
  const pad = Math.max(0.5, (Math.max(...vals) - Math.min(...vals)) * 0.15);
  const domain = vals.length ? [+(Math.min(...vals) - pad).toFixed(1), +(Math.max(...vals) + pad).toFixed(1)] : ["auto", "auto"];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ right: 20, top: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="date" tick={ax} interval={0} angle={-30} textAnchor="end" height={50} />
        <YAxis tick={ax} width={50} domain={domain as [number, number]} allowDataOverflow={false} />
        <Tooltip formatter={(v) => `${v}${unit}`} />
        <Legend />
        <Line name="Before" dataKey={keys[0]} stroke={GREY} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} isAnimationActive={false} />
        <Line name="After" dataKey={keys[1]} stroke={WATER} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
