import { useEffect, useMemo } from "react";
import { GeoJSON, ImageOverlay, LayersControl, MapContainer, Rectangle, TileLayer, useMap } from "react-leaflet";
import type { Layer, LatLngBoundsExpression, PathOptions } from "leaflet";
import { fileUrl } from "../api";
import { CHANGE_COLOR, CHANGE_LABEL } from "./ui";

export const ESRI_IMAGERY = {
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  attribution: "Imagery: Esri, Maxar, Earthstar Geographics",
};

const LAYER_LABEL: Record<string, string> = {
  optical_before: "Optical before (Sentinel-2)", optical_after: "Optical after (Sentinel-2)",
  before: "Radar before (Sentinel-1)", after: "Radar after (Sentinel-1)",
  water_before: "Water frequency before", water_after: "Water frequency after", change: "Change",
};
const DEFAULT_ON = new Set(["after", "change"]);

export function PlainAttribution() {
  const map = useMap();
  useEffect(() => { map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>'); }, [map]);
  return null;
}

function Fit({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => { map.fitBounds(bounds); }, []); // eslint-disable-line
  return null;
}

function FlyTo({ target }: { target?: GeoJSON.Geometry | null }) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    const coords: number[][] = target.type === "Polygon" ? target.coordinates[0] : target.type === "MultiPolygon" ? target.coordinates.flat(2) : [];
    if (!coords.length) return;
    const lats = coords.map((c) => c[1]), lngs = coords.map((c) => c[0]);
    const t = setTimeout(() => {
      map.invalidateSize();
      map.fitBounds([[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]], { padding: [24, 24], maxZoom: 15, animate: false });
    }, 150);
    return () => clearTimeout(t);
  }, [target, map]);
  return null;
}

export default function ResultsMap({ runId, bounds, layers, polygons, statusById, onSelect, focus, height = "h-[560px]", compact = false }: {
  runId: string; bounds: [[number, number], [number, number]]; layers: string[];
  polygons: GeoJSON.FeatureCollection | null; statusById?: Record<string, string>;
  onSelect?: (id: string) => void; focus?: GeoJSON.Geometry | null; height?: string; compact?: boolean;
}) {
  const style = (f?: GeoJSON.Feature): PathOptions => ({ color: CHANGE_COLOR[f?.properties?.cls] ?? "#999", weight: 1.6, fillOpacity: 0 });
  const key = useMemo(() => JSON.stringify(statusById ?? {}), [statusById]);
  return (
    <div className="relative">
      <MapContainer bounds={bounds} zoomSnap={0.25} className={`${height} w-full rounded-lg`} scrollWheelZoom>
        <PlainAttribution />
        {!focus && <Fit bounds={bounds} />}
        <FlyTo target={focus} />
        <LayersControl position="topright" collapsed={compact}>
          <LayersControl.BaseLayer checked name="Satellite basemap (Esri)">
            <TileLayer url={ESRI_IMAGERY.url} attribution={ESRI_IMAGERY.attribution} />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="No basemap">
            <TileLayer url="data:image/gif;base64,R0lGODlhAQABAAAAACw=" />
          </LayersControl.BaseLayer>
          {layers.map((l) => (
            <LayersControl.Overlay key={l} name={LAYER_LABEL[l] ?? l} checked={DEFAULT_ON.has(l)}>
              <ImageOverlay url={fileUrl(runId, `quicklooks/${l}.png`)} bounds={bounds} opacity={l === "change" ? 0.9 : 1} />
            </LayersControl.Overlay>
          ))}
          {polygons && polygons.features.length > 0 && (
            <LayersControl.Overlay checked name="Change polygons">
              <GeoJSON key={key} data={polygons} style={style}
                onEachFeature={(f: GeoJSON.Feature, layer: Layer) => {
                  const p = f.properties ?? {};
                  layer.bindTooltip(
                    `<b>${p.id}</b> · ${CHANGE_LABEL[p.cls] ?? p.cls}<br/>${Number(p.area_ha).toFixed(2)} ha · confidence ${Number(p.confidence).toFixed(2)}<br/>Priority ${p.priority}${statusById?.[p.id] ? ` · ${statusById[p.id]}` : ""}`,
                    { sticky: true });
                  layer.on("click", () => onSelect?.(p.id));
                  layer.on("mouseover", (e) => e.target.setStyle({ weight: 3.5, fillOpacity: 0.15 }));
                  layer.on("mouseout", (e) => e.target.setStyle({ weight: 1.6, fillOpacity: 0 }));
                }} />
            </LayersControl.Overlay>
          )}
        </LayersControl>
        <Rectangle bounds={bounds} pathOptions={{ color: "#64748b", weight: 1, dashArray: "4 4", fill: false }} interactive={false} />
      </MapContainer>
      {!compact && <div className="pointer-events-none absolute bottom-6 left-3 z-[1000] rounded-lg bg-white/95 px-3 py-2 text-xs shadow">
        {Object.entries(CHANGE_LABEL).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: CHANGE_COLOR[k] }} />{v}</div>
        ))}
      </div>}
    </div>
  );
}
