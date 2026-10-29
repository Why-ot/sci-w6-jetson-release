# GIT UPLOAD STATUS

**Task:** `SCI_STAGE07_P2_W6_GIT_DISTRIBUTION`
**Date:** 2026-10-29 (Asia/Shanghai)

```text
GITHUB_REPOSITORY = NEED_USER_INPUT
GITHUB_PUSH       = NOT_ATTEMPTED
```

---

## 1. Environment check (actual output)

| item | value |
|---|---|
| `git --version` | **2.55.0.windows.2** |
| repository at `F:\GraspResearch` | **none** (no `.git` at the project root) |
| nested third-party repos | `third_party/graspness_unofficial/.git`, `third_party/graspnetAPI/.git` — **untouched** |
| global `user.name` / `user.email` | **unset** |
| `~/.git-credentials` | **absent** |
| global `credential.helper` | **unset** |
| network access to GitHub | not tested — no repository URL was supplied, so no attempt was made |

## 2. Local repository created

| item | value |
|---|---|
| path | `SCI_RESTART_20261008/SCI_STAGE07_P2_W6_GIT_RELEASE/` |
| branch | `main` |
| commit | **`1cda803`** — "W6 S40 measurement package: audited release" |
| tracked files | **11** |
| remotes | **none** |
| identity | repo-local only: `SCI W6 Release Bot <w6-release@localhost>` — global config untouched |

The identity is deliberately non-personal and scoped to this repository: no global git configuration was
modified, and no credential of any kind is stored.

## 3. What is tracked

```text
.gitattributes                         ( * -text : disables line-ending conversion )
.gitignore                             ( strict: keys, data, weights, venv, caches )
README.md
SHA256SUMS_RELEASE.txt                 ( 10 entries, all verified )
docs/DEPLOYMENT_GUIDE.md
docs/JETSON_OFFLINE_INSTALL.md
docs/LAPTOP_POWERSHELL_COMMANDS.md
integration/eligibility.py
integration/offline_check.py
integration/test_eligibility.py
package/W6_TRANSFER_PACKAGE.tar.gz     ( 15,719 B )
```

## 4. What is explicitly excluded (and why)

| excluded | mechanism | reason |
|---|---|---|
| SSH keys (`id_rsa*`, `id_ed25519*`, `*.pem`, `*.ppk`) | `.gitignore` | credentials |
| `known_hosts`, `.netrc`, `.git-credentials`, `*.token`, `.env*` | `.gitignore` | credentials |
| raw sensor data (`*.raw`, `*.bag`, `*.db3`, `capture*/`, `S40_SESSION_*/`) | `.gitignore` | real captures belong in Stage07-P0 |
| model weights (`*.pt`, `*.ckpt`, `*.onnx`, `checkpoints/`) | `.gitignore` | size; not needed |
| datasets | `.gitignore` | size |
| the rest of `GraspResearch` | never staged — this is a separate repository | the task forbids uploading the whole project |
| `__pycache__`, `.venv`, editor folders | `.gitignore` | noise |

`package/W6_TRANSFER_PACKAGE.tar.gz` is a `.tar.gz`, which `*.tar` does not match; it is additionally
whitelisted with a `!` rule, and `git check-ignore` confirmed it is **not** ignored.

## 5. The line-ending problem that was found and fixed

The first attempt produced a clone in which **2 of 10 files had different SHA256 values** (`.gitignore`,
`README.md`). Cause: those files had been written with CRLF and a UTF-8 BOM, and git normalised/hydrated them
differently on checkout.

Fix, applied and verified:

1. added `.gitattributes` containing `* -text` (no conversion of any file);
2. rewrote the three text config files as **UTF-8 without BOM, LF only**;
3. re-committed and performed a **fresh `git clone` into a temporary directory**, then re-verified every
   hash from the clone.

Result after the fix:

```text
post-clone: 10 ok, 0 failures
```

This matters because the entire deployment chain is hash-verified: a silent CRLF conversion would have made
the laptop's step-3 check fail for reasons unrelated to integrity.

## 6. What is required from the user to finish the upload

```text
1. create a PRIVATE repository on GitHub (suggested name: w6-s40-measurement)
2. provide its URL, e.g.  https://github.com/<account>/<repo>.git
3. ensure the machine has push credentials (PAT via credential manager, or an SSH key already registered)
```

Then, on this PC:

```bash
cd /mnt/f/GraspResearch/SCI_RESTART_20261008/SCI_STAGE07_P2_W6_GIT_RELEASE
git remote add origin https://github.com/<account>/<repo>.git
git push -u origin main
```

**No push will be attempted to any repository that the user has not named.** No other git repository on this
machine is touched.

## 7. Verification a reviewer can repeat

```bash
cd SCI_STAGE07_P2_W6_GIT_RELEASE
git log --oneline -1
git ls-files | wc -l          # 11
sha256sum -c SHA256SUMS_RELEASE.txt   # 10 OK  (Linux)
```

```powershell
# Windows: see docs/LAPTOP_POWERSHELL_COMMANDS.md §2
```
