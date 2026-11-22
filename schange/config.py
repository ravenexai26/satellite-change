"""Load and check the run configuration."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


def load(path: str | Path) -> dict:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_path"] = str(path.resolve())
    cfg["_dir"] = str(path.resolve().parent)
    check(cfg)
    return cfg


def check(cfg: dict) -> None:
    w, s, e, n = cfg["area"]["bbox"]
    if not (w < e and s < n):
        raise ConfigError("area.bbox must be [west, south, east, north]")
    for p in ("before", "after"):
        if cfg["periods"][p]["start"] >= cfg["periods"][p]["end"]:
            raise ConfigError(f"periods.{p}: start must be before end")
    if cfg["periods"]["before"]["end"] >= cfg["periods"]["after"]["start"]:
        raise ConfigError("the before period must end before the after period starts")
    c = cfg["change"]
    if not (0 <= c["water_after_max"] < c["water_before_min"] <= 1):
        raise ConfigError("change thresholds must satisfy 0 <= water_after_max < water_before_min <= 1")
    if cfg["scenes"]["source"] not in ("cdse", "local", "synthetic"):
        raise ConfigError("scenes.source must be cdse, local or synthetic")


def resolve(cfg: dict, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else Path(cfg["_dir"]) / p


def fingerprint(cfg: dict) -> str:
    clean = {k: v for k, v in copy.deepcopy(cfg).items() if not k.startswith("_")}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()[:12]
