"""The single analysis grid every image is placed on."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from shapely.geometry import box


@dataclass(frozen=True)
class Grid:
    crs: str
    transform: rasterio.Affine
    width: int
    height: int
    res: float

    @property
    def shape(self):
        return (self.height, self.width)

    @property
    def bounds(self):
        x0, y1 = self.transform.c, self.transform.f
        return (x0, y1 - self.height * self.res, x0 + self.width * self.res, y1)

    def profile(self, dtype="float32", count=1, nodata=None):
        p = dict(driver="GTiff", crs=self.crs, transform=self.transform, width=self.width,
                 height=self.height, count=count, dtype=dtype, compress="deflate", tiled=True,
                 blockxsize=512, blockysize=512)
        if nodata is not None:
            p["nodata"] = nodata
        return p

    def pixel_area_ha(self) -> float:
        return self.res * self.res / 10_000.0


def from_bbox(bbox_lonlat, crs: str, res: float) -> Grid:
    """Snap the lon/lat box to a whole-metre grid in the target CRS."""
    w, s, e, n = bbox_lonlat
    t = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = t.transform([w, e, e, w, (w + e) / 2, (w + e) / 2], [s, s, n, n, s, n])
    x0 = np.floor(min(xs) / res) * res
    x1 = np.ceil(max(xs) / res) * res
    y0 = np.floor(min(ys) / res) * res
    y1 = np.ceil(max(ys) / res) * res
    width, height = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    return Grid(crs, from_origin(x0, y1, res, res), width, height, res)


def aoi_polygon_lonlat(bbox):
    return box(*bbox)


def warp_to_grid(src_path, grid: Grid, band_indexes, resampling=Resampling.bilinear):
    """Read bands from any GeoTIFF and resample them onto the grid. Returns float32 (bands, H, W)."""
    out = np.full((len(band_indexes),) + grid.shape, np.nan, dtype="float32")
    with rasterio.open(src_path) as src:
        for i, b in enumerate(band_indexes):
            reproject(source=rasterio.band(src, b), destination=out[i], dst_transform=grid.transform,
                      dst_crs=grid.crs, dst_nodata=np.nan, resampling=resampling,
                      src_nodata=src.nodata)
    return out
