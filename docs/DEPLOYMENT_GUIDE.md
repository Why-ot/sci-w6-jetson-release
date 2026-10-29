# DEPLOYMENT GUIDE — W6 S40 measurement package

**Package:** `W6_TRANSFER_PACKAGE.tar.gz` (15,719 B, sha256 `58cd3facea991083999f6662be6dd908d5f7bce50e8b90314b8769d802643c3b`)
**Route:** desktop PC → private GitHub repo → laptop → SSH/SCP → Jetson.
**The desktop PC is not on the same network as the Jetson and must not attempt to reach it.**

---

## What this package is

An offline geometry-analysis toolkit for the S40 two-plane reference. It reads saved raw D435 frames and
computes plane fits, separation, and validity statistics. It **does not** open a camera, connect to ROS, or
command the robot.

| component | purpose |
|---|---|
| `package/W6_TRANSFER_PACKAGE.tar.gz` | the W6 software (source, 20 unit tests, configs, templates) |
| `integration/offline_check.py` | ten-point real-frame compatibility check |
| `integration/eligibility.py` | gate that refuses to report an S40 result before all physical preconditions exist |
| `integration/test_eligibility.py` | 5 tests for that gate |

---

## Step 1 — desktop PC: push to a **private** GitHub repository

The repository URL must be supplied by you. Nothing is pushed until you provide it.

```bash
cd /mnt/f/GraspResearch/SCI_RESTART_20261008/SCI_STAGE07_P2_W6_GIT_RELEASE
git remote add origin https://github.com/<YOUR_ACCOUNT>/<PRIVATE_REPO>.git
git push -u origin main
```

Requirements:

