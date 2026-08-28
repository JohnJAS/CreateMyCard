---
name: sync-cloud-code
description: "Synchronize the current committed contents of a Git subdirectory one way into another repository, independent of shared history, with exclusions, content verification, and one traceable target commit per sync."
---

# Sync Cloud Code

Perform a **one-way, source-authoritative directory snapshot sync**. The desired content comes from a frozen source HEAD; determine changes by comparing current file content, not by replaying commits. No shared Git history, matching historical source baseline, or target/source commit correspondence is required. Create at most **one target commit per sync**, not one per source commit.

Do not run `git apply`, cherry-pick, search source history for a matching snapshot, or require a common ancestor to carry out this workflow. Source commit metadata is for traceability only and never decides which files to copy or whether a sync is necessary. The source/target direction is specified by the user, not inferred from which repository originally created the code.

## Defaults and scope

- Source repository: `D:\workspace\gittest\CreateMyCard`
- Source path: `widget_service/cloud`
- Target repository: `D:\workspace\gittest\GenUI`
- Target path: `genui-agent/cloud`
- Excluded: the source path's top-level `config/`, all `__pycache__/` directories, `*.pyc`, `*.pyo`, `*.pyd`, and `*.log`.

User-provided actual repository paths override these defaults. Verify both repositories are accessible and both subdirectories exist inside them. Do not treat a successful run on a test copy as validation of a different, inaccessible internal repository. Use repository-relative forward-slash paths in metadata. Nested config directories other than the top-level excluded one remain in scope.

## Safety checks and before-report

1. Read applicable repository instructions. Require both worktrees and indexes to be clean (`git status --short --branch`, including untracked files). Do not stash, reset, or mix user changes into the sync.
2. Freeze source HEAD and target HEAD as full SHAs. Verify target ignore rules cover `__pycache__/`, `*.py[cod]`, and `*.log`; ask before editing ignore files if rules are missing.
3. Run [scripts/verify_sync.py](scripts/verify_sync.py) in before mode with a new `--output` report outside both repositories. See [references/directory-audit.md](references/directory-audit.md) for flags. Supply the actual repository/path overrides consistently; do not audit the defaults and then write elsewhere.
4. Exit 1 before a sync means content differences to review, not an execution failure. Exit 2 requires investigation before proceeding. In particular, report ignored, non-excluded source-local files; never copy them as committed source content.
5. Report additions, same-path content replacements, and target-only files. Include the actual diff for changed text files when useful. A clean target may still have independent committed changes: source-authoritative copying will replace them, including deliberate target-side reverts. Clearly disclose this before writing; obtain confirmation for overwriting changed existing target files unless the user's request already explicitly authorizes that source-wins policy. Do not promise an automatic merge or preservation of independent edits within overwritten files.
6. If there is nothing to synchronize under the agreed line-ending policy, report no changes without copying or creating an empty commit. Otherwise obtain the current TicketNo before writing. Never invent a ticket or reuse an example or previous run's number without the user's instruction.

Never require or invent an initial source baseline. Missing, stale, rewritten, or unrelated history does not block content comparison; it only limits any historical summary reported later.

## Build the committed source snapshot

Create a unique temporary directory outside both repositories. Enumerate the frozen source snapshot with `git ls-tree -r -z <source-head> -- <source-path>`, filter the exclusions, and retain full relative paths. Materialize **only those committed regular files** from their Git blobs into the temporary directory, preserving bytes. Use `git cat-file` with binary subprocess I/O; do not route binary content through PowerShell text pipelines.

Do not recursively copy the live source worktree. A clean status alone does not exclude ignored files or freeze concurrent edits. Do not rely on `git archive` without accounting for export-ignore/export-subst behavior; the exported manifest must match the committed file list and each payload must match its blob. No automatic clean/smudge filters or LFS downloads are allowed. Stop for a specific handling decision if links, junctions, submodules, filters/LFS, or executable-mode differences prevent a faithful regular-file copy. Reject unsafe mapped paths and file-versus-directory collisions before writing.

Record and verify the materialized file manifest and SHA256 hashes against the frozen blobs. Recheck that source and target HEADs/statuses have not changed since the before-report. Keep repositories idle during the operation; stop if unexpected concurrent changes appear.

## Preview and copy

On Windows, use Robocopy on the **materialized snapshot**, not the source working directory:

```powershell
robocopy <snapshot-dir> <target-repo>\<target-path> /E /L /FP /IS /IT /IM /R:1 /W:1 /XD "<snapshot-dir>\config" __pycache__ /XF *.pyc *.pyo *.pyd *.log
```

