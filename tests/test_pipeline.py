"""Tests: python -m pytest -q"""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from schange import change, config, sar, water
from schange.grid import from_bbox
from schange.pipeline import run_all

ROOT = Path(__file__).resolve().parents[1]


def test_lee_filter_keeps_mean_and_reduces_variance():
    rng = np.random.default_rng(0)
    img = rng.gamma(4.4, 1 / 4.4, (300, 300)).astype("float32") * 0.1
    out = sar.lee_filter(img, 5, 4.4)
    assert abs(out.mean() - img.mean()) / img.mean() < 0.02
    assert out.var() < img.var() * 0.5


def test_lee_filter_keeps_nan():
    img = np.ones((50, 50), dtype="float32")
    img[10, 10] = np.nan
    assert np.isnan(sar.lee_filter(img)[10, 10])


def test_split_otsu_finds_gap_between_water_and_land():
    rng = np.random.default_rng(1)
    db = np.where(np.arange(1000)[None, :] < 400, -21.0, -8.0) + rng.normal(0, 1.5, (1000, 1000))
    t = water.split_otsu(db.astype("float32"), tile_px=200, min_tiles=2)
    assert t.method == "split-otsu"
    assert -18 < t.value_db < -11


def test_classify_rules():
    fb = np.array([[1.0, 0.75, 0.5, 0.0, 0.25, np.nan]])
    fa = np.array([[0.0, 0.25, 0.0, 1.0, 0.75, 0.0]])
    cls = change.classify(fb, fa, 0.75, 0.25)
    assert cls.tolist() == [[1, 1, 0, 2, 2, 255]]


def test_remove_small_patches():
    cls = np.zeros((20, 20), dtype="uint8")
    cls[1:3, 1:3] = change.WATER_TO_LAND      # 4 px
    cls[10:18, 10:18] = change.LAND_TO_WATER  # 64 px
    out = change.remove_small(cls, 50)
    assert (out == change.WATER_TO_LAND).sum() == 0
    assert (out == change.LAND_TO_WATER).sum() == 64


def test_grid_snaps_to_resolution():
    g = from_bbox([89.70, 25.75, 90.10, 26.15], "EPSG:32646", 10)
    assert g.transform.c % 10 == 0 and g.transform.f % 10 == 0
    assert 3500 < g.width < 4600 and 4000 < g.height < 5000


def test_config_rejects_overlapping_periods(tmp_path):
    cfg = config.load(ROOT / "config.yaml")
    cfg["periods"]["after"]["start"] = cfg["periods"]["before"]["start"]
    with pytest.raises(config.ConfigError):
        config.check(cfg)


def test_end_to_end_on_simulated_river(tmp_path):
    cfg = config.load(ROOT / "config.yaml")
    cfg = copy.deepcopy(cfg)
    cfg["_dir"] = str(tmp_path)
    cfg["area"]["bbox"] = [89.90, 25.95, 89.98, 26.03]      # small box for speed
    cfg["scenes"]["source"] = "synthetic"
    cfg["processing"]["otsu_tile_px"] = 100
    cfg["change"]["min_area_ha"] = 0.2
    r = run_all(cfg, log=lambda *_: None)
    truth = r.score_against_truth()
    for k in ("water_to_land", "land_to_water"):
        assert truth[k]["precision"] >= 0.9, truth
        assert truth[k]["recall"] >= 0.9, truth
    out = tmp_path / "output"
    for f in ["scenes.csv", "thresholds.csv", "metrics.json", "alerts.json", "method_note.md",
              "evidence_report.pdf", "change_polygons.geojson", "change_polygons.kml", "change_polygons.gpkg",
              "rasters/change_class.tif", "figures/change_overview_A4.png", "validation/validation.csv"]:
        assert (out / f).exists(), f
    alerts = json.loads((out / "alerts.json").read_text())
    assert alerts and all(a["requires_human_verification"] for a in alerts)
    assert {"alert_id", "source", "type", "geometry", "observed_at", "confidence", "evidence",
            "model_version", "status", "audit"} <= set(alerts[0])
    m = json.loads((out / "metrics.json").read_text())
    assert m["calibration_check"]["status"] == "pass"


def test_rerun_gives_identical_polygons(tmp_path):
    cfg = config.load(ROOT / "config.yaml")
    cfg["_dir"] = str(tmp_path)
    cfg["area"]["bbox"] = [89.90, 25.95, 89.96, 26.01]
    cfg["scenes"]["source"] = "synthetic"
    cfg["processing"]["otsu_tile_px"] = 100
    a = run_all(cfg, log=lambda *_: None).state["gdf"]
    b = run_all(cfg, log=lambda *_: None).state["gdf"]
    assert len(a) == len(b) and np.allclose(a.area_ha.values, b.area_ha.values)
    assert all(x.equals(y) for x, y in zip(a.geometry, b.geometry))
