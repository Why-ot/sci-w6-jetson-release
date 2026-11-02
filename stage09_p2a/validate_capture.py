"""validate_capture.py — offline validator for an S40 capture session.

Pure Python + numpy. Never opens a camera. Never writes into the session directory.
Decides whether a session is complete enough for S40 analysis, and refuses otherwise.

    python validate_capture.py --session DIR [--json] [--require-reference]

Exit codes: 0 = valid, 1 = invalid, 2 = not found, 3 = valid capture but analysis not authorised.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

TARGETS = ["S00", "S20", "S40A", "S40B", "S60"]
STEP_TARGETS = ["S20", "S40A", "S40B", "S60"]
PLACEMENTS = 5
FRAMES = 30

DEPTH_W, DEPTH_H = 848, 480
COLOR_W, COLOR_H = 640, 480
DEPTH_BYTES = DEPTH_W * DEPTH_H * 2          # 814,080
COLOR_BYTES = COLOR_W * COLOR_H * 3          # 921,600

META_FILES = ["intrinsics.json", "device_config.json", "depth_scale.json",
              "roi_definition.json", "placement_metadata.csv", "frame_timestamps.csv"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_depth_file(p: Path) -> dict:
    """Structural check of one raw Z16 depth file, without trusting its name."""
    size = p.stat().st_size
    r = {"file": p.name, "bytes": size, "expected_bytes": DEPTH_BYTES, "ok": False, "reasons": []}
    if size != DEPTH_BYTES:
        r["reasons"].append(f"byte length {size} != {DEPTH_BYTES}")
        return r
    raw = np.fromfile(p, dtype="<u2")
    if raw.size != DEPTH_W * DEPTH_H:
        r["reasons"].append(f"element count {raw.size} != {DEPTH_W*DEPTH_H}")
        return r
    depth = raw.reshape(DEPTH_H, DEPTH_W)
    valid = depth > 0
    r.update({"dtype": str(raw.dtype), "valid_ratio": float(valid.mean()),
              "z_min_mm": int(depth[valid].min()) if valid.any() else 0,
              "z_max_mm": int(depth[valid].max()) if valid.any() else 0,
              "unique_values": int(np.unique(depth).size)})
    if not valid.any():
        r["reasons"].append("no valid depth pixels")
    if r["unique_values"] < 10:
        r["reasons"].append(f"only {r['unique_values']} distinct depth values (constant or corrupt?)")
    r["ok"] = not r["reasons"]
    return r


def check_color_file(p: Path) -> dict:
    r = {"file": p.name, "bytes": p.stat().st_size, "ok": False, "reasons": []}
    if p.suffix == ".raw":                       # raw RGB8, the Stage09-P2A default
        if r["bytes"] != COLOR_BYTES:
            r["reasons"].append(f"raw colour byte length {r['bytes']} != {COLOR_BYTES}")
        else:
            r["format"] = "raw_rgb8"
    else:                                        # PNG, accepted for backward compatibility
        if r["bytes"] < 1000:
            r["reasons"].append(f"PNG suspiciously small ({r['bytes']} B)")
        elif r["bytes"] > 4 * COLOR_BYTES:
            r["reasons"].append(f"PNG larger than 4x raw ({r['bytes']} B)")
        else:
            with p.open("rb") as fh:
                if fh.read(8) != b"\x89PNG\r\n\x1a\n":
                    r["reasons"].append("not a PNG (bad magic)")
            r["format"] = "png"
    r["ok"] = not r["reasons"]
    return r


def validate_session(root: Path, require_reference: bool) -> dict:
    rep = {"session": str(root), "exists": root.exists(), "targets": {}, "problems": [], "warnings": []}
    if not root.exists():
        rep["status"] = "NOT_FOUND"
        return rep

    for t in TARGETS:
        tdir = root / t
        tentry = {"present": tdir.exists(), "placements": [], "ok": True}
        if not tdir.exists():
            rep["problems"].append(f"target {t} directory missing")
            tentry["ok"] = False
            rep["targets"][t] = tentry
            continue
        for i in range(1, PLACEMENTS + 1):
            p = tdir / f"placement_{i:02d}"
            pe = {"placement": i, "ok": True, "reasons": [], "ref_reasons": []}
            if not p.exists():
                pe["ok"] = False
                pe["reasons"].append("placement directory missing")
                tentry["ok"] = False
                tentry["placements"].append(pe)
                rep["problems"].append(f"{t}/placement_{i:02d} missing")
                continue

            depth_files = sorted((p / "raw" / "depth").glob("*.raw")) if (p / "raw" / "depth").exists() else []
            color_files = []
            if (p / "raw" / "color").exists():
                for pat in ("*.rgb8.raw", "*.png"):
                    color_files += list((p / "raw" / "color").glob(pat))
            color_files = sorted(color_files, key=lambda f: f.name)

            # duplicate / sequence checks
            names = [f.name for f in depth_files]
            if len(names) != len(set(names)):
                pe["reasons"].append("duplicate depth filenames")
            expected = [f"frame_{k:03d}.raw" for k in range(FRAMES)]
            if names != expected:
                pe["reasons"].append(f"depth files are not frame_000..frame_{FRAMES-1}")
            cnames = [f.name for f in color_files]
            if len(cnames) != len(set(cnames)):
                pe["reasons"].append("duplicate colour filenames")
            c_raw = [f"frame_{k:03d}.rgb8.raw" for k in range(FRAMES)]
            c_png = [f"frame_{k:03d}.png" for k in range(FRAMES)]
            if cnames not in (c_raw, c_png):
                pe["reasons"].append("colour files are not a complete frame_000..029 sequence")
            if len(depth_files) != FRAMES:
                pe["reasons"].append(f"{len(depth_files)} depth frames, expected {FRAMES}")
            if len(color_files) != FRAMES:
                pe["reasons"].append(f"{len(color_files)} colour frames, expected {FRAMES}")

            # structural checks on the first and last frame only (cost control)
            for f in ([depth_files[0], depth_files[-1]] if depth_files else []):
                chk = check_depth_file(f)
                if not chk["ok"]:
                    pe["reasons"].extend(chk["reasons"])
                pe.setdefault("depth_sample", chk)
            for f in ([color_files[0]] if color_files else []):
                chk = check_color_file(f)
                if not chk["ok"]:
                    pe["reasons"].extend(chk["reasons"])

            meta = {n: (p / "meta" / n).exists() for n in META_FILES}
            pe["meta"] = meta
            for n, present in meta.items():
                if not present:
                    pe["reasons"].append(f"missing meta/{n}")

            # intrinsics sanity
            if meta["intrinsics.json"]:
                try:
                    k = json.loads((p / "meta" / "intrinsics.json").read_text(encoding="utf-8"))
                    fx, fy, cx, cy = k["fx"], k["fy"], k["cx"], k["cy"]
                    if not all(np.isfinite([fx, fy, cx, cy])) or fx <= 0 or fy <= 0:
                        pe["reasons"].append("intrinsics out of range")
                    if k.get("width", DEPTH_W) != DEPTH_W or k.get("height", DEPTH_H) != DEPTH_H:
                        pe["reasons"].append("intrinsics resolution != 848x480")
                    pe["intrinsics"] = {"fx": fx, "fy": fy, "cx": cx, "cy": cy}
                except Exception as e:  # noqa: BLE001
                    pe["reasons"].append(f"intrinsics unreadable: {type(e).__name__}")
            if meta["depth_scale.json"]:
                try:
                    s = json.loads((p / "meta" / "depth_scale.json").read_text(encoding="utf-8"))
                    v = float(s.get("depth_scale_m_per_unit", 0))
                    if not (0 < v < 0.1):
                        pe["reasons"].append(f"depth_scale implausible: {v}")
                    pe["depth_scale"] = v
                except Exception as e:  # noqa: BLE001
                    pe["reasons"].append(f"depth_scale unreadable: {type(e).__name__}")

            # timestamps monotonic
            if meta["frame_timestamps.csv"]:
                try:
                    with (p / "meta" / "frame_timestamps.csv").open(newline="", encoding="utf-8") as fh:
                        rows = list(csv.DictReader(fh))
                    ts = [float(r["device_timestamp_ms"]) for r in rows if (r.get("device_timestamp_ms") or "").strip()]
                    if len(ts) >= 2 and any(b <= a for a, b in zip(ts, ts[1:])):
                        pe["reasons"].append("device timestamps not strictly increasing")
                    if len(ts) != FRAMES:
                        pe["reasons"].append(f"{len(ts)} timestamps, expected {FRAMES}")
                except Exception as e:  # noqa: BLE001
                    pe["reasons"].append(f"timestamps unreadable: {type(e).__name__}")

            # reference readings (only enforced when requested)
            ref = p / "reference" / "reference_readings.csv"
            n_ref = 0
            if ref.exists():
                with ref.open(newline="", encoding="utf-8") as fh:
                    n_ref = sum(1 for r in csv.DictReader(fh) if (r.get("reading_mm") or "").strip())
            pe["reference_readings"] = n_ref
            if require_reference and t in STEP_TARGETS and n_ref < 3:
                # a missing reference does not invalidate the capture; it blocks the formal result
                pe["ref_reasons"].append(f"{n_ref} reference readings, need >= 3")

            pe["ok"] = not pe["reasons"]
            tentry["ok"] &= pe["ok"]
            tentry["placements"].append(pe)

        # S00 must not masquerade as a step target
        if t == "S00":
            tentry["note"] = "S00 is a plane reference; step analysis is not applicable"

        rep["targets"][t] = tentry
        if not tentry["ok"]:
            rep["problems"].append(f"target {t} has failing placements")

    # ROI frozen? A file cannot carry its own hash, so the frozen hash covers the `regions` payload only.
    roi = root / "S40A" / "placement_01" / "meta" / "roi_definition.json"
    rep["roi_frozen"] = False
    if roi.exists():
        try:
            d = json.loads(roi.read_text(encoding="utf-8"))
            stated = d.get("_payload_sha256")
            regions = d.get("regions")
            rep["roi_frozen"] = bool(stated)
            if stated and regions is not None:
                actual = hashlib.sha256(json.dumps(regions, sort_keys=True).encode()).hexdigest()
                if stated != actual:
                    rep["problems"].append("ROI regions changed after they were frozen (payload hash mismatch)")
                    rep["roi_frozen"] = False
            if not regions:
                rep["warnings"].append("ROI file has no regions[] mapping image area to physical face")
                rep["roi_frozen"] = False
        except json.JSONDecodeError:
            rep["problems"].append("roi_definition.json is not valid JSON")

    rep["capture_complete"] = not rep["problems"]
    if not rep["capture_complete"]:
        rep["status"] = "INCOMPLETE"
    elif require_reference and not all(
            rep["targets"][t]["placements"] and all(p.get("reference_readings", 0) >= 3 for p in rep["targets"][t]["placements"])
            for t in STEP_TARGETS):
        rep["status"] = "CAPTURE_OK_REFERENCE_MISSING"
    else:
        rep["status"] = "COMPLETE"
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--require-reference", action="store_true",
                    help="also require >=3 reference readings per placement (needed for a formal S40 result)")
    a = ap.parse_args(argv)

    rep = validate_session(Path(a.session), a.require_reference)
    if a.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(f"session : {rep['session']}")
        print(f"status  : {rep.get('status')}")
        for t, e in rep["targets"].items():
            ok = sum(1 for p in e["placements"] if p["ok"])
            print(f"  {t:5s} placements ok {ok}/{PLACEMENTS}")
        for p in rep["problems"][:25]:
            print(f"  ! {p}")
        for w in rep["warnings"][:10]:
            print(f"  ~ {w}")

    if rep.get("status") == "NOT_FOUND":
        return 2
    if rep.get("status") == "COMPLETE":
        return 0
    if rep.get("status") == "CAPTURE_OK_REFERENCE_MISSING":
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
