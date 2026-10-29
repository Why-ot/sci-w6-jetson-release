# W6 S40 measurement package — release

Offline geometry analysis for the S40 two-plane depth reference (Intel RealSense D435).
Reads saved raw frames; never opens a camera, never touches ROS or the robot.

## Contents

| path | what |
|---|---|
| `package/W6_TRANSFER_PACKAGE.tar.gz` | W6 software: source, 20 unit tests, configs, templates |
| `integration/offline_check.py` | ten-point real-frame compatibility check (no hard-coded intrinsics or scale) |
| `integration/eligibility.py` | gate that refuses to report an S40 result before all physical preconditions exist |
| `integration/test_eligibility.py` | 5 tests for the gate |
| `docs/DEPLOYMENT_GUIDE.md` | eight-step route: PC → GitHub → laptop → Jetson |
| `docs/LAPTOP_POWERSHELL_COMMANDS.md` | copy-paste PowerShell for the laptop |
| `docs/JETSON_OFFLINE_INSTALL.md` | verification, extraction and self-test on the Jetson |
| `SHA256SUMS_RELEASE.txt` | the authoritative 5-file manifest |

## Verify after cloning

```bash
sha256sum -c SHA256SUMS_RELEASE.txt      # Linux/macOS
```
```powershell
# Windows PowerShell — see docs/LAPTOP_POWERSHELL_COMMANDS.md §2
```

## Install on the Jetson

```bash
cd ~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION
sha256sum W6_TRANSFER_PACKAGE.tar.gz     # 58cd3fac...3c3b
tar -tzf W6_TRANSFER_PACKAGE.tar.gz | grep -E '^/|\.\./' || echo paths-safe
tar -xzf W6_TRANSFER_PACKAGE.tar.gz      # -> ./w6_pkg/
cd w6_pkg && python3 -m unittest discover -s tests && PYTHONPATH=src python3 -m w6.cli selfcheck
```

## Scope limits

Analysis only. No camera capture, no ROS, no arm motion, no CAN frames.
The S40 physical target does not exist, so every real S40 precision number stays `NOT_AVAILABLE`.
