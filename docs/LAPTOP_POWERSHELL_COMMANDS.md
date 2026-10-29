# LAPTOP — PowerShell command flow

Run these on **device B (laptop, Windows + VSCode)**. The desktop PC cannot reach the Jetson; this is the
bridge.

Placeholders to replace before running:

| placeholder | meaning |
|---|---|
| `<YOUR_ACCOUNT>/<PRIVATE_REPO>` | the GitHub private repository you created |
| `<JETSON>` | the SSH **host alias** your laptop already uses (`ssh <JETSON>` must work today) |

---

## 0. Preconditions

```powershell
git --version                  # any modern git
ssh <JETSON> hostname          # must print the Jetson hostname — if this fails, stop here
ssh <JETSON> "python3 --version; python3 -c 'import numpy;print(numpy.__version__)'"
```

If the last line fails or shows Python < 3.10, see `JETSON_OFFLINE_INSTALL.md` §3.

## 1. Clone

```powershell
$Repo = "https://github.com/<YOUR_ACCOUNT>/<PRIVATE_REPO>.git"
$Work = "$HOME\work"
New-Item -ItemType Directory -Force -Path $Work | Out-Null
Set-Location $Work
git clone $Repo w6-release
Set-Location .\w6-release
```

## 2. Verify SHA256 (authoritative, 5 files)

```powershell
$ok = 0; $bad = 0
Get-Content .\SHA256SUMS_RELEASE.txt | ForEach-Object {
    if ($_ -match '^([0-9a-f]{64})\s+(.+)$') {
        $h = $Matches[1]; $p = $Matches[2].Trim()
        if ((Test-Path $p) -and ((Get-FileHash $p -Algorithm SHA256).Hash.ToLower() -eq $h)) {
            $ok++; Write-Host "OK      $p" -ForegroundColor Green
        } else {
            $bad++; Write-Host "MISMATCH $p" -ForegroundColor Red
        }
    }
}
Write-Host "verified=$ok failures=$bad"
if ($bad -ne 0) { throw "Release verification failed — do not deploy." }
```

Expected: `verified=5 failures=0`.

Quick spot check of the archive alone:

```powershell
(Get-FileHash .\package\W6_TRANSFER_PACKAGE.tar.gz -Algorithm SHA256).Hash.ToLower()
# expect 58cd3facea991083999f6662be6dd908d5f7bce50e8b90314b8769d802643c3b
```

## 3. SSH host identity

```powershell
ssh-keygen -F <JETSON>        # prints the known_hosts entry if the host is already trusted
ssh <JETSON> hostname         # a successful connect proves the key matches
```

If `ssh-keygen -F` prints nothing, the host is not yet trusted: connect once interactively, read the
fingerprint, and confirm it **out of band** before typing `yes`. Never use
`-o StrictHostKeyChecking=no` and never delete an existing known_hosts line.

## 4. Create the target directory (does not touch Stage07-P0)

```powershell
$JETSON = "<JETSON>"
$Dest   = "~/sci_camera_audit/SCI_STAGE07_P1_W6_INTEGRATION"
ssh $JETSON "mkdir -p $Dest && ls -la ~/sci_camera_audit/"
```

The `ls` confirms `SCI_STAGE07_P0_D435_PREFLIGHT/` still exists and is untouched.

## 5. Upload

```powershell
scp .\package\W6_TRANSFER_PACKAGE.tar.gz "${JETSON}:$Dest/"
scp .\SHA256SUMS_RELEASE.txt            "${JETSON}:$Dest/"
scp -r .\integration                    "${JETSON}:$Dest/"
```

## 6. Remote verification (must pass before anything is run)

```powershell
ssh $JETSON "cd $Dest && sha256sum W6_TRANSFER_PACKAGE.tar.gz && tar -tzf W6_TRANSFER_PACKAGE.tar.gz | grep -E '^/|\.\./' && echo UNSAFE || echo paths-safe"
```

Expected:

```text
58cd3facea991083999f6662be6dd908d5f7bce50e8b90314b8769d802643c3b  W6_TRANSFER_PACKAGE.tar.gz
paths-safe
```

If the hash differs, **stop** and do not extract.

## 7. Extract and test on the Jetson

```powershell
ssh $JETSON "cd $Dest && tar -xzf W6_TRANSFER_PACKAGE.tar.gz && cd w6_pkg && python3 -m unittest discover -s tests"
ssh $JETSON "cd $Dest/w6_pkg && PYTHONPATH=src python3 -m w6.cli selfcheck"
ssh $JETSON "cd $Dest && python3 -m unittest integration.test_eligibility -v"
```

Expected: `Ran 20 tests ... OK`, `"selfcheck": "PASS"`, `Ran 5 tests ... OK`.

## 8. Real-frame compatibility (see JETSON_OFFLINE_INSTALL.md §5 for the full form)

```powershell
ssh $JETSON "ls -la ~/sci_camera_audit/SCI_STAGE07_P0_D435_PREFLIGHT/"
```

Then run `offline_check.py` on the Jetson with the real `--depth`, `--intrinsics`, `--depth-scale` and
`--meta-dir`. Do not pass a hard-coded scale.

---

## Failure handling

| symptom | action |
|---|---|
| `git clone` asks for credentials | use a personal access token in the Windows credential manager; never paste a token into a file in the repo |
| `verified` < 5 | stop; the clone is corrupt or the repo was modified |
| `ssh` host key changed | **stop**; do not delete the known_hosts entry until the change is explained |
| `sha256sum` mismatch on the Jetson | stop; re-upload |
| `Ran 20 tests` shows failures | stop; report the failing test names |
| `offline_check.py` reports `all_ok: false` | report which of the ten checks failed; do not "fix" by editing the script |
