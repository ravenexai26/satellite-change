"""Method note (Markdown) and the evidence PDF for the proposal."""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

LIMITS = [
    "Pixel size is 10 m: channels, banks and sand islands are visible; people, boats and single vehicles are not.",
    "Wind roughens open water and can make it look like land; smooth wet sand can look like water. "
    "The frequency rule (consistent state across all scenes of a period) reduces both but does not remove them.",
    "River level differs between any two dates. Changes along the water's edge may partly reflect level, not a "
    "moved bank; comparing the same season in both years limits this.",
    "Sentinel-1 revisits every few days, so this is a planning and prioritisation layer, not a real-time alarm.",
    "Every polygon is a lead for verification by authorised personnel. The system describes physical change "
    "only; it does not determine the cause.",
]


def method_note(m: dict, cfg: dict) -> str:
    pb, pa = cfg["periods"]["before"], cfg["periods"]["after"]
    c = cfg["change"]
    cal = m["calibration_check"]
    val = m.get("validation", {})
    thr = m["thresholds_db"]
    lines = [
        f"# Method note: {cfg['project']['name']}",
        "",
        f"Run {m['run_at']} · code version {m['model_version']} · config {m['config_fingerprint']}",
        "",
        "## Result",
        "",
        f"Between {pb['label']} ({pb['start']} to {pb['end']}) and {pa['label']} ({pa['start']} to {pa['end']}), "
        f"{m['area_ha']['water_to_land']:.1f} ha changed from water to land and "
        f"{m['area_ha']['land_to_water']:.1f} ha from land to water, in {m['polygons']['total']} polygons of at "
        f"least {c['min_area_ha']} ha ({m['polygons']['high']} high, {m['polygons']['medium']} medium, "
        f"{m['polygons']['low']} low priority).",
        "",
        "## Data",
        "",
        "- Sensor: Sentinel-1 C-band SAR, IW mode, GRD high resolution, VV and VH",
        f"- Orbit: {m['orbit']}; {m['n_before']} scenes before, {m['n_after']} after (listed in scenes.csv)",
        f"- Satellites: {', '.join(m['satellites'])}",
        f"- Area: {cfg['area']['bbox']} (WGS84), analysed on a {cfg['area']['resolution_m']} m grid in {cfg['area']['crs']}",
        "",
        "## Processing",
        "",
        f"1. Backscatter: {cfg['processing']['backscatter']} with orthorectification on the "
        f"{cfg['processing']['dem']} DEM (source: {m['source']}).",
        f"2. Speckle: Lee filter, {cfg['processing']['speckle_filter']['window']}×"
        f"{cfg['processing']['speckle_filter']['window']} window, ENL {cfg['processing']['speckle_filter']['enl']}.",
        f"3. Water per scene: {cfg['processing']['water_band']} in dB below a split-based Otsu threshold "
        f"(tiles {cfg['processing']['otsu_tile_px']} px with Ashman D > 2). Thresholds ranged "
        f"{thr['min']:.2f} to {thr['max']:.2f} dB (thresholds.csv).",
        "4. Water frequency per pixel and period = water scenes / valid scenes.",
        f"5. Change: water_to_land where before ≥ {c['water_before_min']} and after ≤ {c['water_after_max']}; "
        f"land_to_water the reverse. Patches under {c['min_area_ha']} ha (8-connected) removed.",
        ("6. Single-pair comparison (one image per date): confidence per polygon = mean over its pixels of how far "
         "both images sit from their water thresholds, scaled so 6 dB or more clear of the threshold in both = 1. "
         "With one image per date, wind or wet sand in either image can cause false changes, so treat these "
         "alerts as more tentative than a multi-scene comparison."
         if m.get("mode") == "single_pair" else
         "6. Confidence per polygon = mean |after frequency − before frequency|, range "
         f"{c['water_before_min'] - c['water_after_max']:.1f} to 1."),
        f"7. Priority: high if area ≥ {cfg['priority']['high_area_ha']} ha and confidence ≥ "
        f"{cfg['priority']['high_confidence']}; medium if area ≥ {cfg['priority']['medium_area_ha']} ha or "
        f"confidence ≥ {cfg['priority']['high_confidence']}; otherwise low."
        + (f" Raised one level within {cfg['priority']['near_boundary_km']} km of the Survey of India boundary."
           if cfg['reference'].get('boundary_file') else ""),
        "",
        "## Checks",
        "",
        f"- Calibration: stable-land median backscatter {cal.get('median_before_db', 'n/a')} dB before, "
        f"{cal.get('median_after_db', 'n/a')} dB after, difference {cal.get('difference_db', 'n/a')} dB "
        f"(limit {c['calibration_max_diff_db']} dB): **{cal['status']}**.",
    ]
    auto = val.get("optical_auto")
    if auto:
        lines.append(f"- Optical cross-check (Sentinel-2 NDWI, independent sensor): {auto['polygons_agree']} of "
                     f"{auto['polygons_checked']} change polygons agree on more than half their area; "
                     f"{auto['nochange_agree']} of {auto['nochange_checked']} no-change points agree.")
    man = val.get("manual")
    if man:
        lines.append(f"- Manual check against Sentinel-2: change {man['change']['correct']}/{man['change']['judged']} "
                     f"correct, no change {man['no_change']['correct']}/{man['no_change']['judged']} correct.")
    else:
        lines.append("- Manual check: sample and labelling sheets in validation/; not yet scored.")
    lines += ["", "## Limits", ""] + [f"- {x}" for x in LIMITS]
    lines += ["", cfg["outputs"]["credit"] + "."]
    return "\n".join(lines) + "\n"


def evidence_pdf(path: Path, figs: list[Path], note_md: str, simulated: bool):
    with PdfPages(path) as pdf:
        for f in figs:
            if not f.exists():
                continue
            img = plt.imread(f)
            h, w = img.shape[:2]
            landscape = w > h
            fig = plt.figure(figsize=(11.69, 8.27) if landscape else (8.27, 11.69))
            ax = fig.add_axes([0.03, 0.03, 0.94, 0.94])
            ax.imshow(img)
            ax.axis("off")
            if simulated:
                fig.text(0.5, 0.5, "SIMULATED TEST DATA\nNOT A REAL MAP", ha="center", va="center", fontsize=40,
                         color="red", alpha=0.25, rotation=25, weight="bold")
            pdf.savefig(fig)
            plt.close(fig)
        body = []
        for line in note_md.splitlines():
            body += textwrap.wrap(line.replace("**", ""), 105) or [""]
        per = 62
        for k in range(0, len(body), per):
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.text(0.07, 0.95, "\n".join(body[k:k + per]), va="top", ha="left", fontsize=7.6, family="DejaVu Sans")
            pdf.savefig(fig)
            plt.close(fig)
