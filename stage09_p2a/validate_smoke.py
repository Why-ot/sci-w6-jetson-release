"""validate_smoke.py — structural check of an ENGINEERING_SMOKE_ONLY run.

Refuses any target other than SMOKE. Never produces a geometric result.
    python3 validate_smoke.py --session ~/sci_camera_audit/SMOKE_20261102_1200
Exit 0 = smoke OK, 1 = smoke failed, 2 = not found.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

DEPTH_BYTES = 848 * 480 * 2
COLOR_BYTES = 640 * 480 * 3


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--expected-frames", type=int, default=5)
    a = ap.parse_args(argv)

    root = Path(a.session).expanduser()
    rep = {"session": str(root), "label": "ENGINEERING_SMOKE_ONLY", "problems": []}
    if not root.exists():
        print("NOT_FOUND"); return 2

    targets = [d for d in root.iterdir() if d.is_dir()]
    if len(targets) != 1 or targets[0].name != "SMOKE":
        rep["problems"].append(f"expected exactly one SMOKE target, found {[t.name for t in targets]}")
    if not targets:
        print(json.dumps(rep, indent=2)); return 1

    p = targets[0] / "placement_01"
    depth = sorted((p / "raw" / "depth").glob("*.raw")) if p.exists() else []
    color = sorted((p / "raw" / "color").glob("*.rgb8.raw")) if p.exists() else []

    rep["depth_frames"] = len(depth)
    rep["color_frames"] = len(color)
    if len(depth) != a.expected_frames:
        rep["problems"].append(f"{len(depth)} depth frames, expected {a.expected_frames}")
    if len(color) != a.expected_frames:
        rep["problems"].append(f"{len(color)} colour frames, expected {a.expected_frames}")

    for f in depth:
        if f.stat().st_size != DEPTH_BYTES:
            rep["problems"].append(f"{f.name}: {f.stat().st_size} B != {DEPTH_BYTES}")
    for f in color:
        if f.stat().st_size != COLOR_BYTES:
            rep["problems"].append(f"{f.name}: {f.stat().st_size} B != {COLOR_BYTES}")

    hashes = [sha256(f) for f in depth]
    rep["distinct_depth_hashes"] = len(set(hashes))
    if len(set(hashes)) != len(hashes):
        rep["problems"].append("repeated depth frames (identical hashes) - pipeline may be stalled")

    man = p / "meta" / "frame_manifest.csv"
    write_ms = []
    if man.exists():
        import csv
        with man.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    write_ms.append(float(r.get("write_ms") or "nan"))
                except ValueError:
                    pass
    else:
        rep["problems"].append("frame_manifest.csv missing")
    good = [w for w in write_ms if np.isfinite(w)]
    if good:
        med = float(np.median(good))
        rep["median_write_ms"] = med
        if med > 20.0:
            rep["problems"].append(f"median write {med:.1f} ms > 20 ms: 30 fps budget at risk")

    for name in ("intrinsics.json", "device_config.json", "depth_scale.json", "frame_timestamps.csv"):
        if not (p / "meta" / name).exists():
            rep["problems"].append(f"meta/{name} missing")

    rep["status"] = "SMOKE_OK" if not rep["problems"] else "SMOKE_FAILED"
    print(json.dumps(rep, indent=2))
    return 0 if not rep["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
