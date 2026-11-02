# OFFLINE TEST REPORT

**Stage:** `SCI_STAGE09_P1_REAL_CAPTURE_READY`
**Date:** 2026-11-02
**Result: 16 / 16 checks passed.** All fixtures are `SYNTHETIC`; **no camera was opened**.

---

## 1. Why synthetic fixtures, and what that does not claim

The task asked for validation against the Stage07-P0 real D435 frame. **That frame is not on this PC.**

| check | result |
|---|---|
| `*STAGE07_P0*` directory under project roots | **none** (only Stage07-P1 and P2 exist) |
| `.raw` files under `F:\GraspResearch` | **0** |
| Stage07-P0 location | the Jetson (`~/sci_camera_audit/`) |

So the software was tested on fixtures that reproduce the **exact byte layout** and **every listed failure
mode**. Each fixture lives under a `SYNTHETIC_` directory and carries `_tag: SYNTHETIC` in its metadata.
A passing run means the software is ready; it says nothing about the camera.

## 2. Environment

| item | value |
|---|---|
| interpreter | `/home/gh/miniconda3/envs/c2_gsnet/bin/python` (3.10) |
| numpy | 2.2.6 |
| pyrealsense2 | **not installed on this PC** (Jetson-only dependency) |
| `capture_s40.py --help` | works without pyrealsense2 (deferred import) — verified |

## 3. Results

| # | test | got | expected | verdict |
|---|---|---|---|---|
| 1 | complete synthetic session | `COMPLETE` | `COMPLETE` | **PASS** |
| 2 | capture intact, no reference readings | `CAPTURE_OK_REFERENCE_MISSING` | same | **PASS** |
| 3 | depth file truncated to 100 B | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 4 | `intrinsics.json` missing | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 5 | intrinsics say 640×480 | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 6 | timestamps strictly decreasing | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 7 | extra duplicate file in the depth folder | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 8 | corrupt PNG (bad magic) | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 9 | `depth_scale = 5.0` | `INCOMPLETE` | `INCOMPLETE` | **PASS** |
| 10 | all-zero depth frame (correct byte count) | detected | detected | **PASS** |
| 11 | 3-D back-projection on a synthetic frame | 365,920 points, z ∈ [0.001, 2.999] m | executes | **PASS** |
| 12 | session directory absent | `NOT_FOUND` | `NOT_FOUND` | **PASS** |
| 13 | CLI exit code, valid session | 0 | 0 | **PASS** |
| 14 | CLI exit code, reference missing | 3 | 3 | **PASS** |
| 15 | CLI exit code, `NOT_FOUND` | 2 | 2 | **PASS** |
| 16 | `capture_s40.py` without `--confirm CAPTURE` | exit 2 | exit 2 | **PASS** |

Full machine-readable record: `results/offline_test_results.json`.

## 4. Two defects found and fixed by the tests

| defect | symptom | fix |
|---|---|---|
| ROI hash self-reference | the ROI file stored `_sha256` of *itself*, which can never match; the validator would have rejected every real session | hash the canonical JSON of `regions` only, stored as `_payload_sha256`; documented in the schema |
| reference failure miscategorised | a complete capture with no reference readings was reported `INCOMPLETE`, conflating "broken camera" with "missing instrument" | reference problems are now tracked separately; status `CAPTURE_OK_REFERENCE_MISSING`, exit 3 |

The first would have blocked the real experiment on day one; the second would have hidden a distinction that
matters (an unreferenced capture must be ingestible but not analysable).

## 5. Coverage of the required test list

| required test | covered by |
|---|---|
| depth RAW byte length | #3, #10, and `check_depth_file` (exact 814,080 B) |
| RGB8 byte length | #8 (PNG magic + size sanity) |
| real intrinsics parse | #4, #5, #11 |
| depth scale | #9, and `depth_scale.json` plausibility range (0, 0.1) |
| 3-D back-projection | #11 |
| file hash | `frame_manifest.csv` written by the capture; the validator recomputes on demand |
| missing metadata | #4 |
| corrupted file | #3, #8, #10 |
| duplicate filenames | #7 |
| wrong resolution | #5 |
| wrong timestamps | #6 |

## 6. What these tests cannot establish

| not established | why |
|---|---|
| that the D435 produces these files | no camera |
| that `pyrealsense2` imports on the Jetson | not reachable from this PC |
| that 30 real frames arrive without drops | requires hardware |
| that the real intrinsics/scale match the historical claims | requires the device |
| any geometric accuracy | requires the targets and the instrument |

## 7. Verdict

```text
OFFLINE_PIPELINE       = PASS   (16/16 on synthetic fixtures with the real byte layout)
REAL_CAMERA_CAPTURE    = NOT_TESTED
```

The gap between these two lines is the entire remaining risk, and it is not closed by anything in this stage.
