import { useEffect, useState } from "react";
import { api } from "../../api";
import type { RunDetail, Scene } from "../../types";
import { Empty, Section, Spinner } from "../../components/ui";

export default function ScenesTab({ run }: { run: RunDetail }) {
  const [rows, setRows] = useState<Scene[] | null>(null);
  useEffect(() => {
    const get = () => api.scenes(run.id).then(setRows);
    get();
    if (run.status.state !== "running") return;
    const t = setInterval(get, 4000);
    return () => clearInterval(t);
  }, [run.id, run.status.state]);
  if (!rows) return <Spinner />;
  if (!rows.length) return <Empty>The scene search has not finished yet.</Empty>;
  const used = rows.filter((r) => r.selected === "True");
  return (
    <Section title={`Radar acquisitions: ${used.length} used of ${rows.length} found`}>
      <p className="mb-4 text-sm text-slate-600">Scenes used share one orbit direction and relative orbit and cover the area. Each row is one satellite pass; consecutive slices of a pass are merged.</p>
      <div className="overflow-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
            <tr><th className="px-3 py-2">Used</th><th className="px-3 py-2">Period</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Satellite</th><th className="px-3 py-2">Orbit</th><th className="px-3 py-2 text-right">Area covered</th><th className="px-3 py-2">Scene IDs</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr key={i} className={r.selected === "True" ? "" : "text-slate-400"}>
                <td className="px-3 py-2">{r.selected === "True" ? "✓" : ""}</td>
                <td className="px-3 py-2 capitalize">{r.period}</td>
                <td className="px-3 py-2 tabular-nums">{r.date}</td>
                <td className="px-3 py-2">{r.satellite}</td>
                <td className="px-3 py-2">{r.orbit_direction} {r.relative_orbit}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.aoi_coverage ? `${Math.round(+r.aoi_coverage * 100)}%` : ""}</td>
                <td className="max-w-md truncate px-3 py-2 font-mono text-xs" title={r.scene_ids}>{r.scene_ids}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
