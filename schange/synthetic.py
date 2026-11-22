"""A simulated braided river with known changes, used to test the whole pipeline.

Builds a channel network and sand islands (chars) on the real analysis grid, moves them between
'before' and 'after', and renders radar scenes with realistic speckle plus two deliberate traps:
wind-roughened water in one scene and a dark wet sandbar in another. The true change map is
saved so the pipeline's output can be scored against it.
"""
from __future__ import annotations

import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter

from .change import LAND_TO_WATER, NO_CHANGE, WATER_TO_LAND


def _river(shape, shift, chars, rng):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    centre = w * 0.5 + w * 0.12 * np.sin(yy / h * 2.6 * np.pi) + shift
    half_width = w * (0.11 + 0.03 * np.sin(yy / h * 5 * np.pi + 1))
    water = np.abs(xx - centre) < half_width
    side = np.abs(xx - (centre + w * 0.2)) < w * 0.018  # a secondary channel
    water |= side & (yy > h * 0.2) & (yy < h * 0.75)
    for cy, cx, ry, rx in chars:
        water &= ((yy - cy * h) / (ry * h)) ** 2 + ((xx - cx * w) / (rx * w)) ** 2 > 1
    return water


def truth_maps(shape, seed=7):
    rng = np.random.default_rng(seed)
    before = _river(shape, 0.0, [(0.30, 0.50, 0.05, 0.03), (0.62, 0.47, 0.04, 0.025)], rng)
    after = _river(shape, shape[1] * 0.025,
                   [(0.30, 0.50, 0.07, 0.045), (0.80, 0.55, 0.035, 0.03)], rng)  # char grows, a new char appears
    cls = np.full(shape, NO_CHANGE, dtype="uint8")
    cls[before & ~after] = WATER_TO_LAND
    cls[~before & after] = LAND_TO_WATER
    return before, after, cls


def _scene(water, rng, wind=False, wet_sand=None):
    h, w = water.shape
    land_db = -8.5 + 2.0 * gaussian_filter(rng.standard_normal((h, w)), 25) * 3
    water_db = np.full((h, w), -21.0)
    if wind:
        water_db += 7.0 * (gaussian_filter(rng.standard_normal((h, w)), 40) > 0.004)
    db = np.where(water, water_db, land_db)
    if wet_sand is not None:
        db[wet_sand] = -19.0
    lin = 10 ** (db / 10)
    speckle = rng.gamma(shape=4.4, scale=1 / 4.4, size=(h, w))  # GRDH ENL ~4.4
    vv = (lin * speckle).astype("float32")
    vh = (lin * 10 ** (-7 / 10) * rng.gamma(4.4, 1 / 4.4, size=(h, w))).astype("float32")
    return vv, vh


def make(grid, work_dir, n_before=4, n_after=4, seed=11):
    rng = np.random.default_rng(seed)
    before, after, cls = truth_maps(grid.shape)
    h, w = grid.shape
    yy, xx = np.mgrid[0:h, 0:w]
    sandbar = ((yy - 0.45 * h) / (0.03 * h)) ** 2 + ((xx - 0.80 * w) / (0.03 * w)) ** 2 < 1
    sandbar &= ~before & ~after
    passes = []
    dates = {"before": ["2025-10-19", "2025-10-31", "2025-11-12", "2025-11-24"][:n_before],
             "after": ["2026-10-20", "2026-11-01", "2026-11-13", "2026-11-19"][:n_after]}
    for period, water in (("before", before), ("after", after)):
        for k, d in enumerate(dates[period]):
            vv, vh = _scene(water, rng, wind=(period == "before" and k == 1),
                            wet_sand=sandbar if (period == "after" and k == 2) else None)
            path = work_dir / "scenes" / period / f"{d}_SIM_ASC_041.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(path, "w", **grid.profile("float32", 3)) as dst:
                dst.write(np.stack([vv, vh, np.ones_like(vv)]))
            passes.append({"period": period, "date": d, "satellite": "SIM", "orbit_direction": "ASCENDING",
                           "relative_orbit": 41, "aoi_coverage": 1.0, "scene_ids": f"SIMULATED_{d}",
                           "path": str(path), "selected": True})
    # simulated optical reference: true water + 3% label noise, for testing auto-validation
    for period, water in (("before", before), ("after", after)):
        noisy = water ^ (rng.random(water.shape) < 0.03)
        nir = np.where(noisy, 300, 2500).astype("uint16")
        green = np.where(noisy, 900, 700).astype("uint16")
        arr = np.stack([np.full_like(nir, 600), green, np.full_like(nir, 650), nir, np.ones_like(nir)])
        p = work_dir / "sentinel2" / f"s2_{period}.tif"
        p.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(p, "w", **grid.profile("uint16", 5)) as dst:
            dst.write(arr)
    with rasterio.open(work_dir / "truth_change.tif", "w", **grid.profile("uint8")) as dst:
        dst.write(cls, 1)
    return passes
