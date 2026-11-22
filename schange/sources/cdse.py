"""Copernicus Data Space Ecosystem (CDSE): scene search and server-side processing.

Search uses the public OData catalogue (no login). Download uses the Sentinel Hub Process API
on CDSE, which applies orbit, calibration, border-noise masking, orthorectification and
radiometric terrain flattening (gamma0) with the Copernicus 30 m DEM, and returns small
GeoTIFFs already on our grid. A free CDSE account and OAuth client are needed:
https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings  -> OAuth clients -> Create
Set CDSE_CLIENT_ID and CDSE_CLIENT_SECRET in the environment.
"""
from __future__ import annotations

import io
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import rasterio
import requests
from shapely import wkt
from shapely.geometry import box, shape
from shapely.ops import unary_union

ODATA = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
MAX_TILE_PX = 2000


class CDSEError(RuntimeError):
    pass


# ---------------------------------------------------------------- search

def _attr(p: dict, name: str):
    for a in p.get("Attributes", []):
        if a.get("Name") == name:
            return a.get("Value")
    return None


def search_s1(bbox, start: str, end: str, log=print) -> list[dict]:
    w, s, e, n = bbox
    poly = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    flt = (
        "Collection/Name eq 'SENTINEL-1' and "
        "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and "
        "att/OData.CSC.StringAttribute/Value eq 'IW_GRDH_1S') and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{poly}') and "
        f"ContentDate/Start gt {start}T00:00:00.000Z and ContentDate/Start lt {end}T23:59:59.999Z"
    )
    params = {"$filter": flt, "$expand": "Attributes", "$orderby": "ContentDate/Start", "$top": 200}
    r = requests.get(ODATA, params=params, timeout=120)
    if r.status_code != 200:
        raise CDSEError(f"OData search failed {r.status_code}: {r.text[:300]}")
    out = []
    for p in r.json().get("value", []):
        name = p["Name"]
        if name.endswith("_COG.SAFE") or "_CARD_" in name:
            continue  # skip derived copies of the same acquisition
        geom = None
        if p.get("GeoFootprint"):
            geom = shape(p["GeoFootprint"])
        elif p.get("Footprint"):
            geom = wkt.loads(p["Footprint"].split(";", 1)[-1].rstrip("'"))
        out.append({
            "scene_id": name.replace(".SAFE", ""),
            "start": p["ContentDate"]["Start"],
            "end": p["ContentDate"]["End"],
            "satellite": name[:3],
            "orbit_direction": (_attr(p, "orbitDirection") or "").upper(),
            "relative_orbit": _attr(p, "relativeOrbitNumber"),
            "footprint": geom,
        })
    log(f"  found {len(out)} IW GRDH scenes {start} to {end}")
    return out


def group_passes(scenes: list[dict], bbox) -> list[dict]:
    """Merge consecutive slices of one satellite pass into one acquisition."""
    aoi = box(*bbox)
    groups = defaultdict(list)
    for s in scenes:
        key = (s["start"][:10], s["satellite"], s["orbit_direction"], s["relative_orbit"])
        groups[key].append(s)
    passes = []
    for (date, sat, direction, rel), items in sorted(groups.items()):
        fp = unary_union([i["footprint"] for i in items if i["footprint"] is not None])
        cov = fp.intersection(aoi).area / aoi.area if not fp.is_empty else 0.0
        passes.append({
            "date": date, "satellite": sat, "orbit_direction": direction, "relative_orbit": rel,
            "time_from": min(i["start"] for i in items), "time_to": max(i["end"] for i in items),
            "scene_ids": ";".join(i["scene_id"] for i in items), "aoi_coverage": round(cov, 3),
        })
    return passes


def search_s2(bbox, start: str, end: str, max_cloud: float = 100) -> list[dict]:
    """Sentinel-2 L2A products over the box, with their cloud cover."""
    w, s, e, n = bbox
    poly = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    flt = (
        "Collection/Name eq 'SENTINEL-2' and "
        "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and "
        "att/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
        f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and "
        f"att/OData.CSC.DoubleAttribute/Value le {max_cloud}) and "
        f"OData.CSC.Intersects(area=geography'SRID=4326;{poly}') and "
        f"ContentDate/Start gt {start}T00:00:00.000Z and ContentDate/Start lt {end}T23:59:59.999Z"
    )
    r = requests.get(ODATA, params={"$filter": flt, "$expand": "Attributes", "$orderby": "ContentDate/Start",
                                    "$top": 200}, timeout=120)
    if r.status_code != 200:
        raise CDSEError(f"OData search failed {r.status_code}: {r.text[:300]}")
    return [{"date": p["ContentDate"]["Start"][:10], "satellite": p["Name"][:3], "cloud": _attr(p, "cloudCover"),
             "product": p["Name"]} for p in r.json().get("value", [])]


# ---------------------------------------------------------------- download

