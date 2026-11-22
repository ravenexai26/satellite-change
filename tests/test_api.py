"""Web API tests: python -m pytest -q tests/test_api.py"""
import importlib
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHANGE_RUNS_DIR", str(tmp_path / "runs"))
    import schange.server as server
    importlib.reload(server)
    return TestClient(server.app), server


def _wait(c, run_id, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get(f"/api/runs/{run_id}").json()["status"]
        if s["state"] in ("done", "failed"):
            return s
        time.sleep(2)
    raise TimeoutError


def test_rejects_bad_requests(client):
    c, _ = client
    body = {"name": "x", "bbox": [90.1, 25.9, 90.0, 26.0], "before": {"start": "2025-10-15", "end": "2025-11-30"},
            "after": {"start": "2026-10-15", "end": "2026-11-21"}, "source": "synthetic"}
    assert c.post("/api/runs", json=body).status_code == 422          # west > east
    body["bbox"] = [89.90, 25.95, 89.96, 26.01]
    body["source"] = "cdse"
    assert c.post("/api/runs", json=body).status_code == 422          # no credentials for a full run
    assert c.get("/api/runs/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert "root:" not in c.get("/api/runs/../../etc/passwd").text      # never serves files outside the app
    assert c.get("/api/does-not-exist").status_code == 404
    assert c.get("/api/runs/nope").status_code == 404


def test_full_simulated_run_review_and_validation(client):
    c, _ = client
    body = {"name": "API test", "bbox": [89.90, 25.95, 89.96, 26.01],
            "before": {"start": "2025-10-15", "end": "2025-11-30"},
            "after": {"start": "2026-10-15", "end": "2026-11-21"}, "source": "synthetic",
            "settings": {"min_area_ha": 0.2}}
    r = c.post("/api/runs", json=body)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    s = _wait(c, rid)
    assert s["state"] == "done", c.get(f"/api/runs/{rid}/log").json()
    run = c.get(f"/api/runs/{rid}").json()
    assert run["simulated"] and run["metrics"]["polygons"]["total"] > 0
    assert c.get(f"/api/runs/{rid}/layers").json()["bounds"]
    assert c.get(f"/api/runs/{rid}/polygons").json()["features"]
    assert len(c.get(f"/api/runs/{rid}/scenes").json()) == 8
    alerts = c.get(f"/api/runs/{rid}/alerts").json()
    aid = alerts[0]["alert_id"]
    assert c.post(f"/api/runs/{rid}/alerts/{aid}/review", json={"status": "bogus", "actor": "a"}).status_code == 422
    rv = c.post(f"/api/runs/{rid}/alerts/{aid}/review", json={"status": "forwarded", "actor": "Duty officer"})
    assert rv.status_code == 200 and rv.json()["audit"][-1]["actor"] == "Duty officer"
    v = c.get(f"/api/runs/{rid}/validation").json()
    labels = {row["sample_id"]: {"label": "correct"} for row in v["rows"]}
    res = c.put(f"/api/runs/{rid}/validation", json={"labels": labels}).json()
    assert res["change"]["correct"] == res["change"]["judged"] > 0
    assert c.get(f"/api/runs/{rid}/files/evidence_report.pdf").status_code == 200
    assert c.get(f"/api/runs/{rid}/files/../config.yaml").status_code in (400, 404)
    assert c.get(f"/api/runs/{rid}/rasters.zip").status_code == 200


def test_tiles_use_copernicus_and_cache(client, tmp_path, monkeypatch):
    c, server = client
    from schange import imagery
    calls = []

    class FakeSession:
        def process(self, body, accept=None):
            calls.append(body)
            return imagery.EMPTY_PNG

    monkeypatch.setattr(server, "TILE_CACHE", tmp_path / "tiles")
    assert c.get("/api/tiles/radar/2026-11-20/12/3072/1758.png").status_code == 503   # not connected
    monkeypatch.setattr(server, "_session", lambda: FakeSession())
    r = c.get("/api/tiles/radar/2026-11-20/12/3072/1758.png?window=6")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    body = calls[0]
    assert body["input"]["data"][0]["type"] == "sentinel-1-grd"
    assert body["input"]["data"][0]["dataFilter"]["timeRange"] == {"from": "2026-11-14T00:00:00Z", "to": "2026-11-20T23:59:59Z"}
    assert body["input"]["data"][0]["processing"]["backCoeff"] == "GAMMA0_TERRAIN"
    c.get("/api/tiles/radar/2026-11-20/12/3072/1758.png?window=6")
    assert len(calls) == 1                                                          # second request from cache
    c.get("/api/tiles/optical/2026-11-20/12/3072/1758.png?cloud=20")
    assert calls[1]["input"]["data"][0]["dataFilter"]["maxCloudCoverage"] == 20
    assert c.get("/api/tiles/radar/2026-11-20/5/1/1.png").content == imagery.EMPTY_PNG  # too far out: no request
    assert len(calls) == 2
    assert c.get("/api/tiles/bogus/2026-11-20/12/1/1.png").status_code == 404
    assert c.get("/api/tiles/radar/2026-11-20/3/99/1.png").status_code == 422


def test_quick_compare_single_pair(client):
    c, _ = client
    bad = {"bbox": [89.0, 25.0, 91.0, 27.0], "date_a": "2026-11-13", "date_b": "2026-11-20", "source": "synthetic"}
    assert c.post("/api/quick-compare", json=bad).status_code == 422                  # area too large
    body = {**bad, "bbox": [89.90, 25.95, 89.96, 26.01], "min_area_ha": 0.2}
    assert c.post("/api/quick-compare", json={**body, "date_b": "2026-11-01"}).status_code == 422
    r = c.post("/api/quick-compare", json=body)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert r.json()["kind"] == "quick"
    s = _wait(c, rid)
    assert s["state"] == "done", c.get(f"/api/runs/{rid}/log").json()
    run = c.get(f"/api/runs/{rid}").json()
    assert run["full_metrics"]["mode"] == "single_pair"
    assert run["full_metrics"]["n_before"] == 1 and run["full_metrics"]["n_after"] == 1
    confs = [a["confidence"] for a in c.get(f"/api/runs/{rid}/alerts").json()]
    assert confs and all(0 <= x <= 1 for x in confs) and min(confs) < 1   # not the constant 1.0 of 0/1 frequencies
    assert "Single-pair" in c.get(f"/api/runs/{rid}/files/method_note.md").text
