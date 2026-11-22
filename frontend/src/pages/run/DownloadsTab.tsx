import { useEffect, useState } from "react";
import { marked } from "marked";
import { fileUrl } from "../../api";
import type { RunDetail } from "../../types";
import { Section } from "../../components/ui";

const FILES: [string, string, string][] = [
  ["evidence_report.pdf", "Evidence report", "PDF: maps, close-ups, method note"],
  ["change_polygons.geojson", "Change polygons", "GeoJSON, WGS84"],
  ["change_polygons.kml", "Change polygons", "KML for Bhuvan and Google Earth"],
  ["change_polygons.gpkg", "Change polygons", "GeoPackage for QGIS and ArcGIS"],
  ["alerts.json", "Alerts", "JSON with evidence and audit logs"],
  ["metrics.json", "All numbers", "JSON written by the pipeline"],
  ["scenes.csv", "Scenes", "CSV of every acquisition found"],
  ["thresholds.csv", "Thresholds", "CSV, one row per scene"],
];

export default function DownloadsTab({ run }: { run: RunDetail }) {
  const [note, setNote] = useState("");
  useEffect(() => { fetch(fileUrl(run.id, "method_note.md")).then((r) => (r.ok ? r.text() : "")).then(setNote); }, [run.id]);
  return (
    <div className="space-y-6">
      <Section title="Downloads">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {FILES.map(([f, t, d]) => (
            <a key={f} href={fileUrl(run.id, f)} download className="rounded-lg border border-slate-200 p-4 hover:border-navy-600 hover:bg-navy-50">
              <div className="font-medium text-slate-900">{t}</div>
              <div className="text-xs text-slate-500">{d}</div>
              <div className="mt-1 font-mono text-xs text-navy-700">{f}</div>
            </a>
          ))}
          <a href={`/api/runs/${run.id}/rasters.zip`} className="rounded-lg border border-slate-200 p-4 hover:border-navy-600 hover:bg-navy-50">
            <div className="font-medium text-slate-900">Rasters</div>
            <div className="text-xs text-slate-500">Cloud-Optimised GeoTIFFs: backscatter, water frequency, change class</div>
            <div className="mt-1 font-mono text-xs text-navy-700">rasters.zip</div>
          </a>
        </div>
      </Section>
      <Section title="Figures for the report">
        <div className="space-y-4">
          <img src={fileUrl(run.id, "figures/change_overview_A4.png")} alt="Change overview" className="w-full rounded border border-slate-200" />
          <img src={fileUrl(run.id, "figures/largest_changes_A4.png")} alt="Largest changes" className="mx-auto max-w-3xl rounded border border-slate-200" />
        </div>
      </Section>
      {note && (
        <Section title="Method note">
          <div className="space-y-2 text-sm leading-relaxed text-slate-700 [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_ol>li]:list-decimal"
            dangerouslySetInnerHTML={{ __html: marked.parse(note) as string }} />
        </Section>
      )}
    </div>
  );
}
