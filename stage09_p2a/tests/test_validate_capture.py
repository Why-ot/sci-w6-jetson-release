"""Offline tests for validate_capture.py, using SYNTHETIC fixtures.

Every fixture is written under a directory whose name starts with SYNTHETIC_ and every metadata file carries
"_tag": "SYNTHETIC". None of this is a camera capture.

Run:  python tests/test_validate_capture.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from validate_capture import (validate_session, check_depth_file, DEPTH_BYTES, COLOR_BYTES,  # noqa: E402
                              FRAMES, TARGETS)

VALIDATOR = HERE / "validate_capture.py"


def write_meta(p: Path, scale=0.001, intr=None, n_ts=FRAMES, bad_ts=False) -> None:
    m = p / "meta"
    m.mkdir(parents=True, exist_ok=True)
    k = intr or {"fx": 927.17, "fy": 927.367, "cx": 651.315, "cy": 349.621,
                 "width": 848, "height": 480, "_tag": "SYNTHETIC"}
    (m / "intrinsics.json").write_text(json.dumps(k), encoding="utf-8")
    (m / "depth_scale.json").write_text(json.dumps({"depth_scale_m_per_unit": scale,
                                                    "source": "SYNTHETIC"}), encoding="utf-8")
    (m / "device_config.json").write_text(json.dumps({"serial": "SYNTHETIC", "_tag": "SYNTHETIC"}),
                                          encoding="utf-8")
    regions = [{"name": "FRONT", "polygon": [[10, 10], [200, 10], [200, 200], [10, 200]]}]
    (m / "roi_definition.json").write_text(json.dumps({
        "_tag": "SYNTHETIC", "regions": regions,
        "_payload_sha256": hashlib.sha256(json.dumps(regions, sort_keys=True).encode()).hexdigest()}),
        encoding="utf-8")
    (m / "placement_metadata.csv").write_text("target_id,placement_id,notes\nS40A,1,SYNTHETIC\n", encoding="utf-8")
    rows = ["frame_index,device_timestamp_ms,host_timestamp_iso"]
    for i in range(n_ts):
        t = 1000 - i if bad_ts else 1000 + i * 33
        rows.append(f"{i},{t},1970-01-01T00:00:00")
    (m / "frame_timestamps.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def make_placement(p: Path, n_depth=FRAMES, n_color=FRAMES, depth_bytes=DEPTH_BYTES,
                   valid_frac=0.9, n_ts=FRAMES, bad_ts=False, scale=0.001, ref_rows=3):
    (p / "raw" / "depth").mkdir(parents=True, exist_ok=True)
    (p / "raw" / "color").mkdir(parents=True, exist_ok=True)
    (p / "reference").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    for i in range(n_depth):
        a = (rng.random(848 * 480) * 3000).astype(np.uint16)          # SYNTHETIC values
        a[rng.random(a.size) > valid_frac] = 0
        b = a.tobytes()
        if depth_bytes != DEPTH_BYTES:
            b = b[:depth_bytes] if depth_bytes < DEPTH_BYTES else b + b"\x00" * (depth_bytes - DEPTH_BYTES)
        (p / "raw" / "depth" / f"frame_{i:03d}.raw").write_bytes(b)
    for i in range(n_color):
        # Stage09-P2A default: raw RGB8, exactly 921,600 B
        (p / "raw" / "color" / f"frame_{i:03d}.rgb8.raw").write_bytes(
            rng.integers(0, 256, COLOR_BYTES, dtype=np.uint8).tobytes())
    write_meta(p, scale=scale, n_ts=n_ts, bad_ts=bad_ts)
    lines = ["target_id,placement_id,reading_index,reading_mm,instrument_model"]
    for j in range(1, ref_rows + 1):
        lines.append(f"S40A,1,{j},40.0{1+j},SYNTHETIC_CALIPER")
    (p / "reference" / "reference_readings.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_session(root: Path, targets=TARGETS, placements=5, **kw):
    for t in targets:
        for i in range(1, placements + 1):
            make_placement(root / t / f"placement_{i:02d}", **kw)


class Report:
    def __init__(self):
        self.rows = []

    def check(self, name, got, want, detail=""):
        ok = (got == want)
        self.rows.append((name, ok, got, want, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name:52s} got={got!r} want={want!r} {detail}")
        return ok


def main() -> int:
    r = Report()
    tmp = Path(tempfile.mkdtemp(prefix="SYNTHETIC_"))
    try:
        # ---------- 1. clean session, reference present
        s = tmp / "SYNTHETIC_clean"
        make_session(s)
        rep = validate_session(s, require_reference=True)
        r.check("valid session -> COMPLETE", rep["status"], "COMPLETE")

        # ---------- 2. missing reference
        s2 = tmp / "SYNTHETIC_noref"
        make_session(s2, ref_rows=0)
        r.check("no reference -> CAPTURE_OK_REFERENCE_MISSING",
                validate_session(s2, require_reference=True)["status"], "CAPTURE_OK_REFERENCE_MISSING")

        # ---------- 3. short depth file
        s3 = tmp / "SYNTHETIC_shortdepth"
        make_session(s3)
        (s3 / "S40A" / "placement_01" / "raw" / "depth" / "frame_000.raw").write_bytes(b"\x00" * 100)
        rep3 = validate_session(s3, require_reference=False)
        r.check("short depth file -> INCOMPLETE", rep3["status"], "INCOMPLETE")

        # ---------- 4. missing metadata
        s4 = tmp / "SYNTHETIC_nometa"
        make_session(s4)
        (s4 / "S40A" / "placement_01" / "meta" / "intrinsics.json").unlink()
        r.check("missing intrinsics -> INCOMPLETE",
                validate_session(s4, require_reference=False)["status"], "INCOMPLETE")

        # ---------- 5. wrong resolution in intrinsics
        s5 = tmp / "SYNTHETIC_badintr"
        make_session(s5)
        write_meta(s5 / "S40A" / "placement_01",
                   intr={"fx": 927.0, "fy": 927.0, "cx": 320.0, "cy": 240.0, "width": 640, "height": 480})
        r.check("wrong intrinsics resolution -> INCOMPLETE",
                validate_session(s5, require_reference=False)["status"], "INCOMPLETE")

        # ---------- 6. non-monotonic timestamps
        s6 = tmp / "SYNTHETIC_badts"
        make_session(s6)
        write_meta(s6 / "S40A" / "placement_01", bad_ts=True)
        r.check("decreasing timestamps -> INCOMPLETE",
                validate_session(s6, require_reference=False)["status"], "INCOMPLETE")

        # ---------- 7. duplicate filename (frame count short because one is missing)
        s7 = tmp / "SYNTHETIC_dup"
        make_session(s7)
        d = s7 / "S40A" / "placement_01" / "raw" / "depth"
        shutil.copy(d / "frame_000.raw", d / "frame_000_copy.raw")
        r.check("extra duplicate file -> INCOMPLETE",
                validate_session(s7, require_reference=False)["status"], "INCOMPLETE")

        # ---------- 8. corrupt colour png
        s8 = tmp / "SYNTHETIC_badpng"
        make_session(s8)
        (s8 / "S40A" / "placement_01" / "raw" / "color" / "frame_000.rgb8.raw").write_bytes(b"notapng")
        r.check("truncated raw colour -> INCOMPLETE",
                validate_session(s8, require_reference=False)["status"], "INCOMPLETE")

        # ---------- 9. implausible depth_scale
        s9 = tmp / "SYNTHETIC_badscale"
        make_session(s9)
        write_meta(s9 / "S40A" / "placement_01", scale=5.0)
        r.check("implausible depth_scale -> INCOMPLETE",
                validate_session(s9, require_reference=False)["status"], "INCOMPLETE")

        # ---------- 10. constant depth image (corruption that keeps the byte count)
        s10 = tmp / "SYNTHETIC_const"
        make_session(s10)
        (s10 / "S40A" / "placement_01" / "raw" / "depth" / "frame_000.raw").write_bytes(
            np.zeros(848 * 480, dtype=np.uint16).tobytes())
        chk = check_depth_file(s10 / "S40A" / "placement_01" / "raw" / "depth" / "frame_000.raw")
        r.check("all-zero depth detected", chk["ok"], False, str(chk["reasons"]))

        # ---------- 11. back-projection on a synthetic frame
        from w6_like_backproject import backproject_ok
        s11 = tmp / "SYNTHETIC_bp"
        make_placement(s11 / "S40A" / "placement_01")
        ok, detail = backproject_ok(s11 / "S40A" / "placement_01" / "raw" / "depth" / "frame_000.raw",
                                    {"fx": 927.17, "fy": 927.367, "cx": 651.315, "cy": 349.621}, 0.001)
        r.check("3D back-projection executes", ok, True, detail)

        # ---------- 12. NOT_FOUND
        r.check("missing session -> NOT_FOUND",
                validate_session(tmp / "does_not_exist", False)["status"], "NOT_FOUND")

        # ---------- 13. CLI exit codes
        out = subprocess.run([sys.executable, str(VALIDATOR), "--session", str(s)], capture_output=True, text=True)
        r.check("CLI exit 0 on valid session", out.returncode, 0)
        out = subprocess.run([sys.executable, str(VALIDATOR), "--session", str(s2), "--require-reference"],
                             capture_output=True, text=True)
        r.check("CLI exit 3 when reference missing", out.returncode, 3)
        out = subprocess.run([sys.executable, str(VALIDATOR), "--session", str(tmp / "nope")],
                             capture_output=True, text=True)
        r.check("CLI exit 2 on NOT_FOUND", out.returncode, 2)

        # ---------- 14. capture_s40.py refuses without --confirm CAPTURE
        out = subprocess.run([sys.executable, str(HERE / "capture_s40.py"), "--target", "S40A",
                              "--placement", "1", "--out", str(tmp / "x"), "--confirm", "no"],
                             capture_output=True, text=True)
        r.check("capture refuses without confirmation", out.returncode, 2)

        n_pass = sum(1 for _, ok, *_ in r.rows if ok)
        print(f"\n{n_pass}/{len(r.rows)} checks passed")
        (HERE / "results").mkdir(exist_ok=True)
        (HERE / "results" / "offline_test_results.json").write_text(json.dumps(
            [{"test": n, "pass": ok, "got": str(g), "want": str(w), "detail": d} for n, ok, g, w, d in r.rows],
            indent=2), encoding="utf-8")
        return 0 if n_pass == len(r.rows) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
