import { useEffect, useRef, useState } from "react";
import { GeoJSON, ImageOverlay, MapContainer, Pane, Rectangle, TileLayer, ZoomControl, useMap, useMapEvents } from "react-leaflet";
import type { LatLngBoundsExpression, Layer, Map as LMap, PathOptions } from "leaflet";
import { ESRI_IMAGERY, PlainAttribution } from "./ResultsMap";
import { CHANGE_COLOR, CHANGE_LABEL } from "./ui";

export type LayerSpec =
  | { kind: "tiles"; url: string; label: string }
  | { kind: "image"; url: string; bounds: [[number, number], [number, number]]; label: string }
  | { kind: "basemap"; label: string };
export type Mode = "swipe" | "side" | "single";

/** Clips the "left" pane to the part of the map left of the divider and the "right" pane to the rest. */
function SwipeClip({ ratio, enabled }: { ratio: number; enabled: boolean }) {
  const map = useMap();
  const apply = () => {
    const left = map.getPane("left"), right = map.getPane("right");
    if (!left || !right) return;
    if (!enabled) { left.style.clip = ""; right.style.clip = ""; return; }
    const nw = map.containerPointToLayerPoint([0, 0]);
    const se = map.containerPointToLayerPoint(map.getSize());
    const x = nw.x + map.getSize().x * ratio;
    left.style.clip = `rect(${nw.y}px, ${x}px, ${se.y}px, ${nw.x}px)`;
    right.style.clip = `rect(${nw.y}px, ${se.x}px, ${se.y}px, ${x}px)`;
  };
  useMapEvents({ move: apply, zoom: apply, resize: apply, zoomend: apply, moveend: apply });
  useEffect(apply); // eslint-disable-line
  return null;
}

function Layer_({ spec, pane }: { spec: LayerSpec; pane: string }) {
  if (spec.kind === "tiles") return <TileLayer key={spec.url} url={spec.url} pane={pane} maxNativeZoom={17} maxZoom={19} />;
  if (spec.kind === "image") return <ImageOverlay key={spec.url} url={spec.url} bounds={spec.bounds} pane={pane} />;
  return <TileLayer url={ESRI_IMAGERY.url} attribution={ESRI_IMAGERY.attribution} pane={pane} />;
}

function Sync({ other, onView }: { other?: LMap | null; onView?: (m: LMap) => void }) {
  const map = useMap();
  const busy = useRef(false);
  useMapEvents({
    move() {
      if (other && !busy.current) {
        busy.current = true;
        other.setView(map.getCenter(), map.getZoom(), { animate: false });
        busy.current = false;
      }
    },
    moveend() { onView?.(map); },
  });
  useEffect(() => { onView?.(map); }, []); // eslint-disable-line
  return null;
}

function Expose({ set }: { set: (m: LMap) => void }) {
  const map = useMap();
  useEffect(() => set(map), [map, set]);
  return null;
}

function Polys({ data, onSelect }: { data: GeoJSON.FeatureCollection; onSelect?: (id: string) => void }) {
  const style = (f?: GeoJSON.Feature): PathOptions => ({ color: CHANGE_COLOR[f?.properties?.cls] ?? "#fff", weight: 2, fillOpacity: 0 });
  return (
    <GeoJSON key={JSON.stringify(data.features.length) + (data.features[0]?.properties?.id ?? "")} data={data} style={style}
      onEachFeature={(f: GeoJSON.Feature, layer: Layer) => {
        const p = f.properties ?? {};
        layer.bindTooltip(`<b>${p.id}</b> · ${CHANGE_LABEL[p.cls] ?? p.cls}<br/>${Number(p.area_ha).toFixed(2)} ha · confidence ${Number(p.confidence).toFixed(2)} · ${p.priority}`, { sticky: true });
        layer.on("click", () => onSelect?.(p.id));
        layer.on("mouseover", (e) => e.target.setStyle({ weight: 4, fillOpacity: 0.12 }));
        layer.on("mouseout", (e) => e.target.setStyle({ weight: 2, fillOpacity: 0 }));
      }} />
  );
}

