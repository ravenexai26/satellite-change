"""Web API for the Ravenex Satellite Change web app.

Wraps the same pipeline as run.py: each analysis is a folder in runs/ with its own config.yaml, and the pipeline
runs as a separate process so the API stays responsive. The built React app (frontend/dist) is served from /.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import signal
import subprocess
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, imagery, review
from .sources import cdse
from . import config as C

ROOT = Path(__file__).resolve().parents[1]
RUNS = Path(os.environ.get("SCHANGE_RUNS_DIR", ROOT / "runs"))
BASE_CFG = ROOT / "config.yaml"
DIST = ROOT / "frontend" / "dist"
RUN_ID = re.compile(r"^[0-9]{8}-[0-9]{6}_[a-z0-9-]{1,40}$")

app = FastAPI(title="Ravenex Satellite Change API", version=__version__)
PROCS: dict[str, subprocess.Popen] = {}
CREDS: dict[str, str] = {}          # Copernicus OAuth client, held in memory only, never written to disk
TILE_CACHE = ROOT / "work" / "tiles"
MAX_QUICK_KM2 = 2500


def _creds() -> tuple[str | None, str | None]:
    return (CREDS.get("id") or os.environ.get("CDSE_CLIENT_ID"),
            CREDS.get("secret") or os.environ.get("CDSE_CLIENT_SECRET"))


_SESSION: dict[str, cdse.Session] = {}


def _session() -> cdse.Session:
    cid, sec = _creds()
    if not (cid and sec):
        raise HTTPException(503, "Connect a Copernicus account to load satellite imagery.")
    key = f"{cid}:{hash(sec)}"
    if key not in _SESSION:
        _SESSION.clear()
        _SESSION[key] = cdse.Session(cid, sec)
    return _SESSION[key]


# ------------------------------------------------------------------ helpers

def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _run_dir(run_id: str) -> Path:
    if not RUN_ID.match(run_id):
        raise HTTPException(404, "unknown analysis")
    d = RUNS / run_id
    if not (d / "config.yaml").exists():
        raise HTTPException(404, "unknown analysis")
    return d


def _status(run_id: str, d: Path) -> dict:
    s = _read_json(d / "output" / "status.json", {}) or {}
    p = PROCS.get(run_id)
    if p is not None and p.poll() is not None and s.get("state") == "running":
        s = {**s, "state": "failed", "message": f"process ended with code {p.returncode}"}
    if s.get("state") == "running" and p is None:
        # server restarted while the run was going; we can no longer follow it
        s = {**s, "state": "interrupted", "message": "the server was restarted during this run"}
    return s or {"state": "unknown"}


def _summary(run_id: str, d: Path) -> dict:
    cfg = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
    meta = _read_json(d / "run.json", {}) or {}
    m = _read_json(d / "output" / "metrics.json")
    return {
        "id": run_id, "name": meta.get("name", cfg["project"]["name"]), "created": meta.get("created"),
        "source": cfg["scenes"]["source"], "simulated": cfg["scenes"]["source"] == "synthetic",
        "stage_requested": meta.get("stage", "all"), "kind": meta.get("kind", "seasonal"),
        "bbox": cfg["area"]["bbox"], "periods": cfg["periods"],
        "status": _status(run_id, d),
        "metrics": None if m is None else {"area_ha": m["area_ha"], "polygons": m["polygons"],
                                           "n_before": m["n_before"], "n_after": m["n_after"], "orbit": m["orbit"]},
    }


def _out_file(run_id: str, rel: str) -> Path:
    out = (_run_dir(run_id) / "output").resolve()
    p = (out / rel).resolve()
    if out not in p.parents and p != out:
        raise HTTPException(400, "invalid path")
    if not p.is_file():
        raise HTTPException(404, "file not found")
    return p


def _csv_rows(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "analysis"


# ------------------------------------------------------------------ models

class Period(BaseModel):
    start: date
    end: date


class Settings(BaseModel):
    resolution_m: Literal[10, 20, 30] = 10
    min_area_ha: float = Field(0.5, gt=0, le=100)
    water_before_min: float = Field(0.75, gt=0, le=1)
    water_after_max: float = Field(0.25, ge=0, lt=1)
    min_per_period: int = Field(3, ge=2, le=20)
    orbit_direction: Optional[Literal["ASCENDING", "DESCENDING"]] = None
    relative_orbit: Optional[int] = Field(None, ge=1, le=175)
    boundary_file: str = ""


class NewRun(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    before: Period
    after: Period
    source: Literal["cdse", "synthetic", "local"]
    stage: Literal["search", "all"] = "all"
    settings: Settings = Settings()
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class QuickCompare(BaseModel):
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    date_a: date              # earlier date
    date_b: date              # later date
    window_days: int = Field(6, ge=1, le=30)
    source: Literal["cdse", "synthetic"] = "cdse"
    name: Optional[str] = Field(None, max_length=120)
    min_area_ha: float = Field(0.5, gt=0, le=100)


class Credentials(BaseModel):
    client_id: str = Field(..., min_length=4, max_length=200)
    client_secret: str = Field(..., min_length=4, max_length=200)


class Review(BaseModel):
    status: str
    actor: str = Field(..., min_length=1, max_length=120)
    note: str = Field("", max_length=2000)


class Labels(BaseModel):
    labels: dict[str, dict[str, str]]  # sample_id -> {"label": ..., "notes": ...}


# ------------------------------------------------------------------ endpoints

@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__}


@app.get("/api/defaults")
def defaults():
    cfg = C.load(BASE_CFG)
    return {"bbox": cfg["area"]["bbox"], "periods": cfg["periods"], "change": cfg["change"],
            "min_per_period": cfg["scenes"]["min_per_period"], "credit": cfg["outputs"]["credit"],
            "places": cfg["reference"].get("places", []), "has_env_credentials": all(_creds()),
            "max_quick_km2": MAX_QUICK_KM2}


@app.get("/api/runs")
def list_runs():
    if not RUNS.exists():
        return []
    return [_summary(d.name, d) for d in sorted(RUNS.iterdir(), reverse=True)
            if d.is_dir() and RUN_ID.match(d.name) and (d / "config.yaml").exists()]


def _launch(cfg: dict, name: str, stage: str, kind: str, env: dict) -> dict:
    try:
        C.check(cfg)
    except C.ConfigError as e:
        raise HTTPException(422, str(e))
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}_{_slug(name)}"
    d = RUNS / run_id
    (d / "output").mkdir(parents=True)
    cfg["project"]["output_dir"] = "output"
    cfg["project"]["work_dir"] = os.path.relpath(ROOT / "work", d)
    (d / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (d / "run.json").write_text(json.dumps({"name": name, "stage": stage, "kind": kind,
                                            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}))
    (d / "output" / "status.json").write_text(json.dumps({"stage": "starting", "state": "running"}))
    args = [sys.executable, str(ROOT / "run.py"), "--config", str(d / "config.yaml")]
    if stage == "search":
        args += ["--stage", "search"]
    console = open(d / "output" / "console.log", "a", encoding="utf-8")
    PROCS[run_id] = subprocess.Popen(args, cwd=ROOT, env=env, stdout=console, stderr=subprocess.STDOUT)
    return _summary(run_id, d)


def _base_cfg() -> dict:
    cfg = C.load(BASE_CFG)
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def _env_with_creds(source: str, stage: str, cid: str | None = None, secret: str | None = None) -> dict:
    env = os.environ.copy()
    if source == "cdse" and stage == "all":
        mc, ms = _creds()
        cid, secret = cid or mc, secret or ms
        if not (cid and secret):
            raise HTTPException(422, "Copernicus client ID and secret are needed to download images.")
        env["CDSE_CLIENT_ID"], env["CDSE_CLIENT_SECRET"] = cid, secret
    return env


@app.post("/api/runs", status_code=201)
def create_run(req: NewRun):
    cfg = _base_cfg()
    st = req.settings
    simulated = req.source == "synthetic"
    cfg["project"]["name"] = ("SIMULATED TEST - " if simulated else "") + req.name
    cfg["area"]["bbox"] = [round(v, 5) for v in req.bbox]
    cfg["area"]["resolution_m"] = st.resolution_m
    cfg["periods"]["before"].update(start=req.before.start.isoformat(), end=req.before.end.isoformat())
    cfg["periods"]["after"].update(start=req.after.start.isoformat(), end=req.after.end.isoformat())
    cfg["scenes"].update(source=req.source, min_per_period=st.min_per_period,
                         orbit_direction=st.orbit_direction, relative_orbit=st.relative_orbit)
    cfg["change"].update(min_area_ha=st.min_area_ha, water_before_min=st.water_before_min,
                         water_after_max=st.water_after_max)
    cfg["reference"]["boundary_file"] = st.boundary_file
    try:
        C.check(cfg)
    except C.ConfigError as e:
        raise HTTPException(422, str(e))
    env = _env_with_creds(req.source, req.stage, req.client_id, req.client_secret)
    return _launch(cfg, req.name, req.stage, "seasonal", env)


def _km2(b) -> float:
    import math
    lat = math.radians((b[1] + b[3]) / 2)
    return (b[2] - b[0]) * 111.32 * math.cos(lat) * (b[3] - b[1]) * 110.57


@app.post("/api/quick-compare", status_code=201)
def quick_compare(req: QuickCompare):
    """Compare the newest image up to date A with the newest image up to date B (one image each)."""
    w, s_, e, n = req.bbox
    if not (w < e and s_ < n):
        raise HTTPException(422, "invalid area")
    if _km2(req.bbox) > MAX_QUICK_KM2:
        raise HTTPException(422, f"Zoom in: quick comparisons are limited to {MAX_QUICK_KM2:,} km\u00b2.")
    if req.date_b <= req.date_a:
        raise HTTPException(422, "The second date must be after the first.")
    window = min(req.window_days, (req.date_b - req.date_a).days)
    cfg = _base_cfg()
    name = req.name or f"Quick compare {req.date_a.isoformat()} vs {req.date_b.isoformat()}"
    cfg["project"]["name"] = ("SIMULATED TEST - " if req.source == "synthetic" else "") + name
    cfg["area"]["bbox"] = [round(v, 5) for v in req.bbox]
    cfg["periods"]["before"].update(start=(req.date_a - timedelta(days=window - 1)).isoformat(),
                                    end=req.date_a.isoformat(), label=f"Image up to {req.date_a.isoformat()}")
    cfg["periods"]["after"].update(start=(req.date_b - timedelta(days=window - 1)).isoformat(),
                                   end=req.date_b.isoformat(), label=f"Image up to {req.date_b.isoformat()}")
    cfg["scenes"].update(source=req.source, min_per_period=1, orbit_direction=None, relative_orbit=None)
    cfg["change"].update(min_area_ha=req.min_area_ha, water_before_min=1.0, water_after_max=0.0)
    env = _env_with_creds(req.source, "all")
    return _launch(cfg, name, "all", "quick", env)


# ------------------------------------------------------------------ imagery

@app.get("/api/credentials")
def creds_status():
    cid, sec = _creds()
    return {"connected": bool(cid and sec), "from_environment": bool(os.environ.get("CDSE_CLIENT_ID")) and not CREDS}


@app.post("/api/credentials")
def set_creds(body: Credentials):
    sess = cdse.Session(body.client_id, body.client_secret)
    try:
        sess.headers()
    except cdse.CDSEError as e:
        raise HTTPException(401, f"Copernicus rejected these credentials: {e}")
    except Exception as e:  # network problems
        raise HTTPException(502, f"Could not reach Copernicus: {e}")
    CREDS.update(id=body.client_id, secret=body.client_secret)
    _SESSION.clear()
    return {"connected": True}


@app.delete("/api/credentials")
def clear_creds():
    CREDS.clear()
    _SESSION.clear()
    return {"connected": bool(_creds()[0])}


@app.get("/api/tiles/{sensor}/{day}/{z}/{x}/{y}.png")
def tile(sensor: str, day: date, z: int, x: int, y: int, window: int = 6, cloud: int = 30):
    if sensor not in imagery.SENSORS:
        raise HTTPException(404, "unknown imagery layer")
    if not (1 <= window <= 60 and 0 <= cloud <= 100) or not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(422, "invalid tile request")
    if z < imagery.MIN_ZOOM or z > imagery.MAX_ZOOM:
        return Response(imagery.EMPTY_PNG, media_type="image/png")
    try:
        png = imagery.get_tile(_session(), TILE_CACHE, sensor, day, window, z, x, y, cloud)
    except cdse.CDSEError as e:
        raise HTTPException(502, str(e)[:300])
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/acquisitions")
def acquisitions(bbox: str, day: date, window: int = 6, sensor: str = "radar"):
    """Which images exist in the `window` days up to `day` over the view (public catalogue, no login)."""
    try:
        b = [float(v) for v in bbox.split(",")]
        assert len(b) == 4 and b[0] < b[2] and b[1] < b[3]
    except (ValueError, AssertionError):
        raise HTTPException(422, "bbox must be west,south,east,north")
    start = (day - timedelta(days=window)).isoformat()
    try:
        if sensor.startswith("radar"):
            items = cdse.search_s1(b, start, day.isoformat(), log=lambda *_: None)
            seen = {}
            for i in items:
                k = (i["start"][:10], i["satellite"], i["orbit_direction"], i["relative_orbit"])
                seen[k] = {"date": k[0], "satellite": k[1], "orbit": f"{k[2].title()} {k[3]}"}
            out = sorted(seen.values(), key=lambda v: v["date"], reverse=True)
        else:
            items = cdse.search_s2(b, start, day.isoformat())
            out = sorted([{"date": i["date"], "satellite": i["satellite"],
                           "cloud": None if i["cloud"] is None else round(float(i["cloud"]), 1)} for i in items],
                         key=lambda v: v["date"], reverse=True)
    except Exception as e:
        raise HTTPException(502, f"Catalogue search failed: {str(e)[:200]}")
    return out


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    d = _run_dir(run_id)
    s = _summary(run_id, d)
    s["config"] = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
    s["full_metrics"] = _read_json(d / "output" / "metrics.json")
    return s


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str):
    d = _run_dir(run_id)
    p = PROCS.get(run_id)
    if p is None or p.poll() is not None:
        raise HTTPException(409, "this analysis is not running")
    p.send_signal(signal.SIGTERM) if os.name != "nt" else p.terminate()
    p.wait(timeout=20)
    (d / "output" / "status.json").write_text(json.dumps({**_status(run_id, d), "state": "stopped",
                                                          "message": "stopped by user"}))
    return {"ok": True}


@app.get("/api/runs/{run_id}/log")
def get_log(run_id: str, tail: int = 200):
    d = _run_dir(run_id)
    out = []
    for name in ("run.log", "console.log"):
        p = d / "output" / name
        if p.exists():
            out.append({"file": name, "lines": p.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]})
    return out


@app.get("/api/runs/{run_id}/scenes")
def get_scenes(run_id: str):
    return _csv_rows(_run_dir(run_id) / "output" / "scenes.csv")


@app.get("/api/runs/{run_id}/thresholds")
def get_thresholds(run_id: str):
    return _csv_rows(_run_dir(run_id) / "output" / "thresholds.csv")


@app.get("/api/runs/{run_id}/alerts")
def get_alerts(run_id: str):
    return review.load(_run_dir(run_id) / "output" / "alerts.json")


@app.get("/api/review-statuses")
def statuses():
    return review.STATUSES


@app.post("/api/runs/{run_id}/alerts/{alert_id}/review")
def post_review(run_id: str, alert_id: str, body: Review):
    p = _run_dir(run_id) / "output" / "alerts.json"
    try:
        return review.update(p, alert_id, body.status, body.actor, body.note)
    except KeyError:
        raise HTTPException(404, "unknown alert")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/runs/{run_id}/polygons")
def get_polygons(run_id: str):
    p = _run_dir(run_id) / "output" / "change_polygons.geojson"
    if not p.exists():
        return {"type": "FeatureCollection", "features": []}
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/runs/{run_id}/layers")
def get_layers(run_id: str):
    ql = _run_dir(run_id) / "output" / "quicklooks"
    b = _read_json(ql / "bounds.json")
    if not b:
        return {"bounds": None, "layers": []}
    names = ["optical_before", "optical_after", "before", "after", "water_before", "water_after", "change"]
    return {"bounds": b["bounds"], "layers": [n for n in names if (ql / f"{n}.png").exists()]}


@app.get("/api/runs/{run_id}/validation")
def get_validation(run_id: str):
    d = _run_dir(run_id) / "output"
    sheets = sorted(p.name for p in (d / "validation").glob("labelling_sheet_*.png")) if (d / "validation").exists() else []
    m = _read_json(d / "metrics.json", {}) or {}
    return {"rows": _csv_rows(d / "validation" / "validation.csv"), "sheets": sheets,
            "result": m.get("validation", {})}


@app.put("/api/runs/{run_id}/validation")
def put_validation(run_id: str, body: Labels):
    d = _run_dir(run_id)
    vpath = d / "output" / "validation" / "validation.csv"
    rows = _csv_rows(vpath)
    if not rows:
        raise HTTPException(404, "no validation sample for this analysis")
    for r in rows:
        upd = body.labels.get(r["sample_id"])
        if upd:
            lab = upd.get("label", "").strip().lower()
            if lab not in ("", "correct", "wrong", "unclear"):
                raise HTTPException(422, f"invalid label for {r['sample_id']}")
            r["label"], r["notes"] = lab, upd.get("notes", r.get("notes", ""))[:500]
    with open(vpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    from .pipeline import Run
    r = Run.__new__(Run)
    r.cfg, r.out, r.log = C.load(d / "config.yaml"), d / "output", (lambda *_: None)
    r.simulated = r.cfg["scenes"]["source"] == "synthetic"
    return r.score_manual()


@app.get("/api/runs/{run_id}/files/{rel:path}")
def get_file(run_id: str, rel: str):
    p = _out_file(run_id, rel)
    return FileResponse(p, filename=p.name if p.suffix in (".pdf", ".gpkg", ".kml", ".geojson", ".csv", ".json",
                                                           ".md", ".tif") else None)


@app.get("/api/runs/{run_id}/rasters.zip")
def get_rasters(run_id: str):
    rdir = _run_dir(run_id) / "output" / "rasters"
    files = sorted(rdir.glob("*.tif")) if rdir.exists() else []
    if not files:
        raise HTTPException(404, "no rasters")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{run_id}_rasters.zip"'})


@app.get("/api/method")
def method():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    parts = {}
    for title in ("Method", "Limits", "Data, maps and attribution"):
        i = readme.find(f"## {title}")
        if i >= 0:
            j = readme.find("\n## ", i + 3)
            parts[title] = readme[i + len(title) + 4: j if j > 0 else None].strip()
    return parts


# ------------------------------------------------------------------ frontend

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "not found")
        f = (DIST / path).resolve()
        if path and DIST.resolve() in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