* the repository must be **PRIVATE** (it contains no secrets, but it is research infrastructure);
* never `git add -A` from the project root — this directory is its own repository;
* never add the two third-party repos under `F:\GraspResearch\third_party\`.

## Step 2 — laptop: clone

```powershell
cd $HOME\work
git clone https://github.com/<YOUR_ACCOUNT>/<PRIVATE_REPO>.git w6-release
cd w6-release
```

## Step 3 — laptop: verify the SHA256 manifest

PowerShell:

```powershell
$ok = 0; $bad = 0
Get-Content SHA256SUMS_RELEASE.txt | ForEach-Object {
    if ($_ -match '^([0-9a-f]{64})\s+(.+)$') {
        $h = $Matches[1]; $p = $Matches[2].Trim()
        if ((Test-Path $p) -and ((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -eq $h)) { $ok++ }
        else { $bad++; Write-Host "MISMATCH: $p" -ForegroundColor Red }
    }
}
"verified=$ok failures=$bad"
```

Proceed only if `failures=0`. Expected: 5 files verified.

## Step 4 — laptop: copy to the Jetson over the existing SSH connection

Replace `<JETSON>` with the **host alias you already use** (from your laptop's `~/.ssh/config`). Do not use the
historical addresses `192.168.1.102` / `192.168.31.230` — they are not valid any more.

```powershell
$JETSON = "<your-ssh-alias>"
ssh $JETSON "mkdir -p ~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION"
scp package\W6_TRANSFER_PACKAGE.tar.gz  ${JETSON}:~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION/
scp -r integration                       ${JETSON}:~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION/
scp SHA256SUMS_RELEASE.txt               ${JETSON}:~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION/
```

**Never** copy into `~/sci_camera_audit/SCI_STAGE07_P0_D435_PREFLIGHT/` — that directory holds the real
captures and must not be overwritten.

## Step 5 — Jetson: verify and extract

```bash
cd ~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION

# 1. archive hash
sha256sum W6_TRANSFER_PACKAGE.tar.gz
#    must print: 58cd3facea991083999f6662be6dd908d5f7bce50e8b90314b8769d802643c3b

# 2. path safety before extracting anything
tar -tzf W6_TRANSFER_PACKAGE.tar.gz | grep -E '^/|\.\./' && echo "UNSAFE - STOP" || echo "paths safe"

# 3. extract (creates ./w6_pkg/)
tar -xzf W6_TRANSFER_PACKAGE.tar.gz

# 4. per-file verification against the original W6 manifest
cd w6_pkg && sha256sum -c SHA256SUMS.txt; cd ..
```

Expected: step 4 reports every line `OK` (35 entries; 12 are files present in the package, the rest are
reports/results that are intentionally not shipped — see the note below).

> **Note on step 4.** `w6_pkg/SHA256SUMS.txt` is the *original frozen* manifest of the full W6 stage, which
> includes reports and results that are deliberately not distributed. `sha256sum -c` will print
> "No such file or directory" for those 23 entries and `OK` for the 12 shipped files. That is expected. The
> authoritative check for this release is `SHA256SUMS_RELEASE.txt` (5 files, step 3).

## Step 6 — Jetson: check Python and numpy

```bash
python3 --version                  # must be >= 3.10
python3 -c "import numpy; print('numpy', numpy.__version__)"
```

If Python < 3.10 or numpy is missing, create an isolated environment (never `sudo`, never touch system Python
or the ROS workspace):

```bash
python3 -m venv ~/w6_venv
~/w6_venv/bin/pip install numpy
export PATH=~/w6_venv/bin:$PATH
```

## Step 7 — Jetson: run the self-test and the 20 unit tests

```bash
cd ~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION/w6_pkg
python3 -m unittest discover -s tests          # expect: Ran 20 tests ... OK
PYTHONPATH=src python3 -m w6.cli selfcheck     # expect: "selfcheck": "PASS"

cd ..
python3 -m unittest integration.test_eligibility -v   # expect: Ran 5 tests ... OK
```

## Step 8 — Jetson: offline compatibility check on the real Stage07-P0 frame

Do **not** use synthetic intrinsics or a hard-coded depth scale. Both must come from the capture metadata.

```bash
P0=~/sci_camera_audit/SCI_STAGE07_P0_D435_PREFLIGHT
ls -la $P0                                # locate the real raw depth + metadata

SCALE=$(python3 -c "import json;print(json.load(open('$P0/<meta>/depth_scale.json'))['depth_scale_m_per_unit'])")

python3 integration/offline_check.py \
    --depth      "$P0/<path>/frame_000.raw" \
    --intrinsics "$P0/<meta>/intrinsics.json" \
    --depth-scale "$SCALE" \
    --width 848 --height 480 \
    --meta-dir   "$P0/<meta>" \
    --label      REAL_D435_STAGE07P0 \
    --out        offline_check_real.json
```

Expected output: ten checks with `"ok": true`, `"all_ok": true`, and

```json
"s40_eligibility": { "allowed": false, "blocking_reasons": [ "... 10 reasons ..." ] }
```

**`allowed: false` is the correct result.** The S40 target does not exist yet, so no S40 separation may be
reported. If the gate ever returns `true` before the target is built and the 15 reference readings are taken,
that is a defect and must be reported.

## If the real frame cannot be found

Report `REAL_D435_FRAME = NOT_FOUND` with the `ls -la` output of `$P0`. **Do not re-open the camera to
manufacture a frame**, and do not substitute the synthetic fixture for a real result.

---

## What must never be done with this package

| forbidden | why |
|---|---|
| opening the D435 / capturing new frames | outside the scope of this deployment |
| starting ROS or any robot-control node | not authorised |
| moving the arm or gripper, sending CAN frames | not authorised |
| modifying files under `SCI_STAGE07_P0_D435_PREFLIGHT/` | real capture data, read-only |
| reporting an S40 step, accuracy or U95 | the target does not exist; `NOT_AVAILABLE` |
| `sudo`, system-Python installs, editing the ROS workspace | use a venv |
| committing raw data, keys or credentials to the repo | `.gitignore` blocks them; keep it that way |
