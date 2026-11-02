"""Minimal back-projection helper used by the offline tests (and reusable by the analysis).

Deliberately independent of the frozen W6 package so that the capture validator has no import-time
dependency on it. Same convention: X = (u-cx)/fx*Z, Y = (v-cy)/fy*Z, Z = depth.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def load_raw(path: str | Path, width: int = 848, height: int = 480) -> np.ndarray:
    raw = np.fromfile(Path(path), dtype="<u2")
    if raw.size != width * height:
        raise ValueError(f"{path}: expected {width*height} uint16, got {raw.size}")
    return raw.reshape(height, width)


def backproject(depth_m: np.ndarray, intr: dict) -> np.ndarray:
    h, w = depth_m.shape
    vv, uu = np.mgrid[0:h, 0:w]
    z = depth_m
    pts = np.stack([(uu - intr["cx"]) / intr["fx"] * z,
                    (vv - intr["cy"]) / intr["fy"] * z,
                    z], axis=-1)
    pts[~(np.isfinite(depth_m) & (depth_m > 0))] = np.nan
    return pts


def backproject_ok(raw_path: str | Path, intr: dict, depth_scale: float) -> tuple[bool, str]:
    try:
        raw = load_raw(raw_path)
        depth = raw.astype(np.float64) * float(depth_scale)
        pts = backproject(depth, intr)
        finite = np.isfinite(pts).all(axis=2)
        if finite.sum() < 100:
            return False, f"only {int(finite.sum())} finite points"
        z = pts[..., 2][finite]
        x = pts[..., 0][finite]
        y = pts[..., 1][finite]
        if not (z > 0).all():
            return False, "non-positive Z present"
        return True, f"{int(finite.sum())} points, z=[{z.min():.3f},{z.max():.3f}] m"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
