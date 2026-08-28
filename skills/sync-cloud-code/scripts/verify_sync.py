#!/usr/bin/env python3
"""Read-only audit of cloud directory copies. Python 3.10+, Git, no packages.

Exit 0: scoped source content matches under the selected EOL policy (extras may be reported).
Exit 1: missing/different target bytes. Exit 2: unsafe state or audit error.
No copy, staging, commits, checkout, cleanup, external filters, or network calls.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys


def git(repo, *args, data=None, allowed=(0,)):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, capture_output=True, env=env
    )
    if result.returncode not in allowed:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def text(repo, *args):
    return git(repo, *args).decode("utf-8", "surrogateescape").strip()


def excluded(name):
    parts = PurePosixPath(name).parts
    return bool(parts) and (
        parts[0] == "config" or "__pycache__" in parts
        or name.lower().endswith((".pyc", ".pyo", ".pyd", ".log"))
    )


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def scope(repo_arg, relative):
    repo = Path(repo_arg).resolve(strict=True)
    if Path(text(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise ValueError(f"Not a repository root: {repo}")
    relative = relative.replace("\\", "/").rstrip("/")
    parts = PurePosixPath(relative).parts
    if (not parts or PurePosixPath(relative).is_absolute()
            or any(p in ("..", ".git") or ":" in p for p in parts)):
        raise ValueError(f"Unsafe relative directory: {relative}")
    cursor = repo
    for part in parts:
        cursor /= part
        if is_link(cursor):
            raise ValueError(f"Scope traverses a link/junction: {cursor}")
    if not cursor.is_dir() or not cursor.resolve().is_relative_to(repo):
        raise ValueError(f"Missing or escaped scope: {cursor}")
    return repo, relative, cursor


def digest(data):
    result = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    try:
        if b"\0" not in data:
            data.decode("utf-8")
            result["lf_sha256"] = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    except UnicodeDecodeError:
        pass
    return result


def committed_files(repo, sha, prefix):
    entries, skipped = {}, []
    for record in git(repo, "ls-tree", "-r", "-z", sha, "--", prefix).split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        name = path.decode("utf-8", "surrogateescape")[len(prefix) + 1:]
        if excluded(name):
            skipped.append(name)
            continue
        mode, kind, oid = meta.decode().split()
        if mode not in ("100644", "100755") or kind != "blob":
            raise ValueError(f"Unsupported Git entry (link/submodule): {prefix}/{name}")
        if any(p in ("..", ".git") for p in PurePosixPath(name).parts):
            raise ValueError(f"Unsafe Git path: {name}")
        entries[name] = oid
    # Cat-file returns raw committed blobs, without checkout/LFS/clean filters.
    oids = sorted(set(entries.values()))
    output = git(repo, "cat-file", "--batch", data="".join(x + "\n" for x in oids).encode()) if oids else b""
    digests, offset = {}, 0
    for oid in oids:
        end = output.index(b"\n", offset)
        header = output[offset:end].decode().split()
        if len(header) != 3 or header[:2] != [oid, "blob"]:
            raise ValueError("Unexpected cat-file response")
        size = int(header[2])
        start = end + 1
        digests[oid] = digest(output[start:start + size])
        offset = start + size + 1
    return {name: digests[oid] for name, oid in entries.items()}, skipped


def disk_files(root, include_config=False):
    files, unsafe = {}, []

    def walk_error(error):
        raise error

    for parent, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        for name in list(dirs):
            path = Path(parent) / name
            rel = path.relative_to(root).as_posix()
            skip = excluded(rel) and not (include_config and rel.split("/")[0] == "config")
            if skip:
                dirs.remove(name)
            elif name == ".git" or is_link(path):
                unsafe.append(rel)
                dirs.remove(name)
        for name in names:
            path = Path(parent) / name
            rel = path.relative_to(root).as_posix()
            if excluded(rel) and not (include_config and rel.split("/")[0] == "config"):
                continue
            if name == ".git" or is_link(path) or not stat.S_ISREG(path.lstat().st_mode):
                unsafe.append(rel)
                continue
            before = path.stat()
            files[rel] = digest(path.read_bytes())
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                unsafe.append(rel + " (changed while reading)")
    return files, unsafe


def differences(expected, actual):
    changed = []
    for name in sorted(expected.keys() & actual.keys()):
        a, b = expected[name], actual[name]
        if a["sha256"] != b["sha256"]:
            ending_only = a.get("lf_sha256") is not None and a.get("lf_sha256") == b.get("lf_sha256")
            changed.append({"path": name, "line_endings_only": ending_only})
    return sorted(expected.keys() - actual.keys()), changed


def inspect(args):
    src, sp, source_dir = scope(args.source_repo, args.source_path)
    dst, tp, target_dir = scope(args.target_repo, args.target_path)
    if src == dst or src.is_relative_to(dst) or dst.is_relative_to(src):
        raise ValueError("Source and target must be separate, non-nested repositories")
    source_head = text(src, "rev-parse", "HEAD")
    target_head = text(dst, "rev-parse", "HEAD")
    source_status = git(src, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    target_status = git(dst, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    expected, skipped = committed_files(src, source_head, sp)
    source_disk, source_unsafe = disk_files(source_dir)
    target_all, target_unsafe = disk_files(target_dir, include_config=True)
    target_disk = {p: d for p, d in target_all.items() if not excluded(p)}
    missing, changed = differences(expected, target_disk)
    source_missing, source_changed = differences(expected, source_disk)
    source_local_only = sorted(source_disk.keys() - expected.keys())
    target_only = sorted(target_disk.keys() - expected.keys())
    probes = [tp + "/" + p for p in ("__pycache__/__sync_probe__", "__sync_probe__.pyc", "__sync_probe__.pyo", "__sync_probe__.pyd", "__sync_probe__.log")]
    ignored = set(git(dst, "check-ignore", "--no-index", "-z", "--stdin", data=("\0".join(probes) + "\0").encode(), allowed=(0, 1)).decode().split("\0"))
    missing_ignores = [p for p in probes if p not in ignored]
    dirty_names = (git(dst, "diff", "--name-only", "--no-renames", "--no-ext-diff", "--no-textconv", "-z", "HEAD", "--")
                   + git(dst, "ls-files", "--others", "--exclude-standard", "-z"))
    out_of_scope = []
    for item in dirty_names.split(b"\0"):
        if not item:
            continue
        name = item.decode("utf-8", "surrogateescape")
        if not name.startswith(tp + "/") or excluded(name[len(tp) + 1:]):
            out_of_scope.append(name)
    protected = {p: d["sha256"] for p, d in target_all.items() if p.startswith("config/") or p in target_only}
    report = {
        "schema": 1, "source_repo": str(src), "target_repo": str(dst),
        "ignore_crlf": args.ignore_crlf,
        "source_path": sp, "target_path": tp, "source_commit": source_head, "target_commit": target_head,
        "source_clean": not source_status, "target_clean": not target_status,
        "source_tracked_files": len(expected), "excluded_source_tracked_files": len(skipped),
        "missing_target_files": missing, "different_target_files": changed,
        "target_only_files": target_only, "source_local_only_files": source_local_only,
        "source_worktree_missing": source_missing, "source_worktree_different": source_changed,
        "unsafe_paths": {"source": source_unsafe, "target": target_unsafe},
        "missing_ignore_rules": missing_ignores,
        "target_dirty_paths_outside_sync_scope": sorted(set(out_of_scope)),
        "protected_target_sha256": protected, "protected_target_changes": [],
        "notes": [
            "Raw committed bytes are compared with SHA256; CRLF-only differences count unless --ignore-crlf is explicit.",
            "Target-only files are reported, never deleted; without a baseline they cannot be classified as obsolete or intentional.",
            "A before-report checks preservation of config and prior target-only files. Logs/caches are excluded, not verified.",
            "This audit does not prove historical commit provenance, permissions/executable modes, business correctness, or atomicity against concurrent edits.",
            "Git filters/LFS are not executed. Filtered checkout content may differ from committed blob bytes."
        ],
    }
    if args.before_report:
        prior = json.loads(Path(args.before_report).read_text(encoding="utf-8"))
        for field in ("schema", "source_repo", "target_repo", "source_path", "target_path", "source_commit"):
            if prior.get(field) != report[field]:
                raise ValueError(f"Before-report belongs to a different run/scope: {field}")
        old = prior["protected_target_sha256"]
        current = {p: d["sha256"] for p, d in target_all.items() if p in old or p.startswith("config/")}
        report["protected_target_changes"] = sorted(p for p in old.keys() | current.keys() if old.get(p) != current.get(p))
    unstable = source_head != text(src, "rev-parse", "HEAD") or target_head != text(dst, "rev-parse", "HEAD")
    unstable |= source_status != git(src, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    unstable |= target_status != git(dst, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    report["repository_changed_during_audit"] = unstable
    unsafe = (source_status or (target_status and args.phase == "before") or source_local_only
              or source_missing or any(not x["line_endings_only"] for x in source_changed)
              or source_unsafe or target_unsafe or missing_ignores or unstable
              or (args.phase == "after" and out_of_scope)
              or report["protected_target_changes"])
    effective_changes = [x for x in changed if not (args.ignore_crlf and x["line_endings_only"])]
    report["exit_code"] = 2 if unsafe else (1 if missing or effective_changes else 0)
    report["result"] = ["SCOPED_CONTENT_MATCH", "CONTENT_DIFFERENCES", "REVIEW_REQUIRED"][report["exit_code"]]
    return report


def summary(report):
    changed = report["different_target_files"]
    content_changes = [x["path"] for x in changed if not x["line_endings_only"]]
    ending_changes = sum(x["line_endings_only"] for x in changed)
    lines = [f"{report['result']} (exit {report['exit_code']})",
             f"Source: {report['source_commit']}; target: {report['target_commit']}",
             f"Source files: {report['source_tracked_files']}; missing: {len(report['missing_target_files'])}; content differences: {len(content_changes)}; CRLF-only: {ending_changes}",
             f"Target-only: {len(report['target_only_files'])}; uncommitted source-only: {len(report['source_local_only_files'])}",
             f"Clean source: {report['source_clean']}; clean target: {report['target_clean']}"]
    for label, paths in [("different", content_changes), ("missing", report["missing_target_files"]),
                         ("target-only (preserved)", report["target_only_files"]),
                         ("local-only source (unsafe to copy)", report["source_local_only_files"]),
                         ("protected target changed", report["protected_target_changes"]),
                         ("outside-scope target changes", report["target_dirty_paths_outside_sync_scope"]),
                         ("missing ignore", report["missing_ignore_rules"])]:
        lines.extend(f"  {label}: {path}" for path in paths)
    if ending_changes:
        lines.append("CRLF-only differences are " + ("warnings (--ignore-crlf)." if report["ignore_crlf"] else "counted; use --ignore-crlf only if the project allows LF/CRLF normalization."))
    if any(report["unsafe_paths"].values()) or report["repository_changed_during_audit"]:
        lines.append("Unsafe paths or concurrent changes detected; inspect the JSON report.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", default=r"D:\workspace\gittest\CreateMyCard")
    parser.add_argument("--target-repo", default=r"D:\workspace\gittest\GenUI")
    parser.add_argument("--source-path", default="widget_service/cloud")
    parser.add_argument("--target-path", default="genui-agent/cloud")
    parser.add_argument("--phase", choices=("before", "after"), default="before", help="after allows target worktree changes; it does not authorize them")
    parser.add_argument("--ignore-crlf", action="store_true", help="Explicitly tolerate CRLF/LF-only differences in UTF-8 text; never rewrites files")
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of the concise summary")
    parser.add_argument("--before-report", help="Previous JSON report to verify protected target files")
    parser.add_argument("--output", help="Write a NEW UTF-8 JSON report outside both repositories (never overwrite)")
    args = parser.parse_args()
    try:
        report = inspect(args)
        rendered = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
        if args.output:
            output = Path(args.output).resolve()
            if any(output.is_relative_to(Path(report[key])) for key in ("source_repo", "target_repo")):
                raise ValueError("Report must be outside both repositories")
            with output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        print(rendered if args.json else summary(report), end="" if args.json else "\n")
        if args.output and not args.json:
            print(f"Report: {output}")
        return report["exit_code"]
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"result": "AUDIT_ERROR", "error": str(exc), "exit_code": 2}, ensure_ascii=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
