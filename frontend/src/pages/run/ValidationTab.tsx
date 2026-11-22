import { useEffect, useState } from "react";
import { api, fileUrl } from "../../api";
import type { RunDetail, VRow, Validation } from "../../types";
import { ErrorBox, Kpi, Note, Section, Spinner } from "../../components/ui";

export default function ValidationTab({ run, reload }: { run: RunDetail; reload: () => void }) {
  const [data, setData] = useState<{ rows: VRow[]; sheets: string[]; result: Validation } | null>(null);
  const [labels, setLabels] = useState<Record<string, { label: string; notes: string }>>({});
  const [sheet, setSheet] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    api.validation(run.id).then((d) => {
      setData(d);
      setLabels(Object.fromEntries(d.rows.map((r) => [r.sample_id, { label: r.label, notes: r.notes }])));
    });
  }, [run.id]);
  if (!data) return <Spinner />;
  const auto = data.result.optical_auto;
  const manual = data.result.manual;
  const save = async () => {
    setBusy(true); setErr(""); setSaved(false);
    try {
      const res = await api.saveLabels(run.id, labels);
      setData({ ...data, result: { ...data.result, manual: res } }); setSaved(true); reload();
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  };
  const done = Object.values(labels).filter((l) => l.label).length;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Optical: polygons confirmed" value={auto ? `${auto.polygons_agree} / ${auto.polygons_checked}` : "–"} sub="Sentinel-2 water index agrees" />
        <Kpi label="Optical: no-change confirmed" value={auto ? `${auto.nochange_agree} / ${auto.nochange_checked}` : "–"} sub="random points away from changes" />
        <Kpi label="Manual: change samples" value={manual?.change.judged ? `${manual.change.correct} / ${manual.change.judged}` : "–"} sub="labelled correct" />
        <Kpi label="Manual: no-change samples" value={manual?.no_change.judged ? `${manual.no_change.correct} / ${manual.no_change.judged}` : "–"} sub="labelled correct" />
      </div>
      {auto && <Note>{auto.method}. Sentinel-2 is an independent optical satellite, but its water index can be misled by cloud, shadow or muddy water, so treat it as a cross-check.</Note>}
      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Label the random sample" right={<span className="text-xs text-slate-500">{done} of {data.rows.length} labelled</span>}>
          <p className="mb-3 text-sm text-slate-600">Compare each sample in the Sentinel-2 sheets, then mark whether the system's call is correct.</p>
          <div className="max-h-[560px] overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
                <tr><th className="px-3 py-2">Sample</th><th className="px-3 py-2">System says</th><th className="px-3 py-2 text-right">Sentinel-2</th><th className="px-3 py-2">Your label</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.rows.map((r) => (
                  <tr key={r.sample_id}>
                    <td className="px-3 py-1.5 font-medium">{r.sample_id}</td>
                    <td className="px-3 py-1.5 text-xs">{r.expected.replaceAll("_", " ")}</td>
                    <td className="px-3 py-1.5 text-right text-xs tabular-nums">{r.auto_optical_agreement === "True" ? "agrees" : r.auto_optical_agreement === "False" ? "differs" : r.auto_optical_agreement ? `${Math.round(+r.auto_optical_agreement * 100)}%` : "–"}</td>
                    <td className="px-3 py-1.5">
                      <select className="input py-1" value={labels[r.sample_id]?.label ?? ""} onChange={(e) => setLabels({ ...labels, [r.sample_id]: { ...labels[r.sample_id], label: e.target.value } })}>
                        <option value="">not labelled</option><option value="correct">correct</option><option value="wrong">wrong</option><option value="unclear">unclear</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {err && <div className="mt-3"><ErrorBox msg={err} /></div>}
          <div className="mt-4 flex items-center gap-3">
            <button className="btn-primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save labels and score"}</button>
            {saved && <span className="text-sm text-emerald-700">Saved. The result is now in the method note and PDF report.</span>}
          </div>
        </Section>
        <Section title="Labelling sheets (Sentinel-2 true colour)" right={data.sheets.length > 1 && (
          <div className="flex items-center gap-2 text-sm">
            <button className="btn-secondary px-2 py-1" disabled={sheet === 0} onClick={() => setSheet(sheet - 1)}>‹</button>
            {sheet + 1} / {data.sheets.length}
            <button className="btn-secondary px-2 py-1" disabled={sheet >= data.sheets.length - 1} onClick={() => setSheet(sheet + 1)}>›</button>
          </div>)}>
          {data.sheets.length ? <img src={fileUrl(run.id, `validation/${data.sheets[sheet]}`)} alt="labelling sheet" className="w-full rounded border border-slate-200" />
            : <Note tone="warn">No Sentinel-2 reference was available, so no sheets were made.</Note>}
        </Section>
      </div>
    </div>
  );
}
