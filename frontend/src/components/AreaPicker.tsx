import { useEffect, useRef, useState } from "react";
import { MapContainer, Rectangle, TileLayer, useMap, useMapEvents } from "react-leaflet";
import type { LatLng, LatLngBoundsExpression } from "leaflet";
import { ESRI_IMAGERY, PlainAttribution } from "./ResultsMap";

type BBox = [number, number, number, number];

function Drawer({ drawing, onDone }: { drawing: boolean; onDone: (b: BBox) => void }) {
  const map = useMap();
  const start = useRef<LatLng | null>(null);
  const [preview, setPreview] = useState<LatLngBoundsExpression | null>(null);
  useEffect(() => {
    const c = map.getContainer();
    if (drawing) { map.dragging.disable(); c.classList.add("drawing"); }
    else { map.dragging.enable(); c.classList.remove("drawing"); }
  }, [drawing, map]);
  useMapEvents({
    mousedown(e) { if (drawing) { start.current = e.latlng; setPreview([[e.latlng.lat, e.latlng.lng], [e.latlng.lat, e.latlng.lng]]); } },
    mousemove(e) { if (drawing && start.current) setPreview([[start.current.lat, start.current.lng], [e.latlng.lat, e.latlng.lng]]); },
    mouseup(e) {
      if (drawing && start.current) {
        const a = start.current, b = e.latlng;
        start.current = null; setPreview(null);
        const box: BBox = [Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)].map((v) => +v.toFixed(4)) as BBox;
        if (box[2] - box[0] > 0.005 && box[3] - box[1] > 0.005) onDone(box);
      }
    },
  });
  return preview ? <Rectangle bounds={preview} pathOptions={{ color: "#E69F00", weight: 2, dashArray: "5 4" }} /> : null;
}

function Fit({ bbox, version }: { bbox: BBox; version: number }) {
  const map = useMap();
  useEffect(() => { map.fitBounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { padding: [30, 30] }); }, [version]); // eslint-disable-line
  return null;
}

export default function AreaPicker({ bbox, onChange }: { bbox: BBox; onChange: (b: BBox) => void }) {
  const [drawing, setDrawing] = useState(false);
  const [fitVersion, setFitVersion] = useState(0);
  return (
    <div className="relative">
      <MapContainer center={[(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2]} zoom={10} zoomSnap={0.25} className="h-[420px] w-full rounded-lg" scrollWheelZoom>
        <PlainAttribution />
        <TileLayer url={ESRI_IMAGERY.url} attribution={ESRI_IMAGERY.attribution} />
        <Rectangle bounds={[[bbox[1], bbox[0]], [bbox[3], bbox[2]]]} pathOptions={{ color: "#56B4E9", weight: 2, fillOpacity: 0.08 }} />
        <Drawer drawing={drawing} onDone={(b) => { onChange(b); setDrawing(false); }} />
        <Fit bbox={bbox} version={fitVersion} />
      </MapContainer>
      <div className="absolute top-3 right-3 z-[1000] flex gap-2">
        <button type="button" className={drawing ? "btn-primary shadow" : "btn-secondary shadow"} onClick={() => setDrawing(!drawing)}>
          {drawing ? "Drag on the map…" : "Draw area"}
        </button>
        <button type="button" className="btn-secondary shadow" onClick={() => setFitVersion((v) => v + 1)}>Zoom to area</button>
      </div>
    </div>
  );
}
