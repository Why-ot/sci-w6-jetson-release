# JETSON — offline install and verification

Run on **device C (Yuanyou2 Jetson)**, over the laptop's existing SSH connection.
Target directory: `~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION/` (never `SCI_STAGE07_P0_D435_PREFLIGHT/`).

---

## 1. Receive and verify

```bash
cd ~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION
ls -la

sha256sum W6_TRANSFER_PACKAGE.tar.gz
# expected: 58cd3facea991083999f6662be6dd908d5f7bce50e8b90314b8769d802643c3b
```

**Stop immediately if the hash differs.** Report the actual value; do not proceed and do not re-download
"until it matches" without recording the discrepancy.

## 2. Path-safety check before extracting

```bash
tar -tzf W6_TRANSFER_PACKAGE.tar.gz | head -20
tar -tzf W6_TRANSFER_PACKAGE.tar.gz | grep -E '^/|\.\./' && echo "UNSAFE — STOP" || echo "paths safe"
```

Both must show `paths safe` and a listing rooted at `w6_pkg/`.

## 3. Python and numpy

```bash
python3 --version
python3 -c "import numpy; print('numpy', numpy.__version__)"
uname -m
cat /etc/os-release | head -3
```

| requirement | value | if unmet |
|---|---|---|
| Python | **≥ 3.10** (the code uses `int \| None` annotations) | create a venv with a newer interpreter, or apply the recorded compatibility patch to the copy |
| numpy | any recent | install into a venv |
| arch | aarch64 (expected) | record whatever it is |

Isolated environment (never `sudo`, never system Python, never the ROS workspace):

```bash
python3 -m venv ~/w6_venv
~/w6_venv/bin/pip install numpy
export PATH=~/w6_venv/bin:$PATH
```

## 4. Extract, verify, self-test

```bash
cd ~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION
tar -xzf W6_TRANSFER_PACKAGE.tar.gz          # creates ./w6_pkg/

# per-file check against the ORIGINAL frozen manifest
cd w6_pkg && sha256sum -c SHA256SUMS.txt ; cd ..
```

> 12 files will print `OK`. The other 23 entries are reports/results that were intentionally **not** shipped and
> will print `No such file or directory`. That is expected, not a failure. The release-level check is the
> 5-file `SHA256SUMS_RELEASE.txt` verified on the laptop.

```bash
cd w6_pkg
python3 -m unittest discover -s tests          # EXPECT: Ran 20 tests ... OK
PYTHONPATH=src python3 -m w6.cli selfcheck     # EXPECT: "selfcheck": "PASS"
cd ..

python3 -m unittest integration.test_eligibility -v    # EXPECT: Ran 5 tests ... OK
```

Record the exact interpreter and numpy versions next to these results — the PC used Python 3.10.20 / numpy
2.2.6, and the comparison tolerances are pre-declared in
`SCI_STAGE07_P1_W6_JETSON_INTEGRATION/reports/W6_JETSON_SELFTEST.md` §4.

## 5. Real D435 frame — offline compatibility only

Locate the Stage07-P0 capture. **Read-only. Never modify, never re-capture.**

```bash
P0=~/sci_camera_audit/SCI_STAGE07_P0_D435_PREFLIGHT
ls -la $P0
find $P0 -maxdepth 3 -name '*.raw' -o -maxdepth 3 -name 'intrinsics*.json' -o -maxdepth 3 -name 'depth_scale*.json' | head -20
```

If nothing is found → report **`REAL_D435_FRAME = NOT_FOUND`** with the `ls -la` output and stop.
Do **not** open the camera to produce a frame.

With the files located:

```bash
RAW=$P0/<path>/frame_000.raw
INTR=$P0/<meta>/intrinsics.json
SCALE=$(python3 -c "import json;print(json.load(open('$P0/<meta>/depth_scale.json'))['depth_scale_m_per_unit'])")

python3 integration/offline_check.py \
    --depth "$RAW" --intrinsics "$INTR" --depth-scale "$SCALE" \
    --width 848 --height 480 --meta-dir "$P0/<meta>" \
    --label REAL_D435_STAGE07P0 --out offline_check_real.json

python3 -c "import json;d=json.load(open('offline_check_real.json'));print(d['all_ok']);print([k for k,v in d['checks'].items() if not v.get('ok')])"
```

**Intrinsics and depth scale must come from the capture metadata.** Passing a hard-coded `0.001` or the
GraspNet `camK` values is a defect: the script requires both arguments precisely so that this cannot happen
silently.

### Expected output

```text
checks 01..10: "ok": true
all_ok: true
s40_eligibility.allowed: false      <-- correct: no S40 target exists
```

## 6. Interpreting the real-frame result

| quantity | how to treat it |
|---|---|
| valid-depth ratio of the frame | report with its denominator (`total = 848 × 480 = 407,040`) and the frame identity |
| the historical ratio `0.651894654088` | comparable **only** if that figure is single-frame; if it is a 30-frame statistic, a different single-frame value is expected, not an error |
| depth value range | must be plausible for the working distance; a range like 0.0–0.05 m or 10–20 m indicates a scale error |
| `all_ok: false` | report which check failed and why; never edit the check to make it pass |

## 7. What is still NOT possible

```text
S40 step validation     : NOT_AVAILABLE  (target not built)
reference U95           : UNKNOWN        (0 of 15 readings)
real depth accuracy     : NOT_AVAILABLE  (no independent reference)
absolute depth GT       : NOT_AVAILABLE
grasp success           : NOT_TESTED
```

`offline_check.py` validates the **data path**, not the sensor's accuracy. A passing run means "the software
can read and back-project the frame", nothing more.

## 8. Prohibited on the Jetson

| forbidden | note |
|---|---|
| starting the camera / `rs2` pipeline | this deployment is analysis-only |
| ROS launch files, control nodes | not authorised |
| arm or gripper motion, CAN frames | not authorised |
| writing into `SCI_STAGE07_P0_D435_PREFLIGHT/` | that directory is the raw record |
| `sudo`, system Python changes | use the venv |
| running `w6.cli fit` on a real frame and reporting a separation | the eligibility gate forbids it, and it would be an unbacked S40 result |
