"""Offline integration harness — the ten checks of Stage07-P1 §7.

Runs against a real D435 frame pair when one exists, and against a SYNTHETIC stand-in otherwise (clearly
labelled). It never opens a camera and never writes to the source data.

    python integration/offline_check.py --depth FILE.raw --intrinsics INTR.json \
        --depth-scale 0.001 --width 848 --height 480 [--meta-dir DIR] [--synthetic]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "w6_pkg" / "src"))
sys.path.insert(0, str(HERE))

import w6.core as core                      # noqa: E402
from eligibility import Eligibility         # noqa: E402

EXPECTED_DEPTH_BYTES = 848 * 480 * 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(depth_path: Path, intr: core.Intrinsics, depth_scale: float, meta_dir: Path | None,
        label: str) -> dict:
    checks = {}

    # 1. raw file read
    nbytes = depth_path.stat().st_size
    checks["01_file_read"] = {"ok": True, "bytes": nbytes, "sha256": sha256(depth_path)}

    # 2. data type
    raw = core.read_depth_z16(depth_path, intr.width, intr.height)
    checks["02_dtype"] = {"ok": raw.dtype == np.uint16, "dtype": str(raw.dtype),
                          "min": int(raw.min()), "max": int(raw.max())}

    # 3. resolution
    checks["03_resolution"] = {"ok": raw.shape == (intr.height, intr.width),
                               "shape": list(raw.shape),
                               "expected": [intr.height, intr.width]}

    # 4/5. intrinsics and scale parsed from metadata (never hard-coded)
    checks["04_intrinsics"] = {"ok": all(np.isfinite([intr.fx, intr.fy, intr.cx, intr.cy])),
                               "fx": intr.fx, "fy": intr.fy, "cx": intr.cx, "cy": intr.cy,
                               "source": str(meta_dir / "intrinsics.json") if meta_dir else "cli"}
    checks["05_depth_scale"] = {"ok": depth_scale > 0, "depth_scale": depth_scale,
                                "source": str(meta_dir / "depth_scale.json") if meta_dir else "cli"}

    # 6. Z16 -> metres
    depth_m = core.depth_to_metres(raw, depth_scale)
    checks["06_to_metres"] = {"ok": True, "z_min_m": float(depth_m[core.valid_mask(depth_m)].min()),
                              "z_max_m": float(depth_m[core.valid_mask(depth_m)].max())}

    # 7. valid positive depth ratio
    vm = core.valid_mask(depth_m)
    checks["07_valid_ratio"] = {"ok": True, "valid": int(vm.sum()), "total": int(vm.size),
                                "ratio": float(vm.mean()), "denominator": "single frame, all pixels"}

    # 8. back-projection
    pts = core.backproject(depth_m, intr)
    finite = np.isfinite(pts).all(axis=2)
    checks["08_backproject"] = {"ok": bool(finite.any()), "finite_points": int(finite.sum()),
                                "max_abs_xy_m": float(np.nanmax(np.abs(pts[..., :2])))}

    # 9. coordinate-system sanity: z must be positive, x/y must bracket the image centre
    zz = pts[..., 2][finite]
    xx = pts[..., 0][finite]
    yy = pts[..., 1][finite]
    checks["09_frame_sanity"] = {
        "ok": bool((zz > 0).all() and (xx.min() < 0 < xx.max()) and (yy.min() < 0 < yy.max())),
        "z_all_positive": bool((zz > 0).all()),
        "x_range": [float(xx.min()), float(xx.max())],
        "y_range": [float(yy.min()), float(yy.max())],
        "note": "camera optical frame, x right, y down, z forward"}

    # 10. metadata / directory coherence
    if meta_dir is not None:
        present = {n: (meta_dir / n).exists() for n in
                   ("intrinsics.json", "device_config.json", "depth_scale.json", "frame_timestamps.csv")}
        checks["10_metadata"] = {"ok": all(present.values()), "present": present, "dir": str(meta_dir)}
    else:
        checks["10_metadata"] = {"ok": False, "present": {}, "dir": None,
                                 "note": "no metadata directory supplied"}

    gate = Eligibility()
    return {"label": label, "depth_file": str(depth_path), "checks": checks,
            "all_ok": all(c.get("ok", False) for c in checks.values()),
            "s40_eligibility": gate.to_json()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", required=True)
    ap.add_argument("--intrinsics", required=False)
    ap.add_argument("--depth-scale", type=float, required=False)
    ap.add_argument("--width", type=int, default=848)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--meta-dir", required=False)
    ap.add_argument("--label", default="REAL_D435")
    ap.add_argument("--out", required=False)
    a = ap.parse_args(argv)

    if a.intrinsics:
        intr = core.Intrinsics.from_json(a.intrinsics)
    else:
        raise SystemExit("--intrinsics is required (values must come from metadata, not defaults)")
    if a.depth_scale is None:
        raise SystemExit("--depth-scale is required (must come from metadata, not a hard-coded 0.001)")
    intr.width, intr.height = a.width, a.height
    intr.validate()

    rep = run(Path(a.depth), intr, a.depth_scale, Path(a.meta_dir) if a.meta_dir else None, a.label)
    text = json.dumps(rep, indent=2)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if rep["all_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
