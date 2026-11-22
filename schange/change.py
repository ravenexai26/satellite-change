"""Water frequency, change classes, cleaning, polygons, confidence and priority."""
from __future__ import annotations

import numpy as np
import geopandas as gpd
from rasterio import features
from scipy import ndimage
from shapely.geometry import shape

NO_CHANGE, WATER_TO_LAND, LAND_TO_WATER = 0, 1, 2
CLASS_NAMES = {WATER_TO_LAND: "water_to_land", LAND_TO_WATER: "land_to_water"}
NODATA = 255


class FrequencyAccumulator:
    """Running count of water / valid observations per pixel for one period."""

    def __init__(self, shape):
        self.water = np.zeros(shape, dtype="uint16")
        self.valid = np.zeros(shape, dtype="uint16")
        self.lin_sum = np.zeros(shape, dtype="float64")
        self.db_sum = np.zeros(shape, dtype="float64")
        self.db_sq = np.zeros(shape, dtype="float64")

    def add(self, mask: np.ndarray, linear: np.ndarray, db: np.ndarray):
        ok = mask != NODATA
        self.valid += ok
        self.water += (mask == 1)
        self.lin_sum[ok] += linear[ok]
        self.db_sum[ok] += db[ok]
        self.db_sq[ok] += db[ok].astype("float64") ** 2

    def frequency(self, min_valid: int) -> np.ndarray:
        f = np.full(self.water.shape, np.nan, dtype="float32")
        ok = self.valid >= min_valid
        f[ok] = self.water[ok] / self.valid[ok]
        return f

    def mean_linear(self) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            m = self.lin_sum / self.valid
        m[self.valid == 0] = np.nan
        return m.astype("float32")

    def std_db(self) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            mean = self.db_sum / self.valid
            var = self.db_sq / self.valid - mean * mean
        s = np.sqrt(np.maximum(var, 0))
        s[self.valid == 0] = np.nan
        return s.astype("float32")


def classify(f_before, f_after, before_min: float, after_max: float) -> np.ndarray:
    cls = np.full(f_before.shape, NODATA, dtype="uint8")
    ok = np.isfinite(f_before) & np.isfinite(f_after)
    cls[ok] = NO_CHANGE
    cls[ok & (f_before >= before_min) & (f_after <= after_max)] = WATER_TO_LAND
    cls[ok & (f_before <= after_max) & (f_after >= before_min)] = LAND_TO_WATER
    return cls


def remove_small(cls: np.ndarray, min_pixels: int) -> np.ndarray:
    """Drop 8-connected patches of each change class smaller than min_pixels."""
    out = cls.copy()
    s = np.ones((3, 3), dtype=bool)
    for k in (WATER_TO_LAND, LAND_TO_WATER):
        lab, n = ndimage.label(cls == k, structure=s)
        if n == 0:
            continue
        sizes = np.bincount(lab.ravel())
        small = sizes < min_pixels
        small[0] = False
        out[small[lab]] = NO_CHANGE
    return out


def polygons(cls, f_before, f_after, grid, cfg, score=None) -> gpd.GeoDataFrame:
    """One polygon per connected change patch with area, confidence and priority.

    Confidence is the mean of `score` over the patch; by default |after frequency - before frequency|.
    """
    s = np.ones((3, 3), dtype=bool)
    diff = score if score is not None else np.abs(np.nan_to_num(f_after) - np.nan_to_num(f_before))
    rows = []
    for k, name in CLASS_NAMES.items():
        lab, n = ndimage.label(cls == k, structure=s)
        if n == 0:
            continue
        idx = np.arange(1, n + 1)
        conf = ndimage.mean(diff, lab, idx)
        npx = ndimage.sum(np.ones_like(lab), lab, idx)
        for geom, val in features.shapes(lab.astype("int32"), mask=lab > 0, transform=grid.transform,
                                         connectivity=8):
            i = int(val) - 1
            rows.append(dict(cls=name, area_ha=float(npx[i] * grid.pixel_area_ha()),
                             confidence=float(round(conf[i], 3)), geometry=shape(geom), _label=int(val), _k=k))
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=grid.crs) if rows else \
        gpd.GeoDataFrame(columns=["cls", "area_ha", "confidence", "geometry"], geometry="geometry", crs=grid.crs)
    if len(gdf):
        # shapes() can split one labelled patch into several rings; merge them back
        gdf = gdf.dissolve(by=["_k", "_label"], aggfunc="first").reset_index(drop=True)
        gdf = gdf.sort_values(["area_ha", "confidence"], ascending=False).reset_index(drop=True)
        gdf.insert(0, "id", [f"sat-{i + 1:04d}" for i in range(len(gdf))])
    return gdf


def single_pair_score(db_before, db_after, t_before, t_after, margin_db=6.0):
    """Confidence for a one-image-per-date comparison: how far both pixels sit from their water thresholds.

    0 = on the threshold in at least one image, 1 = at least `margin_db` dB clear of it in both.
    """
    a = np.clip(np.abs(np.nan_to_num(db_before) - t_before) / margin_db, 0, 1)
    b = np.clip(np.abs(np.nan_to_num(db_after) - t_after) / margin_db, 0, 1)
    return np.minimum(a, b).astype("float32")


def add_priority(gdf, cfg, boundary=None):
    p = cfg["priority"]
    if not len(gdf):
        gdf["priority"] = []
        return gdf
    level = np.where((gdf.area_ha >= p["high_area_ha"]) & (gdf.confidence >= p["high_confidence"]), 2,
                     np.where((gdf.area_ha >= p["medium_area_ha"]) | (gdf.confidence >= p["high_confidence"]), 1, 0))
    if boundary is not None and len(boundary):
        b = boundary.to_crs(gdf.crs).union_all()
        dist_km = gdf.geometry.distance(b) / 1000.0
        gdf["dist_boundary_km"] = dist_km.round(2)
        level = np.where(dist_km <= p["near_boundary_km"], np.minimum(level + 1, 2), level)
    gdf["priority"] = np.array(["low", "medium", "high"])[level]
    return gdf
