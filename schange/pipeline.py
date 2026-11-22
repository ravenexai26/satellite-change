"""Run the stages: search -> download -> process -> outputs -> validate."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

from . import __version__, change, calib, outputs, report, synthetic, validation
from .config import fingerprint, resolve
from .grid import from_bbox
from .sar import lee_filter, to_db
from .water import split_otsu, water_mask

SCENE_FIELDS = ["period", "date", "satellite", "orbit_direction", "relative_orbit", "aoi_coverage",
                "scene_ids", "selected", "path"]


class Run:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.out = resolve(cfg, cfg["project"]["output_dir"])
        a = cfg["area"]
        self.grid = from_bbox(a["bbox"], a["crs"], a["resolution_m"])
        # cache per grid, so changing the area or resolution never reuses images made for another grid
        gkey = "grid_" + hashlib.sha1(f"{a['bbox']}|{a['crs']}|{a['resolution_m']}|{cfg['scenes']['source']}"
                                      .encode()).hexdigest()[:10]
        self.work = resolve(cfg, cfg["project"]["work_dir"]) / gkey
        self.out.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        self.simulated = cfg["scenes"]["source"] == "synthetic"
        self.log(f"Grid {self.grid.width} x {self.grid.height} px at {self.grid.res} m in {self.grid.crs}")

    # ------------------------------------------------------------ search
    def search(self):
        src = self.cfg["scenes"]["source"]
        if src == "synthetic":
            n = 1 if self.cfg["scenes"]["min_per_period"] == 1 else 4
            passes = synthetic.make(self.grid, self.work, n_before=n, n_after=n)
        elif src == "local":
            from .sources import local
            passes = []
            for r in local.read_manifest(self.cfg):
                passes.append({"period": r["period"], "date": r["date"], "satellite": r.get("satellite", ""),
                               "orbit_direction": r.get("orbit_direction", ""),
                               "relative_orbit": r.get("relative_orbit", ""), "aoi_coverage": "",
                               "scene_ids": Path(r["path"]).stem, "selected": True, "path": "", "_row": r})
        else:
            from .sources import cdse
            passes = []
            for period in ("before", "after"):
                p = self.cfg["periods"][period]
                for ps in cdse.group_passes(cdse.search_s1(self.cfg["area"]["bbox"], p["start"], p["end"], self.log),
                                            self.cfg["area"]["bbox"]):
                    ps["period"] = period
                    passes.append(ps)
            self._select_orbit(passes)
        self._write_scenes(passes)
        sel = [p for p in passes if p["selected"]]
        nb = sum(p["period"] == "before" for p in sel)
        na = sum(p["period"] == "after" for p in sel)
        self.log(f"Selected {nb} before and {na} after acquisitions -> {self.out / 'scenes.csv'}")
        if min(nb, na) < self.cfg["scenes"]["min_per_period"]:
            raise SystemExit(f"STOP: need at least {self.cfg['scenes']['min_per_period']} scenes per period "
                             f"on one orbit; found {nb} before, {na} after. Widen the dates or change the orbit.")
        self.passes = passes
        return passes

    def _select_orbit(self, passes):
        sc = self.cfg["scenes"]
        ok = [p for p in passes if p["aoi_coverage"] >= sc["min_aoi_coverage"]]
        keys = {}
        for p in ok:
            k = (p["orbit_direction"], p["relative_orbit"])
            keys.setdefault(k, {"before": 0, "after": 0})[p["period"]] += 1
        if sc.get("orbit_direction") and sc.get("relative_orbit") is not None:
            best = (sc["orbit_direction"].upper(), int(sc["relative_orbit"]))
        elif keys:
            best = max(keys, key=lambda k: (min(keys[k].values()), sum(keys[k].values())))
        else:
            best = None
        for p in passes:
            p["selected"] = best is not None and p in ok and (p["orbit_direction"], p["relative_orbit"]) == best
            p["path"] = ""
        self.log(f"  orbit candidates (direction, relative orbit): {keys}; chosen {best}")

    def _write_scenes(self, passes):
        with open(self.out / "scenes.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SCENE_FIELDS, extrasaction="ignore")
            w.writeheader()
            for p in sorted(passes, key=lambda x: (not x["selected"], x["period"] != "before", x["date"])):
                w.writerow(p)

    # ------------------------------------------------------------ download
    def download(self):
        src = self.cfg["scenes"]["source"]
        sel = [p for p in self.passes if p["selected"]]
        if src == "synthetic":
            return
        if src == "local":
            from .sources import local
            for p in sel:
                path = self.work / "scenes" / p["period"] / f"{p['date']}_{Path(p['_row']['path']).stem}.tif"
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    local.to_scene(p["_row"], self.grid, path)
                p["path"] = str(path)
            self._write_scenes(self.passes)
            return
        from .sources import cdse
        sess = cdse.Session()
        for i, p in enumerate(sel, 1):
            path = self.work / "scenes" / p["period"] / \
                f"{p['date']}_{p['satellite']}_{p['orbit_direction'][:3]}_{p['relative_orbit']}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                self.log(f"  [{i}/{len(sel)}] downloading {path.name}")
                cdse.download_pass(sess, self.grid, p, self.cfg, path, self.log)
            p["path"] = str(path)
        self._write_scenes(self.passes)
        v = self.cfg["validation"]
        for period in ("before", "after"):
            path = self.work / "sentinel2" / f"s2_{period}.tif"
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            dates = sorted(p["date"] for p in sel if p["period"] == period)
            centre = dates[len(dates) // 2]
            self.log(f"  downloading Sentinel-2 reference for {period} around {centre}")
            try:
                cdse.download_s2(sess, self.grid, centre, v["sentinel2_window_days"], v["sentinel2_max_cloud"],
                                 path, self.log)
            except cdse.CDSEError as e:
                self.log(f"  Sentinel-2 download failed ({e}); optical cross-check will be skipped")

    # ------------------------------------------------------------ process
    def process(self):
        cfg, g = self.cfg, self.grid
        pc = cfg["processing"]
        acc = {"before": change.FrequencyAccumulator(g.shape), "after": change.FrequencyAccumulator(g.shape)}
        thr_rows = []
        for p in sorted([p for p in self.passes if p["selected"]], key=lambda x: x["date"]):
            with rasterio.open(p["path"]) as src:
                vv, vh = src.read(1), src.read(2)
            vv_f = lee_filter(vv, pc["speckle_filter"]["window"], pc["speckle_filter"]["enl"])
            db = to_db(vv_f)
            t = split_otsu(db, pc["otsu_tile_px"], pc["otsu_min_tiles"], tuple(pc["expected_threshold_db"]))
            mask = water_mask(db, t.value_db)
            row = {"date": p["date"], "period": p["period"], "satellite": p["satellite"], "band": "VV",
                   "threshold_db": round(t.value_db, 3), "method": t.method, "tiles_used": t.tiles_used,
                   "in_expected_range": t.in_expected_range, "water_share": round(float((mask == 1).mean()), 4)}
            if pc.get("use_vh_confirmation") and np.isfinite(vh).any():
                db_vh = to_db(lee_filter(vh, pc["speckle_filter"]["window"], pc["speckle_filter"]["enl"]))
                t2 = split_otsu(db_vh, pc["otsu_tile_px"], pc["otsu_min_tiles"], (-35, -18))
                vh_mask = water_mask(db_vh, t2.value_db)
                mask = np.where((mask == 1) & (vh_mask == 0), 0, mask).astype("uint8")
                row["vh_threshold_db"] = round(t2.value_db, 3)
            if not t.in_expected_range:
                self.log(f"  WARNING {p['date']}: threshold {t.value_db:.2f} dB outside expected range")
            self.log(f"  {p['period']:6s} {p['date']} threshold {t.value_db:6.2f} dB ({t.method}, "
                     f"{t.tiles_used} tiles), water {row['water_share']:.1%}")
            thr_rows.append(row)
            acc[p["period"]].add(mask, vv_f, db)
        with open(self.out / "thresholds.csv", "w", newline="", encoding="utf-8") as f:
            fields = list(dict.fromkeys(k for r in thr_rows for k in r))
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(thr_rows)
        mv = cfg["scenes"]["min_per_period"]
        fb, fa = acc["before"].frequency(mv), acc["after"].frequency(mv)
        c = cfg["change"]
        cls = change.classify(fb, fa, c["water_before_min"], c["water_after_max"])
        cls = change.remove_small(cls, int(np.ceil(c["min_area_ha"] / g.pixel_area_ha())))
        single = int(acc["before"].valid.max()) == 1 and int(acc["after"].valid.max()) == 1
        score = None
        if single:
            # one image per date: frequencies are only 0 or 1, so judge confidence by distance from the thresholds
            tb = next(r["threshold_db"] for r in thr_rows if r["period"] == "before")
            ta = next(r["threshold_db"] for r in thr_rows if r["period"] == "after")
            with np.errstate(divide="ignore", invalid="ignore"):
                score = change.single_pair_score(acc["before"].db_sum.astype("float32"),
                                                 acc["after"].db_sum.astype("float32"), tb, ta)
            self.log("  single-pair mode: one image per date; confidence from distance to the water thresholds")
        self.mode = "single_pair" if single else "multi_scene"
        gdf = change.polygons(cls, fb, fa, g, cfg, score)
        boundary = None
        if cfg["reference"].get("boundary_file"):
            boundary = gpd.read_file(resolve(cfg, cfg["reference"]["boundary_file"]))
        gdf = change.add_priority(gdf, cfg, boundary)
        cal = calib.stable_land_check(acc["before"], acc["after"], fb, fa, c["calibration_max_diff_db"])
        self.log(f"  calibration check: {cal}")
        self.state = dict(acc=acc, fb=fb, fa=fa, cls=cls, gdf=gdf, cal=cal, thr=thr_rows, boundary=boundary)

    # ------------------------------------------------------------ outputs
    def _version(self):
        try:
            h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                               cwd=Path(__file__).parent, timeout=5).stdout.strip()
        except Exception:
            h = ""
        return f"schange-{__version__}" + (f"+git.{h}" if h else "")

    def outputs(self):
        s, g, cfg, out = self.state, self.grid, self.cfg, self.out
        sel = [p for p in self.passes if p["selected"]]
        before_db = to_db(s["acc"]["before"].mean_linear())
        after_db = to_db(s["acc"]["after"].mean_linear())
        rasters = out / "rasters"
        rasters.mkdir(exist_ok=True)
        outputs.write_cog(rasters / "before_vv_db.tif", before_db, g, "float32", np.nan, "mean VV gamma0 dB, before")
        outputs.write_cog(rasters / "after_vv_db.tif", after_db, g, "float32", np.nan, "mean VV gamma0 dB, after")
        outputs.write_cog(rasters / "water_freq_before.tif", s["fb"], g, "float32", np.nan, "water frequency 0-1")
        outputs.write_cog(rasters / "water_freq_after.tif", s["fa"], g, "float32", np.nan, "water frequency 0-1")
        outputs.write_cog(rasters / "change_class.tif", s["cls"], g, "uint8", 255,
                          "0 no change, 1 water_to_land, 2 land_to_water, 255 no data")
        gdf = s["gdf"]
        ha = {k: float(gdf.loc[gdf.cls == k, "area_ha"].sum()) if len(gdf) else 0.0
              for k in ("water_to_land", "land_to_water")}
        sats = sorted({p["satellite"] for p in sel})
        orbit = f"{sel[0]['orbit_direction'].title()} relative orbit {sel[0]['relative_orbit']}" if sel else ""
        meta = dict(n_before=sum(p["period"] == "before" for p in sel), n_after=sum(p["period"] == "after" for p in sel),
                    ha_w2l=ha["water_to_land"], ha_l2w=ha["land_to_water"], orbit=orbit,
                    last_after_date=max(p["date"] for p in sel if p["period"] == "after"),
                    before_scene_ids=[p["scene_ids"] for p in sel if p["period"] == "before"],
                    after_scene_ids=[p["scene_ids"] for p in sel if p["period"] == "after"],
                    model_version=self._version(), run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        chip_paths = outputs.evidence_chips(out / "chips", before_db, after_db, gdf, g, cfg) if len(gdf) else {}
        if len(gdf):
            wgs = outputs.write_vectors(gdf, out)
            alerts = outputs.alerts(wgs, chip_paths, meta, cfg)
        else:
            alerts = []
        with open(out / "alerts.json", "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=1)
        figs = out / "figures"
        figs.mkdir(exist_ok=True)
        outputs.overview_panel(figs / "change_overview_A4.png", before_db, after_db, s["cls"], g, cfg, meta, s["boundary"])
        outputs.zoom_panel(figs / "largest_changes_A4.png", before_db, after_db, gdf, g, cfg)
        outputs.quicklooks(out / "quicklooks", g, {"before": (before_db, "db"), "after": (after_db, "db"),
                                                   "change": (s["cls"], "class"),
                                                   "water_before": (s["fb"], "freq"), "water_after": (s["fa"], "freq")})
        thr = [r["threshold_db"] for r in s["thr"]]
        self.metrics = {
            "run_at": meta["run_at"], "model_version": meta["model_version"],
            "config_fingerprint": fingerprint(cfg), "source": cfg["scenes"]["source"], "simulated": self.simulated,
            "mode": getattr(self, "mode", "multi_scene"),
            "orbit": orbit, "satellites": sats, "n_before": meta["n_before"], "n_after": meta["n_after"],
            "area_ha": {k: round(v, 2) for k, v in ha.items()},
            "polygons": {"total": int(len(gdf)),
                         **{k: int((gdf.priority == k).sum()) if len(gdf) else 0 for k in ("high", "medium", "low")},
                         "water_to_land": int((gdf.cls == "water_to_land").sum()) if len(gdf) else 0,
                         "land_to_water": int((gdf.cls == "land_to_water").sum()) if len(gdf) else 0},
            "thresholds_db": {"min": min(thr), "max": max(thr), "all_in_expected_range":
                              all(r["in_expected_range"] for r in s["thr"])},
            "calibration_check": s["cal"],
            "environment": {"python": platform.python_version(), "numpy": np.__version__,
                            "rasterio": rasterio.__version__},
        }
        self.meta = meta
        self._write_reports()

    def _write_reports(self):
        with open(self.out / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2)
        note = report.method_note(self.metrics, self.cfg)
        if self.simulated:
            note = "> SIMULATED TEST RUN. These numbers describe synthetic data, not the real river.\n\n" + note
        (self.out / "method_note.md").write_text(note, encoding="utf-8")
        report.evidence_pdf(self.out / "evidence_report.pdf",
                            [self.out / "figures" / "change_overview_A4.png",
                             self.out / "figures" / "largest_changes_A4.png"], note, self.simulated)

    # ------------------------------------------------------------ validation
    def validate(self):
        s, g, cfg = self.state, self.grid, self.cfg
        chosen, pts = validation.sample(s["gdf"], s["cls"], g, cfg)
        s2b, s2a = self.work / "sentinel2" / "s2_before.tif", self.work / "sentinel2" / "s2_after.tif"
        auto, rgb_b, rgb_a = None, None, None
        if s2b.exists() and s2a.exists():
            wb, rgb_b = validation.ndwi_water(s2b)
            wa, rgb_a = validation.ndwi_water(s2a)
            outputs.quicklooks(self.out / "quicklooks", g, {"optical_before": (rgb_b, "rgb"),
                                                            "optical_after": (rgb_a, "rgb")})
            poly_res, nc_res = validation.auto_check(s["gdf"], pts, s["cls"], g, wb, wa)
            auto = (poly_res, nc_res)
            pv = [v for _, v in poly_res if v is not None]
            nv = [v for _, v in nc_res if v is not None]
            self.metrics["validation"] = {"optical_auto": {
                "polygons_checked": len(pv), "polygons_agree": int(sum(v > 0.5 for v in pv)),
                "polygon_agreement_rate": round(sum(v > 0.5 for v in pv) / len(pv), 3) if pv else None,
                "nochange_checked": len(nv), "nochange_agree": int(sum(nv)),
                "method": "Sentinel-2 L2A NDWI > 0 as water, least-cloud mosaic per period; a polygon agrees when "
                          "more than half its pixels changed the same way"}}
            self.log(f"  optical cross-check: {self.metrics['validation']['optical_auto']}")
        else:
            self.metrics["validation"] = {}
            self.log("  no Sentinel-2 reference; optical cross-check skipped")
        validation.write_kit(self.out / "validation", chosen, pts, g, cfg, rgb_b, rgb_a, auto)
        self._write_reports()

    def score_manual(self):
        res = validation.score(self.out / "validation" / "validation.csv")
        self.metrics = json.loads((self.out / "metrics.json").read_text())
        self.metrics.setdefault("validation", {})["manual"] = res
        self._write_reports()
        return res

    # ------------------------------------------------------------ simulated truth
    def score_against_truth(self):
        truth_path = self.work / "truth_change.tif"
        if not truth_path.exists():
            return None
        with rasterio.open(truth_path) as src:
            truth = src.read(1)
        pred = self.state["cls"]
        res = {}
        for k, name in change.CLASS_NAMES.items():
            tp = int(((pred == k) & (truth == k)).sum())
            fp = int(((pred == k) & (truth != k)).sum())
            fn = int(((pred != k) & (truth == k)).sum())
            res[name] = {"precision": round(tp / (tp + fp), 3) if tp + fp else None,
                         "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                         "true_ha": round((truth == k).sum() * self.grid.pixel_area_ha(), 1),
                         "mapped_ha": round((pred == k).sum() * self.grid.pixel_area_ha(), 1)}
        res["overall_accuracy"] = round(float((pred == truth).mean()), 4)
        with open(self.out / "synthetic_truth_score.json", "w") as f:
            json.dump(res, f, indent=2)
        return res


def write_status(out: Path, stage: str, state: str, message: str = ""):
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "status.json.tmp"
    tmp.write_text(json.dumps({"stage": stage, "state": state, "message": message,
                               "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))
    tmp.replace(out / "status.json")


def run_all(cfg, stage="all", log=print):
    t0 = time.time()
    out = resolve(cfg, cfg["project"]["output_dir"])
    current = "start"
    try:
        r = Run(cfg, log)
        steps = [("search", r.search)]
        if stage != "search":
            steps += [("download", r.download), ("process", r.process), ("outputs", r.outputs),
                      ("validate", r.validate)]
        for current, fn in steps:
            write_status(out, current, "running")
            log(f"== {current}")
            fn()
        if stage == "search":
            write_status(out, "search", "done", "Scene list ready for review")
            log("Stopped after search. Review scenes.csv, then run again without --stage.")
            return r
        if r.simulated:
            log(f"  simulated truth score: {r.score_against_truth()}")
        write_status(out, "finished", "done", f"Completed in {time.time() - t0:.0f} s")
        log(f"Done in {time.time() - t0:.0f} s. Results in {r.out}")
        return r
    except BaseException as e:
        write_status(out, current, "failed", str(e)[:500])
        raise
