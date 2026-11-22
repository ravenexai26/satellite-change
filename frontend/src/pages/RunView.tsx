import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import type { RunDetail } from "../types";
import { ErrorBox, SimBadge, Spinner, StatusBadge, fmtDate } from "../components/ui";
import Progress from "./run/Progress";
import Overview from "./run/Overview";
import AlertsTab from "./run/AlertsTab";
import ChartsTab from "./run/ChartsTab";
import ScenesTab from "./run/ScenesTab";
import ValidationTab from "./run/ValidationTab";
import DownloadsTab from "./run/DownloadsTab";
import LogTab from "./run/LogTab";

const TABS = [
  ["", "Overview"], ["alerts", "Alerts"], ["charts", "Charts"], ["scenes", "Scenes"],
  ["validation", "Validation"], ["downloads", "Report & downloads"], ["log", "Log"],
] as const;

export default function RunView() {
  const { id = "", "*": rest = "" } = useParams();
  const tab = rest.split("/")[0];
  const nav = useNavigate();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.run(id).then(setRun).catch((e) => setErr(e.message)), [id]);

  useEffect(() => { setRun(null); load(); }, [load]);
  useEffect(() => {
    if (run?.status.state !== "running") return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [run?.status.state, load]);

  if (err) return <ErrorBox msg={err} />;
  if (!run) return <Spinner />;
  const finished = !!run.full_metrics;
  const tabs = finished ? TABS : TABS.filter(([k]) => k === "" || k === "scenes" || k === "log");

  return (
    <div className="space-y-6">
      <div>
        <Link to="/" className="text-sm text-navy-700 hover:underline">← Analyses</Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900">{run.name}</h1>
          <StatusBadge state={run.status.state} stage={run.status.stage} />
          {run.simulated && <SimBadge />}
          {run.kind === "quick" && <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800 ring-1 ring-sky-200">Quick compare</span>}
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Before {run.periods.before.start} to {run.periods.before.end} · After {run.periods.after.start} to {run.periods.after.end}
          {run.metrics && <> · {run.metrics.n_before} + {run.metrics.n_after} scenes · {run.metrics.orbit}</>}
          {run.created && <> · started {fmtDate(run.created)}</>}
        </p>
        {run.full_metrics?.mode === "single_pair" && (
          <p className="mt-2 text-sm text-sky-800">One image per date: faster than a seasonal analysis, but wind or wet sand in either image can cause false changes. Confidence reflects how clearly each pixel is water or land in both images.</p>
        )}
        {run.simulated && (
          <p className="mt-2 text-sm text-violet-700">Simulated test data: these results check the software and are not a map of the real river.</p>
        )}
      </div>

      <nav className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {tabs.map(([k, label]) => (
          <NavLink key={k} to={`/runs/${id}${k ? `/${k}` : ""}`} end
            className={({ isActive }) => `-mb-px border-b-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap ${isActive ? "border-navy-700 text-navy-800" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {label}
          </NavLink>
        ))}
      </nav>

      {tab === "" && (finished ? <Overview run={run} onSelect={(aid) => nav(`/runs/${id}/alerts?alert=${aid}`)} /> : <Progress run={run} reload={load} />)}
      {tab === "alerts" && finished && <AlertsTab run={run} />}
      {tab === "charts" && finished && <ChartsTab run={run} />}
      {tab === "scenes" && <ScenesTab run={run} />}
      {tab === "validation" && finished && <ValidationTab run={run} reload={load} />}
      {tab === "downloads" && finished && <DownloadsTab run={run} />}
      {tab === "log" && <LogTab run={run} />}
    </div>
  );
}
