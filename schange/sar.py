"""Radar image helpers: decibels and the Lee speckle filter."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter


def to_db(linear: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10.0 * np.log10(linear)
    out[~np.isfinite(out)] = np.nan
    return out.astype("float32")


def lee_filter(intensity: np.ndarray, window: int = 5, enl: float = 4.4) -> np.ndarray:
    """Classic Lee filter on linear intensity (Lee 1980). NaN pixels stay NaN.

    W = (var - mean^2 * Cu^2) / (var * (1 + Cu^2)), Cu^2 = 1 / ENL, clipped to [0, 1].
    """
    valid = np.isfinite(intensity)
    img = np.where(valid, intensity, 0.0).astype("float64")
    v = valid.astype("float64")
    n = uniform_filter(v, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = uniform_filter(img, window) / n
        sq = uniform_filter(img * img, window) / n
    var = np.maximum(sq - mean * mean, 0.0)
    cu2 = 1.0 / enl
    with np.errstate(divide="ignore", invalid="ignore"):
        w = (var - mean * mean * cu2) / (var * (1.0 + cu2))
    w = np.clip(np.nan_to_num(w, nan=0.0), 0.0, 1.0)
    out = mean + w * (img - mean)
    out[~valid] = np.nan
    return out.astype("float32")
