# Read-only directory audit

`scripts/verify_sync.py` requires Python 3.10+ and Git, with no additional packages. It does not run Robocopy, copy files, execute Git filters, stage, commit, change Git settings, delete files, or access the network. It reads both repositories and may create a **new** report file outside them when `--output` is supplied. Existing report files are never overwritten.

The defaults are the CreateMyCard and GenUI paths in the skill. Override with `--source-repo`, `--source-path`, `--target-repo`, and `--target-path`.

## Usage

Read-only audit, concise output:

```powershell
python -B -X utf8 C:\Users\shengjiajun\.codex\skills\sync-cloud-code\scripts\verify_sync.py
```

Capture a before-report outside the repositories (choose a new filename for each run):

```powershell
python -B -X utf8 C:\Users\shengjiajun\.codex\skills\sync-cloud-code\scripts\verify_sync.py --output D:\workspace\gittest\cloud-before.json
```

After a separately authorized sync, compare the same frozen source HEAD and verify preservation of target config and prior target-only files:

```powershell
python -B -X utf8 C:\Users\shengjiajun\.codex\skills\sync-cloud-code\scripts\verify_sync.py --phase after --before-report D:\workspace\gittest\cloud-before.json --output D:\workspace\gittest\cloud-after.json
```

`--phase after` permits expected uncommitted target changes; changes outside the scope or in excluded tracked files are still flagged. It is not permission to commit or overwrite anything. `--json` prints the full report rather than the summary.

## Results

- Exit `0`: all included source files match the target under the selected line-ending policy. Extra target files may still exist and are listed; this is not a claim of an exact mirror or successful business tests.
- Exit `1`: missing or different target content. Before a sync this normally describes pending changes; after a sync it requires investigation.
- Exit `2`: review required or audit error, for example dirty source, dirty target in before mode, ignored local source files, missing ignore rules, changed protected files, unsafe paths, or concurrent repository changes. Do not use this result as a clean-copy approval.

By default it compares raw committed blob bytes with SHA256 and never trusts timestamps. UTF-8 text differing only in CRLF/LF is separately identified but still counts as different. If project policy explicitly treats these endings as equivalent, add `--ignore-crlf`; it changes comparison policy only, never file contents. Git checkout filters and LFS are not executed, so filtered files require a separate policy.

The source working tree is also checked against committed content. Ignored, non-excluded local files are reported because Robocopy could copy them even when `git status` is clean. Top-level config, all cache directories, and `.pyc/.pyo/.pyd/.log` are excluded from the copied-content comparison. Nested config directories outside the top level remain in scope.

The before-report stores hashes of target top-level config and target-only files, without file contents. Pairing it with the after check can detect accidental changes or deletions, including changes already committed after the before capture. Logs and caches are excluded, not proven unchanged. Without a before-report, unchanged protected files cannot be established from a single snapshot.

## Boundaries

- Target-only files cannot be classified as intentionally local versus stale source deletions without a known baseline; they are never automatically deleted.
- File equality does not establish which historical commits were originally imported. The script does not infer a sync baseline or claim one-to-one commit attribution.
- It checks regular file bytes, not executable bits, permissions, timestamps, application behavior, or a fully atomic snapshot. Symlinks, junctions in inspected scope, and submodules are rejected for review, not followed.
- Keep repositories idle while checking. HEAD/status and file metadata are sampled to catch common races, but this is not a filesystem lock or proof against concurrent modification.

## Tests

```powershell
python -B -X utf8 C:\Users\shengjiajun\.codex\skills\sync-cloud-code\scripts\test_verify_sync.py -v
```

Tests create isolated temporary Git repositories. They cover same-size/same-time differences (including an actual Windows Robocopy reproduction), exclusions, ignored files, dirty source content, LF/CRLF policy, protected files, scope escapes, links/junctions, binary and Unicode files, and absence of writes to repository data and Git metadata.
