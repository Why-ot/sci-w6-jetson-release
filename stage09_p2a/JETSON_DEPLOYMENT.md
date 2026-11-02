# JETSON DEPLOYMENT — capture software

**Stage:** `SCI_STAGE09_P1_REAL_CAPTURE_READY`
Route: desktop PC → private GitHub repo → laptop → SSH/SCP → Jetson. The desktop PC cannot reach the Jetson.

---

## 0. What must be true before you start

```text
[ ] the Jetson is reachable from the LAPTOP (ssh <alias> works)
[ ] pyrealsense2 is installed on the Jetson   (python3 -c "import pyrealsense2")
[ ] numpy is available
[ ] the D435 is connected and is the ONLY RealSense device on the machine
[ ] the S40/S20/S60/S00 targets are physically present and accepted (Stage09-P0 §2)
[ ] the reference instrument is chosen and its metadata is at hand
```

If `pyrealsense2` is missing, **stop**. Do not install it from an unknown source; record the missing
dependency and escalate. Never `sudo pip install` into the system Python or the ROS workspace.

## 1. Package contents

```text
capture_s40.py               capture program (Jetson only)
validate_capture.py          offline validator (anywhere)
w6_like_backproject.py       back-projection helper used by the tests
tests/test_validate_capture.py
REAL_METADATA_SCHEMA.json
CAPTURE_DESIGN.md · OFFLINE_TEST_REPORT.md · JETSON_DEPLOYMENT.md · EXPERIMENT_OPERATOR_GUIDE.md
```

## 2. Copy to the Jetson

```powershell
# on the LAPTOP (PowerShell)
$JETSON = "<your-ssh-alias>"
$Dest   = "~/sci_camera_audit/SCI_STAGE09_P1_CAPTURE"
ssh $JETSON "mkdir -p $Dest"
scp -r .\capture_s40.py .\validate_capture.py .\w6_like_backproject.py `
       .\tests .\REAL_METADATA_SCHEMA.json .\*.md "${JETSON}:$Dest/"
```

The capture writes to `~/sci_camera_audit/S40_SESSION/` — **never** into `SCI_STAGE07_P0_D435_PREFLIGHT/`.

## 3. Verify on the Jetson

```bash
cd ~/sci_camera_audit/SCI_STAGE09_P1_CAPTURE

python3 --version
python3 -c "import numpy, pyrealsense2 as rs; print('numpy', numpy.__version__); print('rs ok')"

# the validator must run without a camera
python3 validate_capture.py --session /nonexistent
# expected: NOT_FOUND, exit 2

# the capture must refuse without confirmation
python3 capture_s40.py --target S40A --placement 1 --out /tmp/x --confirm no
# expected: exit 2

# the offline test suite must pass on the Jetson too
python3 tests/test_validate_capture.py
# expected: 16/16 checks passed
```

## 4. Pre-capture check (does not record a session)

```bash
python3 - <<'PY'
import pyrealsense2 as rs
ctx = rs.context(); devs = list(ctx.query_devices())
print("devices:", len(devs))
for d in devs:
    print("  serial", d.get_info(rs.camera_info.serial_number),
          "| fw", d.get_info(rs.camera_info.firmware_version),
          "|", d.get_info(rs.camera_info.product_line))
    s = d.first_depth_sensor()
    print("  depth_scale", s.get_depth_scale())
PY
```

Record the output. If more than one device appears, disconnect all but the one to be used.

## 5. Capture command

```bash
cd ~/sci_camera_audit/SCI_STAGE09_P1_CAPTURE
python3 capture_s40.py \
    --target S40A --placement 1 \
    --out ~/sci_camera_audit/S40_SESSION \
    --serial <SERIAL_FROM_STEP_4> \
    --operator "<name>" \
    --confirm CAPTURE
```

Repeat for `--target` ∈ {S00, S20, S40A, S40B, S60} × `--placement` ∈ {1..5} = **25 invocations**.

**Before each invocation the operator must confirm:** the target is the named one, the scene is static, the
hands are clear, and the placement index is the intended one. The program will not run without `--confirm
CAPTURE` typed in full.

## 6. After each capture

1. take **3 independent reference readings** and fill `reference/reference_readings.csv`
2. fill `meta/placement_metadata.csv` (distance, tilt, temperature, illumination, emitter state)
3. validate:

```bash
python3 validate_capture.py --session ~/sci_camera_audit/S40_SESSION --require-reference
```

Exit codes: `0` complete · `3` capture fine, reference missing · `1` structural problem · `2` not found.

## 7. Data return to the PC

```powershell
# on the LAPTOP
scp -r ${JETSON}:~/sci_camera_audit/S40_SESSION .\S40_SESSION
Get-ChildItem .\S40_SESSION -Recurse -File | Measure-Object Length -Sum   # ~760 depth frames ≈ 620 MB
```

Then copy from the laptop to the desktop PC by whatever channel is available, and re-validate on the PC:

```bash
python3 validate_capture.py --session S40_SESSION --require-reference --json > session_validation.json
```

## 8. Stop conditions

| condition | action |
|---|---|
| no device, or two devices | stop; fix the cabling; do not proceed |
| serial mismatch | stop; the wrong camera is attached |
| `depth_scale` outside (0, 0.1) | stop; the device is not reporting a sane scale |
| a frame fails the shape/dtype check | the program aborts; re-capture the placement |
| Ctrl-C | the session is partial; re-capture that placement, never patch it |
| validator exit 1 | do not analyse; read the reported reasons |
| validator exit 3 | the capture may be kept, but **no formal S40 result may be produced** |

## 9. Prohibited

```text
sudo · system-Python installs · touching the ROS workspace
starting ROS or any robot-control node
sending CAN frames · moving the arm or gripper
opening the camera outside this program
using a D435 reading as a reference value
reporting a step error while the validator says exit 3
```
