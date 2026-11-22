"""GIS files, alerts, evidence chips and figures."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.patches import FancyArrow, Patch, Rectangle
from pyproj import Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject

from .change import LAND_TO_WATER, WATER_TO_LAND

C_NEW_LAND = "#E69F00"   # Okabe-Ito orange: water became land
C_NEW_WATER = "#0072B2"  # Okabe-Ito blue: land became water


# ---------------------------------------------------------------- rasters and vectors

def write_cog(path, arr, grid, dtype, nodata=None, description=None):
    tmp = Path(path).with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **grid.profile(dtype, 1, nodata)) as dst:
        dst.write(arr.astype(dtype), 1)
        if description:
            dst.set_band_description(1, description)
    with rasterio.open(tmp) as src:
        prof = src.profile.copy()
        prof.update(driver="COG", compress="deflate")
        for k in ("tiled", "blockxsize", "blockysize"):
            prof.pop(k, None)
        with rasterio.open(path, "w", **prof) as dst:
            dst.write(src.read())
            dst.descriptions = src.descriptions
    tmp.unlink()


def write_vectors(gdf, out_dir: Path):
    wgs = gdf.to_crs("EPSG:4326")
    cols = [c for c in ["id", "cls", "area_ha", "confidence", "priority", "dist_boundary_km", "geometry"] if c in wgs]
    wgs = wgs[cols]
    wgs.to_file(out_dir / "change_polygons.geojson", driver="GeoJSON")
    wgs.to_file(out_dir / "change_polygons.gpkg", driver="GPKG", layer="change_polygons")
    kml = wgs.rename(columns={"id": "Name"})
    kml["Description"] = [f"{r.cls}, {r.area_ha:.2f} ha, confidence {r.confidence:.2f}, priority {r.priority}"
                          for r in wgs.itertuples()]
    kml.to_file(out_dir / "change_polygons.kml", driver="KML")
    return wgs


# ---------------------------------------------------------------- figures helpers

def _stretch(db, lo=-25, hi=0):
    return np.clip((db - lo) / (hi - lo), 0, 1)


def _extent(grid):
    x0, y0, x1, y1 = grid.bounds
    return [x0 / 1000, x1 / 1000, y0 / 1000, y1 / 1000]  # km


def _decorate(ax, grid, cfg, show_places=True, boundary=None):
    ext = _extent(grid)
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_xticks([])
    ax.set_yticks([])
    # scale bar: 5 km
    sx, sy = ext[0] + 0.05 * (ext[1] - ext[0]), ext[2] + 0.05 * (ext[3] - ext[2])
    ax.add_patch(Rectangle((sx, sy), 5, 0.012 * (ext[3] - ext[2]), color="white", ec="black", lw=0.6))
    ax.text(sx + 2.5, sy + 0.03 * (ext[3] - ext[2]), "5 km", ha="center", fontsize=7, color="white",
            bbox=dict(fc="black", alpha=0.5, lw=0, pad=1))
    # north arrow (grid north; UTM convergence here is under 2 degrees)
    nx, ny = ext[1] - 0.07 * (ext[1] - ext[0]), ext[3] - 0.16 * (ext[3] - ext[2])
    ax.add_patch(FancyArrow(nx, ny, 0, 0.08 * (ext[3] - ext[2]), width=0.6, head_width=2, head_length=1.6,
                            color="white", ec="black", lw=0.5, length_includes_head=True))
    ax.text(nx, ny - 0.03 * (ext[3] - ext[2]), "N", ha="center", fontsize=8, color="white", weight="bold")
    if show_places:
        t = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
        for p in cfg["reference"].get("places", []):
            x, y = t.transform(p["lon"], p["lat"])
            x, y = x / 1000, y / 1000
            if ext[0] < x < ext[1] and ext[2] < y < ext[3]:
                ax.plot(x, y, "o", ms=3, color="white", mec="black", mew=0.5)
                ax.text(x + 0.6, y + 0.4, p["name"], fontsize=7, color="white",
                        bbox=dict(fc="black", alpha=0.45, lw=0, pad=1))
    if boundary is not None and len(boundary):
        for geom in boundary.to_crs(grid.crs).geometry:
            line = geom.boundary if geom.geom_type.endswith("Polygon") else geom
            for part in getattr(line, "geoms", [line]):
                xs, ys = part.xy
                ax.plot(np.array(xs) / 1000, np.array(ys) / 1000, color="#CC79A7", lw=1.0, ls="--")


def change_overlay(cls):
    rgba = np.zeros(cls.shape + (4,), dtype="float32")
    for k, c in ((WATER_TO_LAND, C_NEW_LAND), (LAND_TO_WATER, C_NEW_WATER)):
        rgb = matplotlib.colors.to_rgb(c)
        rgba[cls == k] = (*rgb, 1.0)
    return rgba


def overview_panel(path, before_db, after_db, cls, grid, cfg, meta, boundary=None):
    pb, pa = cfg["periods"]["before"], cfg["periods"]["after"]
    fig, axes = plt.subplots(1, 3, figsize=(11.69, 5.2), dpi=300)
    ext = _extent(grid)
    titles = [f"Before: {pb['label']}\n{pb['start']} to {pb['end']}, mean of {meta['n_before']} scenes",
              f"After: {pa['label']}\n{pa['start']} to {pa['end']}, mean of {meta['n_after']} scenes",
              "Change between periods\n(frequency rule, patches ≥ %.1f ha)" % cfg["change"]["min_area_ha"]]
    axes[0].imshow(_stretch(before_db), cmap="gray", extent=ext, interpolation="nearest")
    axes[1].imshow(_stretch(after_db), cmap="gray", extent=ext, interpolation="nearest")
    axes[2].imshow(_stretch(after_db) * 0.55 + 0.25, cmap="gray", vmin=0, vmax=1, extent=ext, interpolation="nearest")
    axes[2].imshow(change_overlay(cls), extent=ext, interpolation="nearest")
    for ax, t in zip(axes, titles):
        ax.set_title(t, fontsize=8.5)
        _decorate(ax, grid, cfg, boundary=boundary)
    handles = [Patch(color=C_NEW_LAND, label=f"Water became land: {meta['ha_w2l']:.0f} ha"),
               Patch(color=C_NEW_WATER, label=f"Land became water: {meta['ha_l2w']:.0f} ha")]
    axes[2].legend(handles=handles, loc="lower right", fontsize=7, framealpha=0.85)
    fig.suptitle(cfg["project"]["name"], fontsize=11, weight="bold", y=0.99)
    fig.text(0.01, 0.015, f"Sentinel-1 VV backscatter (gamma0, terrain-flattened), dB stretch -25 to 0. "
                          f"Grid {grid.crs}, {grid.res:.0f} m. Orbit: {meta['orbit']}. "
                          f"{cfg['outputs']['credit']}. Processed by {cfg['project']['organisation']}.",
             fontsize=6.5, color="#333333")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(path, dpi=300)
    plt.close(fig)


def _window(geom, grid, pad_m=300, max_half_m=3000):
    """Square window (metres) around a polygon, capped in size and kept inside the grid."""
    minx, miny, maxx, maxy = geom.bounds
    half = min(max(maxx - minx, maxy - miny) / 2 + pad_m, max_half_m)
    if half >= max_half_m:  # very long polygon: centre on a point that lies inside it
        p = geom.representative_point()
        cx, cy = p.x, p.y
    else:
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    gx0, gy0, gx1, gy1 = grid.bounds
    half = min(half, (gx1 - gx0) / 2, (gy1 - gy0) / 2)
    cx = min(max(cx, gx0 + half), gx1 - half)
    cy = min(max(cy, gy0 + half), gy1 - half)
    return cx, cy, half


def _crop(img, grid, cx, cy, half):
    r0, c0 = rasterio.transform.rowcol(grid.transform, cx - half, cy + half)
    r1, c1 = rasterio.transform.rowcol(grid.transform, cx + half, cy - half)
    r0, c0 = max(0, r0), max(0, c0)
    r1, c1 = min(grid.height, r1), min(grid.width, c1)
    x0, y1 = rasterio.transform.xy(grid.transform, r0, c0, offset="ul")
    x1, y0 = rasterio.transform.xy(grid.transform, r1, c1, offset="ul")
    return img[r0:r1, c0:c1], [x0 / 1000, x1 / 1000, y0 / 1000, y1 / 1000]


def _nice_bar_m(width_m):
    for b in (5000, 2000, 1000, 500, 200, 100, 50):
        if b <= width_m / 4:
            return b
    return 50


def _outline(ax, geom, color, lw):
    for g in getattr(geom, "geoms", [geom]):
        xs, ys = g.exterior.xy
        ax.plot(np.array(xs) / 1000, np.array(ys) / 1000, color=color, lw=lw)


def zoom_panel(path, before_db, after_db, gdf, grid, cfg, n=3):
    top = gdf.head(n)
    if not len(top):
        return
    fig, axes = plt.subplots(len(top), 2, figsize=(8.27, 3.6 * len(top)), dpi=300, squeeze=False)
    for i, r in enumerate(top.itertuples()):
        cx, cy, half = _window(r.geometry, grid)
        bar = _nice_bar_m(2 * half)
        for j, (img, lab) in enumerate(((before_db, "Before"), (after_db, "After"))):
            ax = axes[i, j]
            sub, ext = _crop(img, grid, cx, cy, half)
            ax.imshow(_stretch(sub), cmap="gray", extent=ext, interpolation="nearest")
            _outline(ax, r.geometry, C_NEW_LAND if r.cls == "water_to_land" else C_NEW_WATER, 1.2)
            ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f"{r.id} {lab}: {r.cls.replace('_', ' ')}, {r.area_ha:.1f} ha, "
                         f"confidence {r.confidence:.2f}", fontsize=7.5)
            w = ext[1] - ext[0]
            x0, y0 = ext[0] + 0.06 * w, ext[2] + 0.06 * (ext[3] - ext[2])
            ax.plot([x0, x0 + bar / 1000], [y0, y0], color="white", lw=2.5, solid_capstyle="butt")
            ax.text(x0 + bar / 2000, y0 + 0.035 * w, f"{bar:,} m" if bar < 1000 else f"{bar // 1000} km",
                    color="white", ha="center", va="bottom", fontsize=6.5,
                    bbox=dict(fc="black", alpha=0.5, lw=0, pad=1))
            if half >= 2999:
                ax.text(ext[1] - 0.03 * w, ext[3] - 0.04 * w, "part of a longer polygon", ha="right", va="top",
                        fontsize=6, color="white", bbox=dict(fc="black", alpha=0.5, lw=0, pad=1))
    fig.text(0.01, 0.005, cfg["outputs"]["credit"] + ". Sentinel-1 VV gamma0, dB stretch -25 to 0.", fontsize=6)
    fig.tight_layout(rect=(0, 0.015, 1, 1))
    fig.savefig(path, dpi=300)
    plt.close(fig)


def evidence_chips(chip_dir: Path, before_db, after_db, gdf, grid, cfg):
    chip_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for r in gdf.head(cfg["outputs"]["max_evidence_chips"]).itertuples():
        cx, cy, half = _window(r.geometry, grid, pad_m=400)
        fig, axes = plt.subplots(1, 2, figsize=(5, 2.6), dpi=120)
        for ax, img, lab in ((axes[0], before_db, "before"), (axes[1], after_db, "after")):
            sub, ext = _crop(img, grid, cx, cy, half)
            ax.imshow(_stretch(sub), cmap="gray", extent=ext, interpolation="nearest")
            _outline(ax, r.geometry, "#E69F00" if r.cls == "water_to_land" else "#56B4E9", 1)
            ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_title(f"{r.id} {lab}", fontsize=7)
        fig.tight_layout()
        p = chip_dir / f"{r.id}.png"
        fig.savefig(p)
        plt.close(fig)
        paths[r.id] = f"chips/{r.id}.png"
    return paths


def alerts(gdf_wgs, chip_paths, meta, cfg):
    out = []
    for r in gdf_wgs.itertuples():
        out.append({
            "alert_id": r.id,
            "source": "satellite",
            "type": r.cls,
            "geometry": json.loads(gdf_wgs.loc[[r.Index]].to_json())["features"][0]["geometry"],
            "observed_at": meta["last_after_date"] + "T00:00:00Z",
            "confidence": r.confidence,
            "confidence_method": "mean |water frequency after - water frequency before| over the polygon",
            "priority": r.priority,
            "area_ha": round(r.area_ha, 3),
            "description": ("Surface water absent in the after period where it was present before (char growth, "
                            "bank accretion or channel drying)" if r.cls == "water_to_land" else
                            "Surface water present in the after period where land was before (bank erosion or "
                            "new channel)"),
            "evidence": {"before_scenes": meta["before_scene_ids"], "after_scenes": meta["after_scene_ids"],
                         "image_chip": chip_paths.get(r.id)},
            "model_version": meta["model_version"],
            "status": "new",
            "requires_human_verification": True,
            "audit": [{"at": meta["run_at"], "actor": "pipeline", "action": "created"}],
        })
    return out


# ---------------------------------------------------------------- web map layers

def quicklooks(out_dir: Path, grid, layers: dict, max_px: int = 2048):
    """Write PNG layers warped to Web Mercator, so a web map can place them exactly.

    layers: name -> (array, kind) with kind "db" (grey), "class" (change colours), "freq" (blue ramp),
    "rgb" (H x W x 3 in 0-1). Bounds go to bounds.json as [[south, west], [north, east]].
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    x0, y0, x1, y1 = grid.bounds
    scale = max(grid.width, grid.height) / max_px
    res = grid.res * max(scale, 1.0)
    tr, w, h = calculate_default_transform(grid.crs, "EPSG:3857", grid.width, grid.height, x0, y0, x1, y1,
                                           resolution=res * 1.04)
    t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    west, north = t.transform(tr.c, tr.f)
    east, south = t.transform(tr.c + w * tr.a, tr.f + h * tr.e)
    bounds_path = out_dir / "bounds.json"
    (bounds_path).write_text(json.dumps({"bounds": [[south, west], [north, east]], "crs": "EPSG:3857"}))

    def warp(a, nearest, nodata):
        dst = np.full((h, w), nodata, dtype="float32")
        reproject(a.astype("float32"), dst, src_transform=grid.transform, src_crs=grid.crs, src_nodata=nodata,
                  dst_transform=tr, dst_crs="EPSG:3857", dst_nodata=nodata,
                  resampling=Resampling.nearest if nearest else Resampling.average)
        return dst

    for name, (arr, kind) in layers.items():
        rgba = np.zeros((h, w, 4), dtype="float32")
        if kind == "db":
            d = warp(arr, False, np.nan)
            v = _stretch(d)
            rgba[..., :3] = np.nan_to_num(v)[..., None]
            rgba[..., 3] = np.isfinite(d)
        elif kind == "freq":
            d = warp(arr, False, np.nan)
            ok = np.isfinite(d) & (d > 0)
            rgba[ok] = np.array([0.0, 0.45, 0.70, 1.0])
            rgba[..., 3] = np.where(ok, np.clip(d, 0, 1) * 0.85, 0)
        elif kind == "class":
            d = warp(np.where(arr == 255, 0, arr), True, 0)
            for k, c in ((WATER_TO_LAND, C_NEW_LAND), (LAND_TO_WATER, C_NEW_WATER)):
                rgba[d == k] = (*matplotlib.colors.to_rgb(c), 1.0)
        elif kind == "rgb":
            for b in range(3):
                rgba[..., b] = np.nan_to_num(warp(arr[..., b], False, np.nan))
            rgba[..., 3] = rgba[..., :3].sum(-1) > 0
        plt.imsave(out_dir / f"{name}.png", np.clip(rgba, 0, 1))
