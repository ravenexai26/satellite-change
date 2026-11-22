"""Map tiles of Sentinel-1 radar and Sentinel-2 optical imagery for any date.

Each 256 x 256 Web Mercator tile is rendered on request by the Copernicus Sentinel Hub Process API and cached on
disk. Satellites do not image a place continuously: a tile "for" a date shows the newest acquisition in the
`window_days` up to and including that date (Sentinel-1 revisits about every 6 days, Sentinel-2 about every 5,
often under cloud).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

from .sources import cdse

MIN_ZOOM, MAX_ZOOM = 8, 17
R = 6378137.0
SENSORS = {"radar": "Sentinel-1 radar (false colour)", "radar_vv": "Sentinel-1 radar (VV, grey)",
           "optical": "Sentinel-2 true colour"}

EVAL_RADAR = """//VERSION=3
function setup() { return {input: ["VV", "VH", "dataMask"], output: {bands: 4, sampleType: "UINT8"}}; }
function db(x) { return 10 * Math.log(Math.max(x, 1e-5)) / Math.LN10; }
function sc(v, lo, hi) { return Math.round(255 * Math.min(1, Math.max(0, (v - lo) / (hi - lo)))); }
function evaluatePixel(s) {
  var vv = db(s.VV), vh = db(s.VH);
  return [sc(vv, -25, 0), sc(vh, -30, -5), sc(vv - vh, 0, 15), 255 * s.dataMask];
}"""

EVAL_RADAR_VV = """//VERSION=3
function setup() { return {input: ["VV", "dataMask"], output: {bands: 4, sampleType: "UINT8"}}; }
function evaluatePixel(s) {
  var v = 10 * Math.log(Math.max(s.VV, 1e-5)) / Math.LN10;
  var g = Math.round(255 * Math.min(1, Math.max(0, (v + 25) / 25)));
  return [g, g, g, 255 * s.dataMask];
}"""

EVAL_OPTICAL = """//VERSION=3
function setup() { return {input: ["B02", "B03", "B04", "dataMask"], output: {bands: 4, sampleType: "UINT8"}}; }
function c(x) { return Math.round(255 * Math.min(1, Math.max(0, 2.8 * x))); }
function evaluatePixel(s) { return [c(s.B04), c(s.B03), c(s.B02), 255 * s.dataMask]; }"""

# a fully transparent 1 x 1 PNG, returned when there is nothing to draw
EMPTY_PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154785e6360606060000000050001196903cf0000000049454e44ae426082")


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Web Mercator (EPSG:3857) bounds of an XYZ tile: west, south, east, north in metres."""
    size = 2 * math.pi * R / (2 ** z)
    w = -math.pi * R + x * size
    n = math.pi * R - y * size
    return w, n - size, w + size, n


def request_body(sensor: str, day: date, window_days: int, z: int, x: int, y: int, max_cloud: int = 30) -> dict:
    t0 = (day - timedelta(days=window_days)).isoformat() + "T00:00:00Z"
    t1 = day.isoformat() + "T23:59:59Z"
    if sensor in ("radar", "radar_vv"):
        data = {"type": "sentinel-1-grd",
                "dataFilter": {"timeRange": {"from": t0, "to": t1}, "acquisitionMode": "IW", "polarization": "DV",
                               "resolution": "HIGH", "mosaickingOrder": "mostRecent"},
                "processing": {"orthorectify": True, "demInstance": "COPERNICUS_30", "backCoeff": "GAMMA0_TERRAIN"}}
        script = EVAL_RADAR if sensor == "radar" else EVAL_RADAR_VV
    elif sensor == "optical":
        data = {"type": "sentinel-2-l2a",
                "dataFilter": {"timeRange": {"from": t0, "to": t1}, "maxCloudCoverage": max_cloud,
                               "mosaickingOrder": "leastCC"}}
        script = EVAL_OPTICAL
    else:
        raise ValueError(f"unknown sensor {sensor}")
    return {"input": {"bounds": {"bbox": list(tile_bounds(z, x, y)),
                                 "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/3857"}},
                      "data": [data]},
            "output": {"width": 256, "height": 256,
                       "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
            "evalscript": script}


def get_tile(session: "cdse.Session", cache: Path, sensor: str, day: date, window_days: int,
             z: int, x: int, y: int, max_cloud: int = 30) -> bytes:
    if z < MIN_ZOOM or z > MAX_ZOOM:
        return EMPTY_PNG
    path = cache / sensor / f"{day.isoformat()}_w{window_days}_c{max_cloud}" / str(z) / str(x) / f"{y}.png"
    if path.exists():
        return path.read_bytes()
    png = session.process(request_body(sensor, day, window_days, z, x, y, max_cloud), accept="image/png")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(png)
    tmp.replace(path)
    return png
