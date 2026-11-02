"""capture_s40.py — D435 capture for S40/S20/S60/S00. Jetson only.

Stage09-P2A revision (documented in ../CAPTURE_RISK_REVIEW.md):
  * colour is stored as raw RGB8 (921,600 B) instead of PNG  -> removes the Pillow dependency and the
    PNG-encode time from the 30 fps budget
  * free-space check before the first frame
  * the per-frame manifest is appended as frames land, so a mid-run failure leaves evidence
  * a FAILURE.json is written on any exception, and the session is marked partial
  * ROI records frozen_at / operator / first_frame_sha256 so the freeze is traceable, not just hashed

Safety contract (unchanged): requires --confirm CAPTURE, refuses non-empty directories, never touches
ROS/CAN/robot, never opens a device it was not told to use.

    python3 capture_s40.py --target S40A --placement 1 --out ~/sci_camera_audit/S40_SESSION --confirm CAPTURE
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

TARGETS = ["S00", "S20", "S40A", "S40B", "S60", "SMOKE"]
FRAMES = 30
DEPTH_W, DEPTH_H = 848, 480
COLOR_W, COLOR_H = 640, 480
DEPTH_BYTES = DEPTH_W * DEPTH_H * 2      # 814,080
COLOR_BYTES = COLOR_W * COLOR_H * 3      # 921,600
MIN_FREE_BYTES = 2 * 1024 ** 3           # 2 GiB headroom for a full session


def now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def preflight(rs, expected_serial: str | None) -> dict:
    ctx = rs.context()
    devices = list(ctx.query_devices())
    if not devices:
        raise SystemExit("STOP: no RealSense device enumerated")
    if len(devices) > 1:
        names = [d.get_info(rs.camera_info.serial_number) for d in devices]
        raise SystemExit(f"STOP: {len(devices)} devices present {names}; disconnect all but one")
    dev = devices[0]
    serial = dev.get_info(rs.camera_info.serial_number)
    if expected_serial and serial != expected_serial:
        raise SystemExit(f"STOP: serial {serial} != expected {expected_serial}")
    sensor = dev.first_depth_sensor()

    def opt(option):
        try:
            return float(sensor.get_option(option)) if sensor.supports(option) else None
        except Exception:  # noqa: BLE001
            return None

    return {
        "serial": serial,
        "firmware": dev.get_info(rs.camera_info.firmware_version),
        "product_line": dev.get_info(rs.camera_info.product_line),
        "depth_scale_m_per_unit": float(sensor.get_depth_scale()),
        "depth_scale_source": "rs2_get_depth_scale() at run time",
        "emitter_enabled": opt(rs.option.emitter_enabled),
        "exposure_us": opt(rs.option.exposure),
        "gain": opt(rs.option.gain),
        "laser_power": opt(rs.option.laser_power),
        "host": platform.node(),
        "python": platform.python_version(),
        "captured_at": now(),
    }


def check_space(path: Path) -> None:
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_BYTES:
        raise SystemExit(f"STOP: only {free/2**30:.2f} GiB free at {path}; need >= 2 GiB")


def write_failure(pdir: Path, stage: str, exc: BaseException) -> None:
    """Leave evidence, never silence. The partial session stays on disk and is marked INCOMPLETE."""
    try:
        (pdir / "meta" / "FAILURE.json").write_text(json.dumps({
            "failed_at": now(), "stage": stage, "exception": type(exc).__name__,
            "message": str(exc)[:2000], "partial_session": True,
            "instruction": "do not analyse; re-capture this placement",
        }, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def run(args) -> int:
    try:
        import pyrealsense2 as rs
    except ImportError:
        raise SystemExit("STOP: pyrealsense2 is not importable. This program runs on the Jetson only.")
    import numpy as np

    out = Path(args.out).expanduser().resolve()
    pdir = out / args.target / f"placement_{args.placement:02d}"
    if pdir.exists() and any(pdir.iterdir()):
        raise SystemExit(f"STOP: {pdir} already contains data; refusing to overwrite")
    for sub in ("raw/depth", "raw/color", "meta", "reference"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)

    check_space(out)

    info = preflight(rs, args.serial)
    cfg = rs.config()
    cfg.enable_device(info["serial"])
    cfg.enable_stream(rs.stream.depth, DEPTH_W, DEPTH_H, rs.format.z16, 30)
    cfg.enable_stream(rs.stream.color, COLOR_W, COLOR_H, rs.format.rgb8, 30)

    pipe = rs.pipeline()
    stage = "pipeline_start"
    try:
        profile = pipe.start(cfg)
        ds = profile.get_stream(rs.stream.depth).as_video_stream_profile()
        cs = profile.get_stream(rs.stream.color).as_video_stream_profile()
        di, ci = ds.get_intrinsics(), cs.get_intrinsics()

        (pdir / "meta" / "intrinsics.json").write_text(json.dumps({
            "fx": di.fx, "fy": di.fy, "cx": di.cx, "cy": di.cy,
            "width": di.width, "height": di.height, "model": str(di.model), "coeffs": list(di.coeffs),
            "_stream": "depth", "_source": "rs2_intrinsics at run time",
            "color": {"fx": ci.fx, "fy": ci.fy, "cx": ci.cx, "cy": ci.cy,
                      "width": ci.width, "height": ci.height},
        }, indent=2), encoding="utf-8")
        (pdir / "meta" / "depth_scale.json").write_text(json.dumps({
            "depth_scale_m_per_unit": info["depth_scale_m_per_unit"],
            "source": info["depth_scale_source"]}, indent=2), encoding="utf-8")
        (pdir / "meta" / "device_config.json").write_text(json.dumps(info, indent=2, default=str),
                                                          encoding="utf-8")

        stage = "capture"
        man_path = pdir / "meta" / "frame_manifest.csv"
        ts_path = pdir / "meta" / "frame_timestamps.csv"
        with man_path.open("w", newline="", encoding="utf-8") as mfh, \
                ts_path.open("w", newline="", encoding="utf-8") as tfh:
            mw = csv.writer(mfh)
            mw.writerow(["frame", "depth", "depth_sha256", "depth_bytes",
                         "color", "color_sha256", "color_bytes", "valid_ratio", "write_ms"])
            tw = csv.writer(tfh)
            tw.writerow(["frame_index", "device_timestamp_ms", "host_timestamp_iso",
                         "color_device_timestamp_ms"])
            for i in range(args.frames):
                t0 = time.perf_counter()
                frames = pipe.wait_for_frames(timeout_ms=5000)
                dframe, cframe = frames.get_depth_frame(), frames.get_color_frame()
                if not dframe or not cframe:
                    raise RuntimeError(f"frame {i}: depth/colour not paired in one frameset")
                d = np.asarray(dframe.get_data())
                c = np.asarray(cframe.get_data())
                if d.shape != (DEPTH_H, DEPTH_W) or d.dtype != np.uint16:
                    raise RuntimeError(f"frame {i}: depth {d.shape} {d.dtype}")
                if c.shape != (COLOR_H, COLOR_W, 3):
                    raise RuntimeError(f"frame {i}: colour {c.shape}")

                dp = pdir / "raw" / "depth" / f"frame_{i:03d}.raw"
                cp = pdir / "raw" / "color" / f"frame_{i:03d}.rgb8.raw"
                d.tofile(dp)
                c.tofile(cp)
                if dp.stat().st_size != DEPTH_BYTES or cp.stat().st_size != COLOR_BYTES:
                    raise RuntimeError(f"frame {i}: unexpected byte size")
                ms = (time.perf_counter() - t0) * 1000.0
                vr = float((d > 0).mean())
                mw.writerow([i, dp.name, sha256_file(dp), dp.stat().st_size,
                             cp.name, sha256_file(cp), cp.stat().st_size, f"{vr:.6f}", f"{ms:.1f}"])
                tw.writerow([i, dframe.get_timestamp(), now(), cframe.get_timestamp()])
                mfh.flush(); tfh.flush()
                print(f"  frame {i:02d}  valid={vr:.3f}  write={ms:.1f} ms")

        (pdir / "meta" / "CAPTURE_INFO.txt").write_text(
            f"captured_at={now()}\ntarget={args.target}\nplacement={args.placement}\n"
            f"frames={args.frames}\ncolor_format=raw_rgb8\noperator={args.operator}\n", encoding="utf-8")
        print(f"\nOK: {args.frames} frames in {pdir}")
        print("NEXT: 3 independent reference readings -> reference/reference_readings.csv")
        return 0
    except BaseException as exc:  # noqa: BLE001
        write_failure(pdir, stage, exc)
        if isinstance(exc, KeyboardInterrupt):
            print("\nInterrupted: session is INCOMPLETE (meta/FAILURE.json written).")
            return 130
        print(f"\nFAILED at {stage}: {type(exc).__name__}: {exc}")
        print("meta/FAILURE.json written; the partial session is kept as evidence.")
        return 1
    finally:
        try:
            pipe.stop()
        except Exception:  # noqa: BLE001
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="S40 D435 capture (Jetson only)")
    ap.add_argument("--target", required=True, choices=TARGETS)
    ap.add_argument("--placement", required=True, type=int, choices=range(1, 6))
    ap.add_argument("--out", required=True)
    ap.add_argument("--serial", default=None)
    ap.add_argument("--operator", default="")
    ap.add_argument("--frames", type=int, default=FRAMES,
                    help="frames to capture; 30 for a real placement, 5 for ENGINEERING_SMOKE_ONLY")
    ap.add_argument("--confirm", required=True,
                    help="must be exactly CAPTURE — human confirmation the scene is ready")
    a = ap.parse_args(argv)
    if a.confirm != "CAPTURE":
        print("Refusing: pass --confirm CAPTURE after checking scene, target and operator")
        return 2
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