export default function SwipeMap({ left, right, mode, polygons, showPolygons = true, bounds, center, zoom, outline, onView, onSelect, height = "h-[600px]" }: {
  left: LayerSpec; right: LayerSpec; mode: Mode; polygons?: GeoJSON.FeatureCollection | null; showPolygons?: boolean;
  bounds?: LatLngBoundsExpression; center?: [number, number]; zoom?: number; outline?: LatLngBoundsExpression | null;
  onView?: (m: LMap) => void; onSelect?: (id: string) => void; height?: string;
}) {
  const [ratio, setRatio] = useState(0.5);
  const [single, setSingle] = useState<"left" | "right">("right");
  const [mapA, setMapA] = useState<LMap | null>(null);
  const [mapB, setMapB] = useState<LMap | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const view = bounds ? { bounds } : { center: center ?? [26, 90], zoom: zoom ?? 11 };

  const overlays = (
    <>
      {outline && <Rectangle bounds={outline} pathOptions={{ color: "#e2e8f0", weight: 1, dashArray: "4 4", fill: false }} interactive={false} />}
      {showPolygons && polygons && polygons.features.length > 0 && <Polys data={polygons} onSelect={onSelect} />}
    </>
  );

  useEffect(() => {
    const up = () => { dragging.current = false; };
    const move = (e: PointerEvent) => {
      if (!dragging.current || !wrap.current) return;
      const r = wrap.current.getBoundingClientRect();
      setRatio(Math.min(0.98, Math.max(0.02, (e.clientX - r.left) / r.width)));
    };
    window.addEventListener("pointerup", up); window.addEventListener("pointermove", move);
    return () => { window.removeEventListener("pointerup", up); window.removeEventListener("pointermove", move); };
  }, []);

  if (mode === "side") {
    return (
      <div className={`grid grid-cols-2 gap-2 ${height}`}>
        {([["left", left, mapB, setMapA], ["right", right, mapA, setMapB]] as const).map(([k, spec, other, set]) => (
          <div key={k} className="relative">
            <MapContainer {...view} zoomSnap={0.25} zoomControl={false} className="h-full w-full rounded-lg" scrollWheelZoom>
              <ZoomControl position="bottomright" />
              <PlainAttribution />
              <Expose set={set} />
              <Sync other={other} onView={k === "left" ? onView : undefined} />
              <TileLayer url={ESRI_IMAGERY.url} attribution={ESRI_IMAGERY.attribution} />
              <Pane name="img" style={{ zIndex: 250 }}><Layer_ spec={spec} pane="img" /></Pane>
              {overlays}
            </MapContainer>
            <span className="pointer-events-none absolute top-3 left-3 z-[1000] rounded bg-black/65 px-2 py-1 text-xs font-semibold text-white">{spec.label}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div ref={wrap} className={`relative ${height}`}>
      <MapContainer {...view} zoomSnap={0.25} zoomControl={false} className="h-full w-full rounded-lg" scrollWheelZoom>
        <ZoomControl position="bottomright" />
        <PlainAttribution />
        <Sync onView={onView} />
        <TileLayer url={ESRI_IMAGERY.url} attribution={ESRI_IMAGERY.attribution} />
        <Pane name="left" style={{ zIndex: 250 }}>{(mode === "swipe" || single === "left") && <Layer_ spec={left} pane="left" />}</Pane>
        <Pane name="right" style={{ zIndex: 251 }}>{(mode === "swipe" || single === "right") && <Layer_ spec={right} pane="right" />}</Pane>
        <SwipeClip ratio={ratio} enabled={mode === "swipe"} />
        {overlays}
      </MapContainer>
      {mode === "swipe" && (
        <>
          <div className="pointer-events-none absolute inset-y-0 z-[1000] w-0.5 bg-white shadow-[0_0_4px_rgba(0,0,0,.6)]" style={{ left: `${ratio * 100}%` }} />
          <button type="button" aria-label="Drag to compare" onPointerDown={(e) => { e.preventDefault(); dragging.current = true; }}
            className="absolute top-1/2 z-[1001] flex h-10 w-10 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-full border-2 border-white bg-navy-800 text-white shadow-lg"
            style={{ left: `${ratio * 100}%` }}>⇆</button>
          <span className="pointer-events-none absolute top-3 left-3 z-[1000] rounded bg-black/65 px-2 py-1 text-xs font-semibold text-white">◀ {left.label}</span>
          <span className="pointer-events-none absolute top-3 right-3 z-[1000] rounded bg-black/65 px-2 py-1 text-xs font-semibold text-white">{right.label} ▶</span>
        </>
      )}
      {mode === "single" && (
        <div className="absolute top-3 left-1/2 z-[1000] flex -translate-x-1/2 overflow-hidden rounded-lg border border-slate-300 bg-white text-sm shadow">
          {(["left", "right"] as const).map((k) => (
            <button key={k} type="button" onClick={() => setSingle(k)}
              className={`px-3 py-1.5 ${single === k ? "bg-navy-700 text-white" : "text-slate-700 hover:bg-slate-50"}`}>
              {(k === "left" ? left : right).label}
            </button>
          ))}
        </div>
      )}
      <div className="pointer-events-none absolute bottom-6 left-3 z-[1000] rounded-lg bg-white/95 px-3 py-2 text-xs shadow">
        {Object.entries(CHANGE_LABEL).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2"><span className="h-0.5 w-4" style={{ background: CHANGE_COLOR[k], height: 3 }} />{v}</div>
        ))}
      </div>
    </div>
  );
}
