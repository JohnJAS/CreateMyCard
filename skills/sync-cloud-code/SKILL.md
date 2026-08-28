---
name: sync-cloud-code
description: "Use when code must be synchronized from a subdirectory in one Git repository into a corresponding subdirectory in another repository, especially when multiple source commits, mixed-path commits, excluded directories, and traceable sync commits matter."
---

# Sync Cloud Code

Synchronize the final committed file state from a source Git subdirectory into a target Git subdirectory, while recording which source revision was imported. This is a content sync workflow, not a `cherry-pick` or history merge.

## Defaults

Use these defaults when the user does not provide paths:

- Source repository: `D:\workspace\gittest\CreateMyCard`
- Source path: `widget_service\cloud`
- Target repository: `D:\workspace\gittest\GenUI`
- Target path: `genui-agent\cloud`
- Excluded source subdirectory: `widget_service\cloud\config` (the target `cloud\config` is preserved)

Paths supplied by the user override the defaults. Resolve all paths to repository-relative paths before running Git commands. Stop if either path is missing or is not inside the stated repository.

## Safety gates

1. Inspect both repositories with `git status --short --branch` and verify the source worktree and target worktree are clean. Do not overwrite or mix with uncommitted user changes; stop and report the files that need attention.
2. Verify the target has an ignore rule for `__pycache__/`, `*.py[cod]`, and `*.log`. If it does not, stop and ask whether to add one; do not silently edit ignore files.
3. Read the source `HEAD` full SHA and the target log. Read full commit messages (`git log --format=%B`) and find the most recent target commit containing `Source-Commit: <sha>` with matching `Source-Repo` and `Source-Path`. Accept both the semicolon-separated metadata in the new `[Description:]` field and standalone trailers in older sync commits. Parse complete metadata values, not substring matches. That SHA is the sync base. If no matching record exists, treat this as an initial sync and use an empty base.
4. If a recorded base exists but is not an ancestor of source `HEAD`, stop: the source history was rewritten or the target metadata is stale. Do not guess a range.

## Determine the source change set

The copied result is the source directory's final state at `HEAD`, so all commits since the recorded base are handled together. A source commit may also modify files outside the source path; ignore those unrelated changes. A commit that touches both the excluded `config` directory and other source files is relevant, but copy only the non-excluded files.

For reporting, list commits with:

```powershell
git -C <source-repo> log --format="%H %s" <base>..HEAD -- <source-path>
```

On an initial sync, list the current source `HEAD` instead. Do not claim that unrelated files were synchronized.

## Commit format and ticket

Use the target repository's required three-line commit format shown below. Before copying, obtain the actual ticket number from the user's current sync request or ask for it. Never invent a ticket, copy one from an old commit, or use the example `DTS2608260066700` unless the user explicitly selects it. A format example is not a ticket assignment.

Keep exactly these three field labels, in this order: `[TicketNo:]`, `[Description:]`, `[Binary Source:]`. Set `[Binary Source:]` to `No` for this code sync. Use the previous `sync: update <target-path> from <source-repo-name>@<short-head>` summary followed by all source metadata on the same `[Description:]` line, separated by semicolons. Do not insert any newline within this field; the complete commit message has exactly three lines. If a repository validator rejects this description structure, stop and ask how to retain the sync metadata; do not bypass hooks or silently discard the baseline.

## Preview and copy

On Windows, preview first and then copy only after the user authorizes the write (or has explicitly asked the skill to perform the sync):

```powershell
robocopy <source-repo>\<source-path> <target-repo>\<target-path> /E /L /FP `
  /XD "<source-repo>\\<source-path>\\config" __pycache__ `
  /XF *.pyc *.log
```

Review the preview. Use `/E`, not `/MIR`: the default workflow never deletes target-only files. Then execute the same command without `/L`:

```powershell
robocopy <source-repo>\<source-path> <target-repo>\<target-path> /E `
  /XD "<source-repo>\\<source-path>\\config" __pycache__ `
  /XF *.pyc *.log
```

Treat Robocopy exit codes 0 through 7 as non-fatal copy results; stop on 8 or higher and do not commit.

On non-Windows systems, use an equivalent recursive copy that excludes the relative `config` directory, Python cache/bytecode files, and log files. Preserve the same no-delete behavior.

## Validate and commit

After copying:

```powershell
git -C <target-repo> status --short
git -C <target-repo> diff --check
git -C <target-repo> diff --stat -- <target-path>
```

If there are no changes under the target path, do not create an empty commit. Otherwise, stage only the target path and use this commit message:

```text
[TicketNo:] <user-provided-ticket-number>
[Description:] sync: update <target-path> from <source-repo-name>@<short-head>; Source-Repo: <source-repo-name>; Source-Path: <source-path>; Source-Commit: <full-head-sha>; Source-Base: <full-base-sha-or-initial>; Source-Commits: <number-of-source-commits>; Excluded-Path: <source-path>/config
[Binary Source:] No
```

Use repository-relative forward-slash paths in metadata. On an initial sync, `Source-Commits: 1` records the single HEAD snapshot listed for reporting, not the total historical commits contributing to its content. Write the exact message as UTF-8 to a temporary file outside the repository and pass it to `git commit --file <message-file>` to preserve the three real lines and literal values. Verify the resulting full commit message matches this format. Do not amend existing commits solely because this skill's format has changed; rewriting a previous commit requires an explicit user request.

Do not stage unrelated target changes. Do not reset, force-push, delete target files, or push remotes unless the user separately requests it.

## Final verification and report

Verify `git status --short --branch` is clean, confirm the new target commit, and report:

- source commit range and the number of source commits touching the source path;
- target files changed;
- that `config`, caches, bytecode, and logs were excluded;
- whether target-only files were preserved;
- the target commit SHA.

If the source has uncommitted changes, the target is dirty, the ignore rule is missing, or the copy fails, stop without committing and explain the exact gate that failed.