Review the preview against the approved content-difference manifest. Then use the same command without `/L`:

```powershell
robocopy <snapshot-dir> <target-repo>\<target-path> /E /IS /IT /IM /R:1 /W:1 /XD "<snapshot-dir>\config" __pycache__ /XF *.pyc *.pyo *.pyd *.log
```

`/IS /IT /IM` includes same, tweaked, and change-time-modified files, avoiding those metadata-based skip categories; it can recopy unchanged files. Windows tests reproduced a same-size/same-mtime content mismatch that `/IS /IT` alone could still skip, so retain `/IM` as well. Hash verification, not Robocopy's copied-file count, establishes the result. Treat codes 0-7 as nonfatal transport results, not proof of equality; stop on code 8 or higher and do not commit. See [Robocopy documentation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy).

Use `/E`, never `/MIR`, `/PURGE`, `/MOVE`, or `/MOV`. **Preserve all target-only files, including source-deleted files left in the target.** Report these as possible stale files without guessing whether they should be removed. Renames can therefore leave an old target file plus the new name. Deletion or cleanup requires a separate explicit request.

On non-Windows systems, use an equivalent recursive regular-file copy from the validated snapshot, overwriting in-scope files regardless of timestamp where needed, without deleting target-only files. Preserve the same exclusions and validation.

## Validate before committing

Run the after audit with `--phase after --before-report <before.json> --output <new-after.json>` and the same paths and line-ending policy. Require exit 0; verify there are no missing/content-mismatched source files, no protected target config/target-only changes, no unexpected dirty paths, and no source HEAD change. Git LF/CRLF conversion must be treated explicitly: default to byte equality, and use `--ignore-crlf` only when repository policy permits that equivalence. Do not alter repository settings to make the check pass.

Also run `git diff --check` and review `git diff --stat` plus untracked additions. The audit checks file content, not executable modes or application behavior; inspect applicable Git modes and run focused syntax/tests in proportion to the changes. A successful copy or whitespace check alone is not enough.

Stage **only the approved in-scope changed/added file list**. Do not use broad `git add .` or stage excluded/target-only files. Inspect `git diff --cached --name-status`, `git diff --cached --check`, and staged file contents against source blobs (accounting for explicitly allowed Git line-ending conversion). If new copied files are ignored by other target rules, stop and ask how to handle those rules; do not force-add silently.

If there are no staged changes, do not create an empty commit. On copy, audit, staging, test, or commit failure, stop and report the exact remaining state. Do not auto-reset partially copied files, stash them, bypass hooks, or claim completion.

## Commit format and provenance

Create one target commit with exactly these three lines, preserving the complete Description on one physical line:

```text
[TicketNo:] <user-provided-ticket-number>
[Description:] sync: update <target-path> from <source-repo-name>@<short-source-head>; Source-Repo: <source-repo-name>; Source-Path: <source-path>; Source-Commit: <full-frozen-source-head>; Source-Base: <previous-reported-source-sha-or-unknown>; Source-Commits: <verified-count-or-unknown>; Excluded-Path: <source-path>/config; Sync-Mode: snapshot
[Binary Source:] No
```

`Source-Commit` identifies the source snapshot imported. `Source-Base` is optional historical context expressed as `unknown` when unavailable; it is not a copy prerequisite or proof that the target previously equaled that revision. If a prior matching sync record exists and its source SHA is a valid ancestor, a source-path-filtered history summary/count may be included for reference only. Otherwise use `unknown`; do not fabricate a commit range, pretend an initial snapshot represents one historical change, or block copying because metadata is unavailable. Even when Source-Commit equals a previous record, inspect actual content: target drift may still need a reviewed replacement.

Write the exact UTF-8 message to a temporary file outside both repositories and use `git commit --file <message-file>`. Verify the resulting three-line message. If the target validator rejects provenance fields in Description, ask how they may be recorded; never bypass validation. Do not amend old commits, rewrite existing history, or push unless separately requested.

## Final report

Verify both repositories' final status, the frozen source SHA, and the new target commit if any. Report changed files, excluded/preserved paths, target-only leftovers, content and test results, and the single target commit SHA. State that independent source commits were not recreated and historical counts may be unknown. A partial copy is not a completed sync.

Changing this skill only updates the workflow; it does not itself authorize a repository sync, an overwrite, or rewriting prior per-commit imports.
