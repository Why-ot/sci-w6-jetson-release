# RELEASE EXECUTIVE REPORT — W6 S40 measurement package

**Task:** `SCI_STAGE07_P2_W6_GIT_DISTRIBUTION`
**Date:** 2026-10-29 (Asia/Shanghai)
**Where the work happened:** desktop PC only. No attempt was made to reach the Jetson from this machine.

---

## 0. Outcome

A self-contained, hash-verified release repository is ready to push. The GitHub remote is **not** configured
because no repository URL was supplied; nothing was pushed anywhere.

| item | result |
|---|---|
| release package built | **YES** — 11 tracked files, commit `1cda803` |
| original artefacts unmodified | **YES** — tarball and integration scripts byte-identical to Stage07-P1 |
| SHA256 chain verified end-to-end | **YES** — 10/10 after a fresh `git clone` |
| GitHub repository | **NEED_USER_INPUT** |
| push | **NOT_ATTEMPTED** |
| laptop deployment commands | **READY** |
| Jetson deployment | **NOT_PERFORMED** |
| real D435 integration | **NOT_PERFORMED** |

## 1. What was read before packaging

| source | result |
|---|---|
| `SCI_W6_PRE_S40_MEASUREMENT/` | 35/35 manifest entries verified |
| `SCI_STAGE07_P1_W6_JETSON_INTEGRATION/package/W6_TRANSFER_PACKAGE.tar.gz` | present, 15,719 B, sha256 `58cd3fac…3c3b` |
| `…/integration/{offline_check,eligibility,test_eligibility}.py` | present |
| `…/reports/P1_EXECUTIVE_REPORT.md`, `SHA256SUMS.txt` | present |

Nothing was modified: the W6 stage and the Stage07-P1 stage were re-hashed after the release was assembled and
both still verify (35/35 and 40/40).

## 2. Release contents

```
SCI_STAGE07_P2_W6_GIT_RELEASE/
  .gitattributes                 * -text  (no line-ending conversion)
  .gitignore                     strict: keys, data, weights, venv, caches
  README.md
  SHA256SUMS_RELEASE.txt         10 entries
  package/W6_TRANSFER_PACKAGE.tar.gz
  integration/{offline_check.py, eligibility.py, test_eligibility.py}
  docs/{DEPLOYMENT_GUIDE.md, LAPTOP_POWERSHELL_COMMANDS.md, JETSON_OFFLINE_INSTALL.md}
  GIT_UPLOAD_STATUS.md
  RELEASE_EXECUTIVE_REPORT.md
```

The tarball is the audited distribution artefact; `integration/` holds the two scripts added in Stage07-P1 plus
their 5 tests.

## 3. Integrity chain

| link | evidence |
|---|---|
| frozen W6 → tarball | tarball sha256 unchanged: `58cd3fac…3c3b` |
| Stage07-P1 → release copy | all three integration scripts hash-identical to the P1 originals |
| release → manifest | `SHA256SUMS_RELEASE.txt` covers 10 files, all verified on disk |
| manifest → fresh clone | cloned to a temporary directory, re-verified: **10 ok, 0 failures** |

The clone round-trip is the link that matters for this distribution, because the laptop's first action after
`git clone` is a hash check.

## 4. The defect that was caught

The first clone reproduced only **8 of 10** hashes. Two text files (`.gitignore`, `README.md`) had been written
with CRLF line endings and a UTF-8 BOM, and git re-hydrated them differently on checkout.

Fixed by adding `.gitattributes` (`* -text`) and rewriting the affected files as UTF-8-without-BOM / LF-only,
then re-verifying via a fresh clone. **Had this gone unnoticed, every downstream verification would have
failed** on the laptop and the Jetson for a reason unrelated to software integrity — and the temptation would
have been to "fix" the manifest instead of the cause.

## 5. Documentation produced

| doc | contents |
|---|---|
| `docs/DEPLOYMENT_GUIDE.md` | the eight steps: push → clone → verify → scp → extract → python check → self-test → real-frame check; the exact CLI as implemented |
| `docs/LAPTOP_POWERSHELL_COMMANDS.md` | copy-paste PowerShell, including a hash-verification loop that aborts on any mismatch and an SSH identity check that never disables host-key checking |
| `docs/JETSON_OFFLINE_INSTALL.md` | receive → verify → path-safety check → extract → 20 tests → selfcheck → real-frame `offline_check.py`, with the expected `allowed: false` gate result |

Every command was derived from the actual source (`w6.cli` subcommands and their arguments, the
`offline_check.py` flags, the tarball's `w6_pkg/` root), not from memory.

## 6. Honest limits

* **No push happened.** Without a repository URL, attempting one would risk publishing to an unknown remote.
* **No laptop or Jetson action happened.** This stage is PC-only, as instructed.
* **Nothing about the D435 is verified.** The package reads saved frames; whether it can read the actual
  Stage07-P0 frame remains untested until the Jetson step runs.
* **No S40 number may be produced.** The eligibility gate enforces this; `REAL_S40_MEASUREMENT` stays
  `NOT_PERFORMED` and any precision figure stays `NOT_AVAILABLE`.
* The release is 11 files and 946 KB; it deliberately excludes the wider project, all data, and all weights.

## 7. The one thing needed to finish

A **private** GitHub repository URL. Then:

```bash
cd SCI_STAGE07_P2_W6_GIT_RELEASE
git remote add origin <PRIVATE_REPO_URL>
git push -u origin main
```

After that, the laptop follows `docs/LAPTOP_POWERSHELL_COMMANDS.md` and the Jetson follows
`docs/JETSON_OFFLINE_INSTALL.md`.

## 8. Final status

```text
RELEASE_PACKAGE            = READY
SHA256_VERIFIED            = YES
GITHUB_REPOSITORY          = NEED_USER_INPUT
GITHUB_PUSH                = NOT_ATTEMPTED
LAPTOP_DEPLOYMENT_COMMANDS = READY
JETSON_DEPLOYMENT          = NOT_PERFORMED
REAL_D435_INTEGRATION      = NOT_PERFORMED
```
