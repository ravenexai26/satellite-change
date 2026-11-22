"""Check that radar brightness of stable land matches between the two periods."""
from __future__ import annotations

import numpy as np

from .sar import to_db


def stable_land_check(acc_before, acc_after, f_before, f_after, max_diff_db: float) -> dict:
    """Stable land = never water in either period and low temporal variation in both.

    Compares the median of each period's mean backscatter (dB) over those pixels.
    """
    sd_b, sd_a = acc_before.std_db(), acc_after.std_db()
    land = (f_before == 0) & (f_after == 0) & np.isfinite(sd_b) & np.isfinite(sd_a)
    if land.sum() < 1000:
        return {"status": "insufficient", "pixels": int(land.sum())}
    lim_b = np.nanpercentile(sd_b[land], 25)
    lim_a = np.nanpercentile(sd_a[land], 25)
    stable = land & (sd_b <= lim_b) & (sd_a <= lim_a)
    mb = float(np.nanmedian(to_db(acc_before.mean_linear())[stable]))
    ma = float(np.nanmedian(to_db(acc_after.mean_linear())[stable]))
    diff = ma - mb
    return {"status": "pass" if abs(diff) <= max_diff_db else "fail", "pixels": int(stable.sum()),
            "median_before_db": round(mb, 2), "median_after_db": round(ma, 2), "difference_db": round(diff, 2),
            "limit_db": max_diff_db}
