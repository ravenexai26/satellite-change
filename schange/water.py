"""Water mapping by split-based Otsu thresholding of backscatter in dB."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.filters import threshold_otsu


@dataclass
class Threshold:
    value_db: float
    method: str            # "split-otsu" or "global-otsu"
    tiles_used: int
    in_expected_range: bool


def _ashman_d(x: np.ndarray, t: float) -> tuple[float, float]:
    lo, hi = x[x < t], x[x >= t]
    if lo.size < 50 or hi.size < 50:
        return 0.0, 0.0
    d = np.sqrt(2.0) * abs(hi.mean() - lo.mean()) / np.sqrt(lo.var() + hi.var())
    return float(d), lo.size / x.size


def split_otsu(db: np.ndarray, tile_px: int = 200, min_tiles: int = 5,
               expected=(-26.0, -12.0), max_samples: int = 2_000_000, seed: int = 0) -> Threshold:
    """Pick tiles that clearly contain both water and land, then run Otsu on their pooled pixels.

    A tile qualifies when its own Otsu split gives Ashman's D > 2 and each class holds
    10-90% of the tile. Falls back to a global Otsu if fewer than `min_tiles` qualify.
    """
    h, w = db.shape
    pooled = []
    for r in range(0, h - tile_px + 1, tile_px):
        for c in range(0, w - tile_px + 1, tile_px):
            t = db[r:r + tile_px, c:c + tile_px]
            x = t[np.isfinite(t)]
            if x.size < 0.9 * t.size:
                continue
            try:
                tt = threshold_otsu(x)
            except ValueError:
                continue
            d, frac = _ashman_d(x, tt)
            if d > 2.0 and 0.1 <= frac <= 0.9:
                pooled.append(x)
    rng = np.random.default_rng(seed)
    if len(pooled) >= min_tiles:
        x = np.concatenate(pooled)
        method, n = "split-otsu", len(pooled)
    else:
        x = db[np.isfinite(db)]
        method, n = "global-otsu", 0
    if x.size > max_samples:
        x = rng.choice(x, max_samples, replace=False)
    value = float(threshold_otsu(x))
    return Threshold(value, method, n, expected[0] <= value <= expected[1])


def water_mask(db: np.ndarray, threshold_db: float) -> np.ndarray:
    """1 = water, 0 = land, 255 = no data."""
    out = np.full(db.shape, 255, dtype="uint8")
    ok = np.isfinite(db)
    out[ok] = (db[ok] < threshold_db).astype("uint8")
    return out
