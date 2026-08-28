"""Integration tests: isolated temporary Git repositories, never real repositories."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import verify_sync as audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verify-sync-test-")
        self.root = Path(self.temp.name)
        self.src, self.dst = self.root / "source", self.root / "target"
        for repo in (self.src, self.dst):
            repo.mkdir()
            self.git(repo, "init", "-q")
            for key, value in [("user.name", "Audit Test"), ("user.email", "audit@example.invalid"),
                               ("core.autocrlf", "false"), ("commit.gpgsign", "false"),
                               ("core.hooksPath", str(self.root / "no-hooks"))]:
                self.git(repo, "config", key, value)
            self.write(repo, "cloud/a.py", b"value=1\n")
            self.write(repo, "cloud/config/local.txt", b"local config\n")
            self.write(repo, "cloud/engine/config/rules.json", b"{}\n")
            self.write(repo, "cloud/binary.dat", b"\x00\x01\xff")
            self.write(repo, "cloud/space 中文.txt", "中文\n".encode())
            self.write(repo, ".gitignore", b"__pycache__/\n*.py[cod]\n*.log\nprivate.tmp\n")
            self.commit(repo)
        self.args = argparse.Namespace(source_repo=str(self.src), target_repo=str(self.dst),
            source_path="cloud", target_path="cloud", phase="before", before_report=None, ignore_crlf=False)

    def tearDown(self):
        # TemporaryDirectory only removes the exact directory it created.
        assert self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve())
        assert self.root.name.startswith("verify-sync-test-")
        self.temp.cleanup()

    def git(self, repo, *args):
        return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)

    def write(self, repo, path, data):
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)

    def commit(self, repo):
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-qm", "test state")

    def snapshot(self, repo):
        # Include Git metadata to detect accidental refresh/stage/commit writes.
        return {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}

    def test_matches_without_modifying_files_or_git_metadata(self):
        before = self.snapshot(self.src), self.snapshot(self.dst)
        result = audit.inspect(self.args)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["source_tracked_files"], 4)
        self.assertEqual((self.snapshot(self.src), self.snapshot(self.dst)), before)

    def test_same_size_same_timestamp_content_difference(self):
        original = (self.dst / "cloud/a.py").stat()
        self.write(self.dst, "cloud/a.py", b"value=2\n")
        os.utime(self.dst / "cloud/a.py", ns=(original.st_atime_ns, original.st_mtime_ns))
        self.commit(self.dst)  # Clean target with a committed independent change.
        result = audit.inspect(self.args)
        self.assertEqual(result["exit_code"], 1)
        self.args.ignore_crlf = True
        self.assertEqual(audit.inspect(self.args)["exit_code"], 1)
        self.assertEqual(result["different_target_files"], [{"path": "a.py", "line_endings_only": False}])

    def test_ignored_local_source_file_is_not_a_committed_input(self):
        self.write(self.src, "cloud/private.tmp", b"must not copy\n")
        result = audit.inspect(self.args)
        self.assertTrue(result["source_clean"])
        self.assertEqual(result["source_local_only_files"], ["private.tmp"])
        self.assertEqual(result["exit_code"], 2)

    def test_all_exclusions_and_nested_config(self):
        for name in ("config/local.txt", "__pycache__/x.txt", "nested/__pycache__/x.txt", "x.pyc", "x.pyo", "x.pyd", "x.log"):
            self.write(self.src, "cloud/" + name, b"excluded difference\n")
        self.commit(self.src)
        self.assertEqual(audit.inspect(self.args)["exit_code"], 0)
        self.write(self.src, "cloud/engine/config/rules.json", b'{"v":1}\n')
        self.commit(self.src)
        self.assertEqual(audit.inspect(self.args)["different_target_files"][0]["path"], "engine/config/rules.json")

    def test_missing_and_target_only_files(self):
        self.write(self.src, "cloud/new.py", b"new\n")
        self.commit(self.src)
        self.write(self.dst, "cloud/target-only.txt", b"keep\n")
        self.commit(self.dst)
        result = audit.inspect(self.args)
        self.assertEqual(result["missing_target_files"], ["new.py"])
        self.assertEqual(result["target_only_files"], ["target-only.txt"])

    def test_after_report_catches_protected_changes(self):
        self.write(self.dst, "cloud/target-only.txt", b"keep\n")
        self.commit(self.dst)
        before = audit.inspect(self.args)
        report_path = self.root / "before.json"
        report_path.write_text(json.dumps(before), encoding="utf-8")
        self.write(self.dst, "cloud/config/local.txt", b"oops\n")
        self.write(self.dst, "cloud/target-only.txt", b"oops\n")
        self.args.phase, self.args.before_report = "after", str(report_path)
        result = audit.inspect(self.args)
        self.assertEqual(result["protected_target_changes"], ["config/local.txt", "target-only.txt"])
        self.assertEqual(result["exit_code"], 2)

    def test_after_allows_expected_changes_but_rejects_outside_changes(self):
        self.write(self.src, "cloud/a.py", b"value=2\n")
        self.commit(self.src)
        self.write(self.dst, "cloud/a.py", b"value=2\n")
        self.args.phase = "after"
        self.assertEqual(audit.inspect(self.args)["exit_code"], 0)
        self.write(self.dst, "outside.txt", b"unrelated\n")
        result = audit.inspect(self.args)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["target_dirty_paths_outside_sync_scope"], ["outside.txt"])

    def test_source_dirty_reads_committed_bytes(self):
        self.write(self.src, "cloud/a.py", b"uncommitted\n")
        result = audit.inspect(self.args)
        self.assertEqual(result["different_target_files"], [])
        self.assertFalse(result["source_clean"])
        self.assertEqual(result["exit_code"], 2)

    def test_line_endings_are_reported_separately_not_silently_normalized(self):
        self.write(self.dst, "cloud/a.py", b"value=1\r\n")
        self.commit(self.dst)
        result = audit.inspect(self.args)
        self.assertEqual(result["different_target_files"], [{"path": "a.py", "line_endings_only": True}])
        self.assertEqual(result["exit_code"], 1)
        self.args.ignore_crlf = True
        self.assertEqual(audit.inspect(self.args)["exit_code"], 0)

    @unittest.skipUnless(os.name == "nt", "Robocopy is Windows-specific")
    def test_actual_robocopy_misses_same_metadata_but_audit_detects_it(self):
        self.write(self.dst, "cloud/a.py", b"value=2\n")
        self.commit(self.dst)
        source_file, target_file = self.src / "cloud/a.py", self.dst / "cloud/a.py"
        stamp = 1_700_000_000_000_000_000
        for path in (source_file, target_file):
            os.utime(path, ns=(stamp, stamp))
        result = subprocess.run(["robocopy", str(source_file.parent), str(target_file.parent),
            "a.py", "/R:0", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS"], capture_output=True)
        self.assertLess(result.returncode, 8)
        self.assertEqual(target_file.read_bytes(), b"value=2\n")
        self.assertEqual(audit.inspect(self.args)["exit_code"], 1)

    def test_missing_ignore_rules(self):
        self.write(self.dst, ".gitignore", b"*.log\n")
        self.commit(self.dst)
        result = audit.inspect(self.args)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(len(result["missing_ignore_rules"]), 4)

    def test_escaped_scope_is_rejected(self):
        self.args.source_path = "../target/cloud"
        with self.assertRaises(ValueError):
            audit.inspect(self.args)

    def test_symlink_or_junction_is_not_followed(self):
        link = self.src / "cloud/escape"
        try:
            link.symlink_to(self.dst / "cloud", target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("Symlinks unavailable")
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(self.dst / "cloud")], check=True, capture_output=True)
        result = audit.inspect(self.args)
        self.assertEqual(result["unsafe_paths"]["source"], ["escape"])
        self.assertEqual(result["exit_code"], 2)


if __name__ == "__main__":
    unittest.main()
