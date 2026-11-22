import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import type { RunDetail } from "../../types";
import { ErrorBox, Note, Section } from "../../components/ui";

const STEPS = [
  ["search", "Find scenes", "Search the Sentinel-1 catalogue and pick one orbit geometry"],
  ["download", "Download", "Terrain-corrected images prepared by Copernicus"],
  ["process", "Detect water and change", "Speckle filter, thresholds, water frequency, change rules"],
  ["outputs", "Build outputs", "Alerts, map files, figures and PDF report"],
  ["validate", "Validate", "Optical cross-check and validation sample"],
] as const;

export default function Progress({ run, reload }: { run: RunDetail; reload: () => void }) {
  const [lines, setLines] = useState<string[]>([]);
  const [console_, setConsole] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const s = run.status;
  const searchOnly = run.stage_requested === "search";
  const steps = searchOnly ? STEPS.slice(0, 1) : STEPS;
  const cur = steps.findIndex(([k]) => k === s.stage);
  const done = s.state === "done";

  useEffect(() => {
    const get = () => api.log(run.id).then((l) => {
      setLines(l.find((x) => x.file === "run.log")?.lines.slice(-16) ?? []);
      setConsole(l.find((x) => x.file === "console.log")?.lines.slice(-14) ?? []);
    });
    get();
    if (s.state !== "running") return;
    const t = setInterval(get, 2500);
    return () => clearInterval(t);
  }, [run.id, s.state]);

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Section title="Progress">
        <ol className="space-y-4">
          {steps.map(([k, title, text], i) => {
            const state = done || i < cur ? "done" : i === cur ? s.state : "waiting";
            return (
              <li key={k} className="flex gap-3">
                <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  state === "done" ? "bg-emerald-600 text-white" : state === "running" ? "bg-navy-700 text-white animate-pulse" :
                  state === "failed" || state === "stopped" || state === "interrupted" ? "bg-red-600 text-white" : "bg-slate-200 text-slate-500"}`}>
                  {state === "done" ? "✓" : i + 1}
                </span>
                <div><div className="text-sm font-medium text-slate-900">{title}</div><div className="text-xs text-slate-500">{text}</div></div>
              </li>
            );
          })}
        </ol>
        {s.state === "running" && (
          <button className="btn-danger mt-6 w-full" onClick={() => api.stop(run.id).then(reload).catch((e) => setErr(e.message))}>Stop this analysis</button>
        )}
        {err && <div className="mt-3"><ErrorBox msg={err} /></div>}
      </Section>
      <div className="space-y-4 lg:col-span-2">
        {done && searchOnly && (
          <Note>
            Scenes found. Check the <Link className="font-medium underline" to={`/runs/${run.id}/scenes`}>scene list</Link>, then{" "}
            <Link className="font-medium underline" to={`/new?from=${run.id}`}>run the full analysis with the same settings</Link>.
          </Note>
        )}
        {["failed", "stopped", "interrupted"].includes(s.state) && <ErrorBox msg={`The analysis ${s.state} during "${s.stage}": ${s.message ?? ""}`} />}
        <Section title="Live log">
          <pre className="max-h-[420px] overflow-auto rounded-lg bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">{lines.join("\n") || "Starting…"}</pre>
        </Section>
        {s.state === "failed" && console_.length > 0 && (
          <Section title="Error details">
            <pre className="max-h-80 overflow-auto rounded-lg bg-red-950 p-4 text-xs text-red-100">{console_.join("\n")}</pre>
          </Section>
        )}
      </div>
    </div>
  );
}