class Session:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.cid = client_id or os.environ.get("CDSE_CLIENT_ID")
        self.secret = client_secret or os.environ.get("CDSE_CLIENT_SECRET")
        if not self.cid or not self.secret:
            raise CDSEError("Set CDSE_CLIENT_ID and CDSE_CLIENT_SECRET (see README, step 2).")
        self.token, self.expires = None, 0

    def headers(self):
        if time.time() > self.expires - 60:
            r = requests.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": self.cid,
                                               "client_secret": self.secret}, timeout=60)
            if r.status_code != 200:
                raise CDSEError(f"CDSE login failed {r.status_code}: {r.text[:300]}")
            j = r.json()
            self.token, self.expires = j["access_token"], time.time() + j.get("expires_in", 600)
        return {"Authorization": f"Bearer {self.token}"}

    def process(self, body: dict, retries: int = 4, accept: str | None = None) -> bytes:
        for k in range(retries):
            h = self.headers()
            if accept:
                h = {**h, "Accept": accept}
            r = requests.post(PROCESS_URL, json=body, headers=h, timeout=300)
            if r.status_code == 200:
                return r.content
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (k + 1))
                continue
            raise CDSEError(f"Process API {r.status_code}: {r.text[:400]}")
        raise CDSEError("Process API kept failing after retries")


S1_EVALSCRIPT = """//VERSION=3
function setup() {
  return {input: ["VV", "VH", "dataMask"],
          output: {bands: 3, sampleType: "FLOAT32"}};
}
function evaluatePixel(s) {
  if (s.dataMask == 0) { return [NaN, NaN, 0]; }
  return [s.VV, s.VH, 1];
}"""

S2_EVALSCRIPT = """//VERSION=3
function setup() {
  return {input: ["B02", "B03", "B04", "B08", "dataMask"],
          output: {bands: 5, sampleType: "UINT16"}, mosaicking: "SIMPLE"};
}
function evaluatePixel(s) {
  return [s.B02 * 10000, s.B03 * 10000, s.B04 * 10000, s.B08 * 10000, s.dataMask];
}"""


def _tiles(grid):
    for r in range(0, grid.height, MAX_TILE_PX):
        for c in range(0, grid.width, MAX_TILE_PX):
            yield r, c, min(MAX_TILE_PX, grid.height - r), min(MAX_TILE_PX, grid.width - c)


def _fetch_mosaic(sess, grid, data_block, evalscript, bands, dtype, log):
    epsg = grid.crs.split(":")[1]
    out = np.zeros((bands,) + grid.shape, dtype=dtype)
    for r, c, h, w in _tiles(grid):
        x0 = grid.transform.c + c * grid.res
        y1 = grid.transform.f - r * grid.res
        body = {
            "input": {"bounds": {"bbox": [x0, y1 - h * grid.res, x0 + w * grid.res, y1],
                                 "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{epsg}"}},
                      "data": [data_block]},
            "output": {"width": w, "height": h,
                       "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
            "evalscript": evalscript,
        }
        content = sess.process(body)
        with rasterio.open(io.BytesIO(content)) as src:
            out[:, r:r + h, c:c + w] = src.read()
    return out


def download_pass(sess, grid, p: dict, cfg, out_path, log=print):
    t0 = datetime.fromisoformat(p["time_from"].replace("Z", "+00:00")) - timedelta(minutes=2)
    t1 = datetime.fromisoformat(p["time_to"].replace("Z", "+00:00")) + timedelta(minutes=2)
    data = {"type": "sentinel-1-grd",
            "dataFilter": {"timeRange": {"from": t0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                         "to": t1.strftime("%Y-%m-%dT%H:%M:%SZ")},
                           "acquisitionMode": "IW", "polarization": "DV", "resolution": "HIGH",
                           "orbitDirection": p["orbit_direction"]},
            "processing": {"orthorectify": True, "demInstance": cfg["processing"]["dem"],
                           "backCoeff": cfg["processing"]["backscatter"]}}
    arr = _fetch_mosaic(sess, grid, data, S1_EVALSCRIPT, 3, "float32", log)
    arr[0][arr[2] == 0] = np.nan
    arr[1][arr[2] == 0] = np.nan
    with rasterio.open(out_path, "w", **grid.profile("float32", 3)) as dst:
        dst.write(arr)
        dst.descriptions = ("VV_linear_gamma0", "VH_linear_gamma0", "valid")


def download_s2(sess, grid, centre_date: str, window_days: int, max_cloud: int, out_path, log=print):
    d = datetime.fromisoformat(centre_date)
    data = {"type": "sentinel-2-l2a",
            "dataFilter": {"timeRange": {"from": (d - timedelta(days=window_days)).strftime("%Y-%m-%dT00:00:00Z"),
                                         "to": (d + timedelta(days=window_days)).strftime("%Y-%m-%dT23:59:59Z")},
                           "maxCloudCoverage": max_cloud, "mosaickingOrder": "leastCC"}}
    arr = _fetch_mosaic(sess, grid, data, S2_EVALSCRIPT, 5, "uint16", log)
    with rasterio.open(out_path, "w", **grid.profile("uint16", 5)) as dst:
        dst.write(arr)
        dst.descriptions = ("B02", "B03", "B04", "B08", "valid")
