# CAPTURE DESIGN — S40/S20/S60/S00 on the D435

**Stage:** `SCI_STAGE09_P1_REAL_CAPTURE_READY`
**Status:** software complete and offline-tested. **No camera has been opened.** No capture exists.

---

## 1. Two programs, one contract

| program | runs on | needs pyrealsense2 | purpose |
|---|---|---|---|
| `capture_s40.py` | Jetson | **yes** | record 30 depth + 30 colour frames with full metadata |
| `validate_capture.py` | anywhere | no (numpy only) | decide whether a session is complete and analysable |

The validator is the gate. A capture that the validator rejects cannot produce an S40 number, regardless of
who runs the analysis.

## 2. Capture contract

| item | value | enforced by |
|---|---|---|
| depth stream | 848 × 480, Z16, 30 fps | `cfg.enable_stream(..., rs.format.z16, 30)` |
| colour stream | 640 × 480, RGB8, 30 fps | `cfg.enable_stream(..., rs.format.rgb8, 30)` |
| depth file | headerless little-endian `uint16`, **814,080 B** | validator byte check |
| colour file | PNG, 921,600 B raw before encoding | validator magic + size sanity |
| frames per placement | **30 + 30** | validator count check |
| placements per target | **5** | validator directory check |
| file hash | per-file SHA256 in `frame_manifest.csv` | capture writes, validator can recompute |
| timestamps | device timestamp (ms) + host ISO, strictly increasing | validator monotonicity check |

## 3. What is read from the device at run time (never copied from a document)

```
serial_number          product_line        firmware_version
depth_scale            ← rs2_get_depth_scale()
depth intrinsics       ← rs2_intrinsics of the depth stream (fx, fy, cx, cy, model, coeffs)
colour intrinsics      ← rs2_intrinsics of the colour stream
emitter_enabled        exposure            gain            laser_power
```

All of it is written to `meta/device_config.json` and `meta/intrinsics.json` **before** the first frame.
`--serial` optionally pins the expected device; a mismatch aborts.

**No value in this project's documentation is used as a device value.** The serial `317422072133`, the
`0.0010000000475` depth scale and the `927.17/927.367/651.315/349.621` intrinsics that appear elsewhere are
*historical claims*; the capture reads the real ones and the validator checks them for plausibility.

## 4. Directory layout produced

```
SESSION/
  S40A/placement_01/
    raw/depth/frame_000.raw … frame_029.raw     814,080 B each
    raw/color/frame_000.png … frame_029.png
    meta/intrinsics.json
    meta/device_config.json
    meta/depth_scale.json
    meta/frame_timestamps.csv
    meta/frame_manifest.csv                     per-file SHA256
    meta/placement_metadata.csv                 filled by the operator
    meta/roi_definition.json                    filled after placement 1, then frozen
    meta/CAPTURE_INFO.txt
    reference/reference_readings.csv            3 readings, instrument fields mandatory
  S20/ … S40B/ … S60/ … S00/                    same structure
```

## 5. Safety properties in code

| property | mechanism |
|---|---|
| no accidental capture | `--confirm CAPTURE` is mandatory; any other value exits 2 |
| no overwrite | aborts if the placement directory already contains files |
| no robot control | imports only `pyrealsense2`, `numpy`, `PIL`, stdlib — no ROS, no CAN, no socket |
| no silent partial session | Ctrl-C prints "session is INCOMPLETE", exits 130 |
| no wrong device | `--serial` pin, plus a hard stop if more than one device is enumerated |
| frame integrity | shape and dtype checked on every frame before writing |

## 6. The validator's decision rule

| status | exit | meaning |
|---|---|---|
| `COMPLETE` | 0 | all 5 targets × 5 placements × 30+30 frames, metadata, ≥3 reference readings, frozen ROI |
| `CAPTURE_OK_REFERENCE_MISSING` | 3 | the capture is intact but the independent reference is absent → **no formal S40 result may be produced** |
| `INCOMPLETE` | 1 | a structural problem (missing frames, bad intrinsics, non-monotonic time, corrupt file, …) |
| `NOT_FOUND` | 2 | the session directory does not exist |

The distinction between exit 1 and exit 3 is deliberate: a missing instrument is not a broken camera, and
collapsing the two would let an unreferenced capture be analysed by accident.

## 7. S00 is not a step target

`S00` is a plane reference. The validator skips the step reference requirement for it and annotates it
`"S00 is a plane reference; step analysis is not applicable"`. Its only admissible products are flatness,
local noise and — with an external length standard — absolute distance bias.

## 8. Quality targets are observations, not filters

The 90 % valid-depth ratio and the 0.2 mm plane RMS do not appear anywhere in the validator as rejection
criteria. They are recorded (the capture prints the per-frame valid ratio) and reported. **No frame is
deleted for missing a target**; exclusions require an explicit reason code in `frame_manifest.csv`.

## 9. Why there is no real-frame test in this stage

The only real D435 frames in this project are the Stage07-P0 pair, which live on the Jetson. This PC has no
copy (verified: no `*STAGE07_P0*` directory under any project root; zero `.raw` files). The software was
therefore validated on **SYNTHETIC fixtures that reproduce the exact byte layout and every failure mode**,
each labelled `_tag: SYNTHETIC` and written under a `SYNTHETIC_` directory. That is a software test, not a
camera test, and it is reported as such.

## 10. Artefacts

```text
capture_s40.py · validate_capture.py · w6_like_backproject.py
tests/test_validate_capture.py · results/offline_test_results.json
REAL_METADATA_SCHEMA.json
```
