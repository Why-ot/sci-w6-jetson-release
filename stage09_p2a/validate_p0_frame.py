"""validate_p0_frame.py — read-only compatibility check of the historical Stage07-P0 D435 frame.

Never writes into the P0 directory. Produces a JSON report next to the analysis, not next to the data.

    python3 validate_p0_frame.py --p0 ~/sci_camera_audit/SCI_STAGE07_P0_D435_PREFLIGHT \
                                 --out p0_readonly_report.json

Label: REAL_SINGLE_FRAME_PREFLIGHT. This is NOT a session and NOT an S40 result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

DEPTH_W, DEPTH_H = 848, 480
COLOR_W, COLOR_H = 640, 480
DEPTH_BYTES = DEPTH_W * DEPTH_H * 2
COLOR_BYTES = COLOR_W * COLOR_H * 3


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", required=True, help="Path to SCI_STAGE07_P0_D435_PREFLIGHT (read-only)")
    ap.add_argument("--out", default="p0_readonly_report.json")
    a = ap.parse_args(argv)

    root = Path(a.p0).expanduser()
    rep = {"label": "REAL_SINGLE_FRAME_PREFLIGHT", "p0_root": str(root), "exists": root.exists(),
           "checks": {}, "problems": []}
    if not root.exists():
        rep["status"] = "NOT_FOUND"
        Path(a.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print("NOT_FOUND:", root)
        return 2

    depth = root / "smoke_data" / "depth_000000.z16.raw"
    color = root / "smoke_data" / "color_000000.rgb8.raw"
    intr = root / "CAMERA_INTRINSICS.json"

    # 1/2 byte lengths
    for name, p, want in (("depth", depth, DEPTH_BYTES), ("color", color, COLOR_BYTES)):
        if p.exists():
            size = p.stat().st_size
            rep["checks"][f"{name}_bytes"] = {"bytes": size, "expected": want, "ok": size == want,
                                              "sha256": sha256(p)}
            if size != want:
                rep["problems"].append(f"{name}: {size} bytes != {want}")
        else:
            rep["checks"][f"{name}_bytes"] = {"ok": False, "error": "file missing"}
            rep["problems"].append(f"{name} file missing")

    # 3/4 intrinsics and scale
    k = {}
    if intr.exists():
        try:
            k = json.loads(intr.read_text(encoding="utf-8"))
            fx, fy = float(k.get("fx", 0)), float(k.get("fy", 0))
            ok = fx > 0 and fy > 0
            rep["checks"]["intrinsics"] = {"ok": ok, "fx": fx, "fy": fy,
                                           "cx": k.get("cx"), "cy": k.get("cy"),
                                           "width": k.get("width"), "height": k.get("height"),
                                           "sha256": sha256(intr)}
            if not ok:
                rep["problems"].append("intrinsics fx/fy not positive")
            if k.get("width") not in (None, DEPTH_W) or k.get("height") not in (None, DEPTH_H):
                rep["checks"]["intrinsics"]["resolution_note"] = "metadata resolution differs from 848x480"
        except Exception as e:  # noqa: BLE001
            rep["checks"]["intrinsics"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            rep["problems"].append("intrinsics unreadable")
    else:
        rep["checks"]["intrinsics"] = {"ok": False, "error": "file missing"}
        rep["problems"].append("CAMERA_INTRINSICS.json missing")

    scale = k.get("depth_scale_m_per_unit") or k.get("depth_scale") or k.get("depth_scale_mm")
    if scale is not None:
        s = float(scale)
        if s > 1.0:            # given in mm
            s = s / 1000.0
        rep["checks"]["depth_scale"] = {"value": s, "ok": 0 < s < 0.1}
        if not (0 < s < 0.1):
            rep["problems"].append(f"depth_scale implausible: {s}")
    else:
        rep["checks"]["depth_scale"] = {"ok": False, "error": "not present in the metadata"}
        rep["problems"].append("depth_scale not found")

    # 5/6/7 back-projection and validity
    if depth.exists() and rep["checks"]["depth_bytes"]["ok"] and k.get("fx"):
        raw = np.fromfile(depth, dtype="<u2").reshape(DEPTH_H, DEPTH_W)
        s = rep["checks"]["depth_scale"]["value"]
        z = raw.astype(np.float64) * s
        valid = z > 0
        vv, uu = np.mgrid[0:DEPTH_H, 0:DEPTH_W]
        X = (uu - float(k["cx"])) / float(k["fx"]) * z
        Y = (vv - float(k["cy"])) / float(k["fy"]) * z
        rep["checks"]["backprojection"] = {
            "ok": bool(valid.any() and (z[valid] > 0).all()),
            "finite_points": int(valid.sum()),
            "x_range": [float(X[valid].min()), float(X[valid].max())],
            "y_range": [float(Y[valid].min()), float(Y[valid].max())],
            "z_range": [float(z[valid].min()), float(z[valid].max())],
        }
        rep["checks"]["valid_ratio"] = {"valid": int(valid.sum()), "total": int(valid.size),
                                        "ratio": float(valid.mean()),
                                        "denominator": "single frame, all pixels"}

    # 8 metadata field compatibility
    required = ["fx", "fy", "cx", "cy"]
    present = [r for r in required if r in k]
    rep["checks"]["metadata_fields"] = {"present": present, "missing": [r for r in required if r not in k],
                                        "extra": sorted(set(k) - set(required))}

    rep["status"] = "PASS" if not rep["problems"] else "FAIL"
    rep["note"] = ("A single historical frame is not a capture session; this report may never be used as an "
                   "S40 result.")
    Path(a.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
