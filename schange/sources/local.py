"""Use your own calibrated radar GeoTIFFs instead of downloading.

Works with ASF HyP3 RTC, ESA SNAP output, or any other calibrated SAR (for example ISRO EOS-04
C-band data from NRSC), as long as each file holds backscatter in linear power units.
List the files in a CSV (`local_scenes.csv`) with these columns:

    path,date,period,satellite,orbit_direction,relative_orbit,vv_band,vh_band,units
    data/S1C_20251101_VV_VH.tif,2025-11-01,before,S1C,ASCENDING,41,1,2,linear

`vh_band` may be empty. `units` is "linear" or "db". HyP3 writes one file per polarisation; in that
case add the VH file path in an optional `vh_path` column and set vh_band to 1.
"""
from __future__ import annotations

import csv

import numpy as np
import rasterio

from ..grid import warp_to_grid
from ..config import resolve


def read_manifest(cfg) -> list[dict]:
    path = resolve(cfg, cfg["scenes"]["local_manifest"])
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["path"] = str(resolve(cfg, r["path"]))
        if r.get("vh_path"):
            r["vh_path"] = str(resolve(cfg, r["vh_path"]))
    return rows


def to_scene(row: dict, grid, out_path):
    vv = warp_to_grid(row["path"], grid, [int(row["vv_band"])])[0]
    vh = np.full(grid.shape, np.nan, dtype="float32")
    if row.get("vh_band"):
        vh = warp_to_grid(row.get("vh_path") or row["path"], grid, [int(row["vh_band"])])[0]
    if row.get("units", "linear").lower() == "db":
        vv, vh = 10 ** (vv / 10), 10 ** (vh / 10)
    vv[vv <= 0] = np.nan
    valid = np.isfinite(vv).astype("float32")
    with rasterio.open(out_path, "w", **grid.profile("float32", 3)) as dst:
        dst.write(np.stack([vv, vh, valid]).astype("float32"))
        dst.descriptions = ("VV_linear_gamma0", "VH_linear_gamma0", "valid")
