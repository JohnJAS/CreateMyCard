---
name: sync-cloud-code
description: "Synchronize committed changes one way between Git subdirectories, creating a separate target commit for each relevant source commit while excluding configuration and generated files and recording the source revision."
---

# Sync Cloud Code

Synchronize **one way, one source commit at a time**. Replay each relevant source commit's scoped patch as a separate target commit, in ancestry order. Do not squash a range, copy the final HEAD directory over intermediate revisions, or cherry-pick an entire mixed-path commit. Source history is never modified; target SHAs differ because paths and messages are rewritten.

## Defaults

- Source repository: `D:\workspace\gittest\CreateMyCard`
- Source path: `widget_service/cloud`
- Target repository: `D:\workspace\gittest\GenUI`
- Target path: `genui-agent/cloud`
- Excluded: the source path's top-level `config/`, all `__pycache__/` directories, `*.pyc`, `*.pyo`, `*.pyd`, and `*.log`.

User-provided paths override these defaults. Resolve repositories and subdirectories, require both paths to exist inside their stated repositories, and use repository-relative forward-slash paths for Git commands and metadata. The target top-level `cloud/config/` is preserved; other nested directories named `config` remain in scope.

## Safety gates and baseline

1. Read applicable repository instructions. Run `git status --short --branch` in both repositories and require clean worktrees and indexes, including no untracked user files. Stop and report dirty paths; do not stash or overwrite user changes.
2. Verify target ignore rules cover `__pycache__/`, `*.py[cod]`, and `*.log`. If missing, ask before changing ignore files. Freeze source HEAD as a full SHA for this run; read patches from Git objects, not working files.
3. Read full messages of commits reachable from target HEAD, newest first. Find the most recent actual sync commit whose `Source-Repo` and `Source-Path` exactly match. Accept both the current three-line message with semicolon-separated metadata in `[Description:]` and the legacy `sync: update ...` title with standalone trailers. Do not mistake a revert message quoting metadata for an import. Its `Source-Commit` is the baseline, including when the record came from the old snapshot workflow.
4. Verify that the baseline exists in the source and is an ancestor of the frozen HEAD. If missing or not an ancestor, stop; never guess or silently reset the baseline. Target-side reverts do not rewind the baseline or automatically trigger reimport of old commits. No reverse synchronization or reconciliation is performed.
5. If no record exists and the user has not supplied a baseline, first perform the read-only [scoped Git snapshot comparison](references/baseline-comparison.md): compare target HEAD's included file paths, blob IDs, and modes with recent source ancestor snapshots, ignoring only the configured exclusions. Present any matching source revision as a **candidate content baseline**, not proof of import history, and obtain user confirmation before replay. Report multiple matches honestly. If no exact match is found in the examined range, ask for the last source revision already represented in the target; do not infer a baseline from partial similarity. Alternatively, the user can explicitly request replay from the root of source history. Never silently invent a baseline or collapse initial history into a snapshot. Full-history replay may conflict with preexisting target files; use the same conflict gate below.
6. Obtain the actual ticket number from this sync request, or ask before changing files. A ticket applies to all target commits in this run unless the user provides a per-commit mapping. Never invent it, reuse an old ticket, or treat the example `DTS2608260066700` as an assigned ticket.

Changing this skill does not authorize running a new sync or rewriting existing target commits.

## Plan the source sequence

Enumerate commits without a path filter first, so merge topology cannot be hidden by history simplification:

```powershell
git -C <source-repo> rev-list --reverse --topo-order <base>..<frozen-head>
git -C <source-repo> rev-list --merges <base>..<frozen-head>
```

For explicitly authorized full-history replay, replace the range with `<frozen-head>`. If the range contains merges, stop before applying any changes and ask for a merge policy; do not replay both branch commits and the merged aggregate, pick a parent silently, or promise to preserve a nonlinear graph as a linear sequence.

For each non-merge commit, compute its patch against its sole parent. For a root commit in full-history replay, use the empty tree as its parent (obtain it with `git hash-object -t tree --stdin` with zero input bytes). Filter the patch to the source path and exclusions before deciding relevance. Changes outside scope, including mixed-path portions of the same commit, are never imported. Empty filtered patches are reported as skipped, without target commits.

Preview source SHA, subject, and mapped added/modified/deleted paths for every relevant commit. Apply in ancestry order, not author timestamp order. An invocation to perform the sync authorizes the previewed scoped changes; otherwise obtain write authorization. Record the initial target HEAD for the final report.

## Generate and apply one scoped patch

Use a unique temporary patch file outside both repositories. Generate it with Git's `--output` option or capture subprocess stdout as bytes; do not pipe binary patches through PowerShell text formatting or rewrite patch headers with string replacement.

For the default source path (substitute all pathspecs consistently when overridden):

