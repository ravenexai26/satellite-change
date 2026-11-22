import type { ReactNode } from "react";
import type { State } from "../types";

export const fmtHa = (v: number) => `${v.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: v < 10 ? 2 : 1 })} ha`;
export const fmtDate = (iso?: string) => (iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "");
export const CHANGE_LABEL: Record<string, string> = { water_to_land: "Water → land", land_to_water: "Land → water" };
export const CHANGE_COLOR: Record<string, string> = { water_to_land: "#E69F00", land_to_water: "#0072B2" };

const STATE_STYLE: Record<string, string> = {
  running: "bg-blue-50 text-blue-700 ring-blue-200", done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-red-50 text-red-700 ring-red-200", stopped: "bg-slate-100 text-slate-600 ring-slate-200",
  interrupted: "bg-amber-50 text-amber-800 ring-amber-200", unknown: "bg-slate-100 text-slate-600 ring-slate-200",
};
const STATE_TEXT: Record<string, string> = { running: "Running", done: "Complete", failed: "Failed", stopped: "Stopped", interrupted: "Interrupted", unknown: "Unknown" };

export function StatusBadge({ state, stage }: { state: State; stage?: string }) {
  const text = state === "done" && stage === "search" ? "Scenes found" : STATE_TEXT[state] ?? state;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${STATE_STYLE[state] ?? STATE_STYLE.unknown}`}>
      {state === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-600" />}
      {text}
    </span>
  );
}

const PRI: Record<string, string> = { high: "bg-red-50 text-red-700 ring-red-200", medium: "bg-amber-50 text-amber-800 ring-amber-200", low: "bg-slate-100 text-slate-600 ring-slate-200" };
export const PriorityBadge = ({ p }: { p: string }) => (
  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ring-1 ${PRI[p]}`}>{p}</span>
);

export const SimBadge = () => (
  <span className="rounded-full bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-700 ring-1 ring-violet-200">Simulated</span>
);

export function ChangeChip({ type }: { type: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHANGE_COLOR[type] }} />
      {CHANGE_LABEL[type] ?? type}
    </span>
  );
}

export function Kpi({ label, value, sub, accent }: { label: string; value: ReactNode; sub?: ReactNode; accent?: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
        {accent && <span className="h-2.5 w-2.5 rounded-sm" style={{ background: accent }} />}
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function Section({ title, children, right, className = "" }: { title?: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || right) && (
        <div className="mb-4 flex items-center justify-between gap-4">
          {title && <h3 className="text-base font-semibold text-slate-900">{title}</h3>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">{children}</div>
);

export const Spinner = () => <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-300 border-t-navy-700" />;

export const ErrorBox = ({ msg }: { msg: string }) => (
  <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{msg}</div>
);

export const Note = ({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) => (
  <div className={`rounded-lg border px-4 py-3 text-sm ${tone === "warn" ? "border-amber-200 bg-amber-50 text-amber-900" : "border-navy-100 bg-navy-50 text-navy-900"}`}>{children}</div>
);
