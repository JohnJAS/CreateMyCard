# Find a candidate first-sync baseline by content

Use this procedure only when no valid source metadata exists in target history and the user has not already supplied the initial baseline. Existing valid metadata takes precedence; do not use snapshot matching to override it or undo a target-side revert.

## Compare the committed cloud snapshots

1. Require clean repositories and freeze both HEAD SHAs. List a bounded recent batch of ancestors of the frozen source HEAD, in ancestry order, without a path filter. For example:

   ```powershell
   git -C <source-repo> rev-list --topo-order --max-count=50 <frozen-source-head>
   ```

2. List the target snapshot once, and each candidate source snapshot as needed:

   ```powershell
   git -C <target-repo> ls-tree -r -z <frozen-target-head> -- <target-path>
   git -C <source-repo> ls-tree -r -z <candidate-source-sha> -- <source-path>
   ```

3. Parse NUL-separated records as `mode type object-id TAB path`. Remove each side's own cloud directory prefix, then apply the skill's same exclusions. Compare dictionaries keyed by the **full relative path**, not just the basename. For example, both corresponding routes files map to `api/routes.py`.

4. For regular files, require equal path sets and equal mode, object type, and blob ID for every path. Blob IDs identify content independently of the repository or file location, so unrelated repository directories do not participate. Check `git rev-parse --show-object-format` in both repositories first; if object formats differ, compare raw blob bytes or a shared SHA256 digest instead of comparing unlike object IDs. Reject unsupported submodules or links for review rather than treating their IDs as ordinary file content.

5. Do not ignore unmatched target-only files just to produce a match, and do not treat two empty filtered snapshots as an informative baseline. A partial match is not sufficient. This is committed-state comparison; file modification times and working-copy LF/CRLF conversion do not determine equality.

## Interpret and confirm the result

- Report the candidate SHA, number of included files, exclusions, and examined history range. If several snapshots match because intervening commits changed only other directories or later restored the same content, say so. A matching snapshot does not identify the original copying event.
- When matches are on one ancestry chain, propose the latest matching ancestor as the content checkpoint, and preview the relevant commits after it. Do not rank candidates by author/committer timestamps. If matching candidates lie on different branches without one being the other's ancestor, ask which line of history to use instead of calling one the latest.
- Ask the user to confirm the proposed checkpoint before writing. If no exact match exists in the examined batch, say that the search was bounded; extend the read-only search when useful or ask for a baseline. Do not claim the entire history was searched unless it was.
- Recheck that both HEADs and clean states remain unchanged after confirmation. Then use the normal ancestry, merge, path-filtering, patch-check, and ticket gates. This procedure does not authorize replaying merge histories automatically.

Do not hardcode a previously observed SHA, file count, or ticket number. The result must come from the current repositories. Once an import succeeds, its source metadata supplies the checkpoint for subsequent runs.

The separate `scripts/verify_sync.py` audit compares current source HEAD with working files; it does **not** search historical snapshots. Use the Git procedure above for first-sync baseline candidates.
