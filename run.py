#!/usr/bin/env python3
"""Ravenex satellite change map.

    python run.py --config config.yaml                 # full run on real Sentinel-1 data
    python run.py --config config.yaml --stage search  # stop after the scene list, for sign-off
    python run.py --config config.yaml --stage score   # score a filled validation/validation.csv
    python run.py --demo                               # end-to-end test on a simulated river
"""
import argparse
import copy
import sys
from datetime import datetime

from schange import config as C
from schange.pipeline import Run, run_all


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--stage", choices=["all", "search", "score"], default="all")
    ap.add_argument("--demo", action="store_true", help="run on simulated data with known truth")
    a = ap.parse_args()

    cfg = C.load(a.config)
    if a.demo:
        cfg = copy.deepcopy(cfg)
        cfg["scenes"]["source"] = "synthetic"
        cfg["project"]["output_dir"] = "output_demo"
        cfg["project"]["work_dir"] = "work_demo"
        cfg["project"]["name"] = "SIMULATED TEST - " + cfg["project"]["name"]

    out = C.resolve(cfg, cfg["project"]["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "run.log", "a", encoding="utf-8")

    def log(msg):
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    if a.stage == "score":
        r = Run.__new__(Run)
        r.cfg, r.log, r.out, r.simulated = cfg, log, out, cfg["scenes"]["source"] == "synthetic"
        log(f"Manual validation: {r.score_manual()}")
        return 0
    run_all(cfg, a.stage, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
