import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { RunSummary } from "../types";
import { Empty, ErrorBox, SimBadge, Spinner, StatusBadge, fmtDate, fmtHa } from "../components/ui";

export default function Runs() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    const load = () => api.runs().then((r) => live && setRuns(r)).catch((e) => live && setErr(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => { live = false; clearInterval(t); };
  }, []);
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Analyses</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">
            Each analysis compares Sentinel-1 radar images of an area from two periods and maps where water became land
            and land became water. Every change becomes an alert for human verification.
          </p>
        </div>
        <Link to="/new" className="btn-primary">New analysis</Link>
      </div>
      {err && <ErrorBox msg={err} />}
      {!runs && !err && <Spinner />}
      {runs && runs.length === 0 && (
        <Empty>
          No analyses yet. <Link className="font-medium text-navy-700 underline" to="/new">Start one</Link>. To try the system
          without an account, choose <b>Simulated demo</b> as the data source.
        </Empty>
      )}
      {runs && runs.length > 0 && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-5 py-3">Analysis</th><th className="px-5 py-3">Periods</th><th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Water → land</th><th className="px-5 py-3 text-right">Land → water</th>
                <th className="px-5 py-3 text-right">Alerts</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-5 py-3">
                    <Link to={`/runs/${r.id}`} className="font-medium text-navy-700 hover:underline">{r.name}</Link>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                      {fmtDate(r.created)} {r.simulated && <SimBadge />}
                      {r.kind === "quick" && <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800 ring-1 ring-sky-200">Quick compare</span>}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-600">
                    {r.periods.before.start} → {r.periods.before.end}<br />{r.periods.after.start} → {r.periods.after.end}
                  </td>
                  <td className="px-5 py-3"><StatusBadge state={r.status.state} stage={r.status.stage} /></td>
                  <td className="px-5 py-3 text-right tabular-nums">{r.metrics ? fmtHa(r.metrics.area_ha.water_to_land) : "–"}</td>
                  <td className="px-5 py-3 text-right tabular-nums">{r.metrics ? fmtHa(r.metrics.area_ha.land_to_water) : "–"}</td>
                  <td className="px-5 py-3 text-right tabular-nums">
                    {r.metrics ? <>{r.metrics.polygons.total}{r.metrics.polygons.high > 0 && <span className="ml-1 text-xs text-red-700">({r.metrics.polygons.high} high)</span>}</> : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
