"""Validation kit.

1. Automatic optical cross-check: Sentinel-2 NDWI water maps of both periods, compared pixel by pixel
   with every change polygon and with a sample of no-change points. Independent sensor, so a good
   check of the radar result, but NDWI is itself a classifier and clouds/shadows can mislead it.
2. Manual check: a random sample written to validation.csv with labelling sheets (before/after
   true-colour chips). A person fills the `label` column; `run.py --stage score` computes accuracy.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio import features
from scipy.ndimage import binary_dilation

from .change import LAND_TO_WATER, NO_CHANGE, WATER_TO_LAND


def ndwi_water(s2_path):
    with rasterio.open(s2_path) as src:
        b02, b03, b04, b08, valid = src.read().astype("float32")
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (b03 - b08) / (b03 + b08)
    water = np.where(valid > 0, (ndwi > 0).astype("uint8"), 255)
    rgb = np.stack([b04, b03, b02], -1) / 2500.0
    return water, np.clip(rgb, 0, 1)


def sample(gdf, cls, grid, cfg):
    v = cfg["validation"]
    rng = np.random.default_rng(v["seed"])
    n = min(v["sample_change"], len(gdf))
    chosen = gdf.iloc[sorted(rng.choice(len(gdf), n, replace=False))] if n else gdf.iloc[:0]
    buf = max(1, int(round(v["nochange_buffer_m"] / grid.res)))
    near = binary_dilation(np.isin(cls, [WATER_TO_LAND, LAND_TO_WATER]), iterations=buf)
    rows, cols = np.nonzero((cls == NO_CHANGE) & ~near)
    pick = rng.choice(rows.size, min(v["sample_nochange"], rows.size), replace=False)
    pts = [(int(rows[i]), int(cols[i])) for i in sorted(pick)]
    return chosen, pts


def auto_check(gdf, pts, cls, grid, w_before, w_after):
    """Share of each polygon's pixels whose NDWI water state changed the same way."""
    res = []
    for r in gdf.itertuples():
        m = features.geometry_mask([r.geometry], grid.shape, grid.transform, invert=True)
        ok = m & (w_before != 255) & (w_after != 255)
        if ok.sum() == 0:
            res.append((r.id, None))
            continue
        if r.cls == "water_to_land":
            agree = (w_before[ok] == 1) & (w_after[ok] == 0)
        else:
            agree = (w_before[ok] == 0) & (w_after[ok] == 1)
        res.append((r.id, float(agree.mean())))
    nochange = []
    for i, (rr, cc) in enumerate(pts):
        b, a = w_before[rr, cc], w_after[rr, cc]
        nochange.append((f"nc-{i + 1:03d}", None if 255 in (b, a) else bool(b == a)))
    return res, nochange


def write_kit(out_dir: Path, chosen, pts, grid, cfg, rgb_before=None, rgb_after=None, auto=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    from pyproj import Transformer
    t = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    rows = []
    auto_poly = dict(auto[0]) if auto else {}
    auto_nc = dict(auto[1]) if auto else {}
    for r in chosen.itertuples():
        c = r.geometry.representative_point()
        lon, lat = t.transform(c.x, c.y)
        rows.append(dict(sample_id=r.id, kind="change", expected=r.cls, lon=round(lon, 6), lat=round(lat, 6),
                         auto_optical_agreement=None if auto_poly.get(r.id) is None else round(auto_poly[r.id], 3),
                         label="", notes=""))
    for i, (rr, cc) in enumerate(pts):
        x, y = rasterio.transform.xy(grid.transform, rr, cc)
        lon, lat = t.transform(x, y)
        sid = f"nc-{i + 1:03d}"
        rows.append(dict(sample_id=sid, kind="no_change", expected="no_change", lon=round(lon, 6),
                         lat=round(lat, 6), auto_optical_agreement=auto_nc.get(sid), label="", notes=""))
    with open(out_dir / "validation.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    if rgb_before is not None:
        _sheets(out_dir, rows, chosen, pts, grid, rgb_before, rgb_after)
    return rows


def _sheets(out_dir, rows, chosen, pts, grid, rgb_b, rgb_a, per_page=6):
    geoms = {r.id: r.geometry for r in chosen.itertuples()}
    for page in range(0, len(rows), per_page):
        chunk = rows[page:page + per_page]
        fig, axes = plt.subplots(len(chunk), 2, figsize=(6, 2.6 * len(chunk)), dpi=110, squeeze=False)
        for i, row in enumerate(chunk):
            if row["kind"] == "change":
                g = geoms[row["sample_id"]]
                cx, cy = g.representative_point().x, g.representative_point().y
                half = max(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1]) / 2 + 300
            else:
                k = int(row["sample_id"].split("-")[1]) - 1
                cx, cy = rasterio.transform.xy(grid.transform, *pts[k])
                g, half = None, 400
            rr, cc = rasterio.transform.rowcol(grid.transform, cx, cy)
            hp = int(half / grid.res)
            r0, r1 = max(0, rr - hp), min(grid.height, rr + hp)
            c0, c1 = max(0, cc - hp), min(grid.width, cc + hp)
            for j, (rgb, lab) in enumerate(((rgb_b, "before"), (rgb_a, "after"))):
                ax = axes[i, j]
                ax.imshow(rgb[r0:r1, c0:c1], interpolation="nearest")
                if g is not None:
                    for part in getattr(g, "geoms", [g]):
                        xs, ys = part.exterior.xy
                        pr = [rasterio.transform.rowcol(grid.transform, x, y) for x, y in zip(xs, ys)]
                        ax.plot([p[1] - c0 for p in pr], [p[0] - r0 for p in pr], color="yellow", lw=1)
                else:
                    ax.plot(cc - c0, rr - r0, "+", color="yellow", ms=10, mew=1.5)
                ax.set_xticks([]); ax.set_yticks([])
                ax.set_title(f"{row['sample_id']} ({row['expected']}) Sentinel-2 {lab}", fontsize=7)
        fig.tight_layout()
        fig.savefig(out_dir / f"labelling_sheet_{page // per_page + 1:02d}.png")
        plt.close(fig)


def score(csv_path: Path) -> dict:
    """Score a filled validation.csv. `label` must be: correct / wrong / unclear."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for kind in ("change", "no_change"):
        lab = [r["label"].strip().lower() for r in rows if r["kind"] == kind]
        judged = [x for x in lab if x in ("correct", "wrong")]
        out[kind] = {"samples": len(lab), "judged": len(judged), "correct": judged.count("correct"),
                     "accuracy": round(judged.count("correct") / len(judged), 3) if judged else None,
                     "unclear": lab.count("unclear"), "unlabelled": lab.count("")}
    return out