```powershell
git -C <source-repo> diff --binary --full-index --no-renames --no-ext-diff --no-textconv --src-prefix=a/ --dst-prefix=b/ --relative=widget_service/cloud --output=<patch-file> <parent> <source-commit> -- widget_service/cloud ':(exclude)widget_service/cloud/config' ':(glob,exclude)widget_service/cloud/**/__pycache__/**' ':(glob,exclude)widget_service/cloud/**/*.pyc' ':(glob,exclude)widget_service/cloud/**/*.pyo' ':(glob,exclude)widget_service/cloud/**/*.pyd' ':(glob,exclude)widget_service/cloud/**/*.log'
```

`--no-renames` represents moves as deletion/addition, including moves across the excluded boundary. Source-tracked deletions inside scope are synchronized, unlike the old copy-only workflow. Never sweep or mirror the directory: target-only files absent from the patch are preserved. Inspect the mapped patch paths and require every path to stay within the target scope and outside exclusions; stop on unsafe paths or unsupported submodule changes.

Before each application, recheck that the target is clean and at the expected last target commit. Then run from the target repository root:

```powershell
git -C <target-repo> apply --check --index -p1 --directory=<target-path> <patch-file>
git -C <target-repo> apply --index -p1 --directory=<target-path> <patch-file>
```

Run the second command only after the first succeeds. `--relative` makes patch paths relative to the source subdirectory; `-p1` strips `a/` and `b/`, and `--directory` maps them into the target subdirectory. `--index` stages only the patch changes. See [Git diff](https://git-scm.com/docs/git-diff) and [Git apply](https://git-scm.com/docs/git-apply) for option semantics.

If the check fails, skip as already present only after verifying every affected target file matches the source commit's full postimage and mode, including absence for deleted paths. A reverse-apply check alone is not enough. If only part is present or there is any divergence, stop and report the source SHA and conflicting paths. Do not partially apply, use `--reject`, force source files over conflicts, auto-merge, or skip failed commits and continue.

## Validate and commit each patch separately

After each successful application:

```powershell
git -C <target-repo> status --short
git -C <target-repo> diff --cached --check
git -C <target-repo> diff --cached --stat
git -C <target-repo> diff --cached --name-status
```

Verify the staged patch is restricted to the expected mapped changes; do not run a broad `git add`. Check excluded paths and target-only files are unchanged. Run applicable focused checks in proportion to risk before committing. If validation fails, stop without committing this patch; leave its state visible for investigation and report earlier successful commits. Do not reset, delete, or stash those changes automatically.

If no staged changes remain, do not create an empty commit. Otherwise create exactly one commit for this source commit, using exactly three lines:

```text
[TicketNo:] <user-provided-ticket-number>
[Description:] sync: update <target-path> from <source-repo-name>@<short-source-commit>; Source-Repo: <source-repo-name>; Source-Path: <source-path>; Source-Commit: <full-source-commit-sha>; Source-Base: <previous-checkpoint-sha-or-initial>; Source-Commits: 1; Excluded-Path: <source-path>/config
[Binary Source:] No
```

Keep the entire Description on **one physical line**, with semicolon-separated metadata. `Source-Commit` is this individual source commit, never the final run HEAD unless that is the commit being applied. `Source-Base` is the last recorded imported source SHA (or user-selected initial baseline, or `initial` for root replay). Advance the checkpoint only after the target commit succeeds. Skipped commits do not create checkpoint-only or empty commits; trailing skips may be examined again on the next run and must be reported honestly.

Write the exact message as UTF-8 to a temporary file outside the repositories and use `git commit --file <message-file>`. Verify the resulting three-line message, record the source-to-target SHA mapping, and require a clean target before advancing to the next source commit. Stop on hook/commit failure, retain the staged patch, and never bypass hooks. If a validator rejects Description metadata, ask how it may be retained instead of dropping the baseline.

Do not amend existing commits, reset history, push, or force-push unless separately requested. A stopped run retains earlier successful commits; a later invocation resumes after their recorded source checkpoint once any outstanding dirty state is resolved.

## Final verification and report

Verify both repository statuses, target commit messages, and the ordered source-to-target mapping. For replay into a matching baseline, verify the resulting imported files against the source objects. Do not use a final bulk copy to hide differences; target-only files, exclusions, and target-side reverts may intentionally differ. Report any unexpected divergence.

Report the source range, count of relevant commits, count actually imported, skipped commits with reasons, target SHAs and changed paths, checks performed, preserved exclusions and target-only files, and any source deletions applied. If interrupted, identify the failed source commit, last successful checkpoint, and any staged/uncommitted changes. Never report a partially completed range as fully synchronized.

## Optional read-only directory audit

Use [scripts/verify_sync.py](scripts/verify_sync.py) to audit a proposed or completed directory copy against source HEAD, including SHA256 differences, ignored local source files, missing ignore rules, unsafe links, and target-only files. A saved before-report can check that target config and target-only files remain unchanged. Read [references/directory-audit.md](references/directory-audit.md) for usage and limitations. This diagnostic does not copy files, determine historical provenance, or change the per-commit sync strategy above. Whole-directory differences can be intentional after target-side reverts; do not overwrite them simply to make this diagnostic pass.
