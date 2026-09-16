"""Tests for the pinned Typst dev toolchain (plan 2026-09-13, task M2-00A).

Deterministic and offline: every install/verify run here uses the documented
test-only overrides (TYPST_TOOL_MANIFEST / TYPST_TOOL_ROOT / TYPST_TOOL_TEST_OS
/ TYPST_TOOL_TEST_ARCH) against fake artifacts in a temporary directory. The
overrides change where data comes from, never whether it is checked — the
production manifest and the pinned digests are asserted separately below and
are never mutated by these tests. The only "network" touched is a refused
connection to 127.0.0.1, which proves the error path without egress.

The fake binary also appends to $TYPST_RUN_MARKER whenever it is executed, so
the tests can PROVE the check-ordering contract: a tampered binary, a binary
with missing/malformed provenance, and an archive with unsafe members never
reach execution — the marker stays absent.
"""

import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "typst"
INSTALL_SH = TOOL_DIR / "install.sh"
VERIFY_SH = TOOL_DIR / "verify.sh"

PINNED_VERSION = "0.15.1"
PINNED_ASSET = "typst-x86_64-unknown-linux-musl.tar.xz"
PINNED_URL = (
    "https://github.com/typst/typst/releases/download/v0.15.1/"
    + PINNED_ASSET
)
PINNED_SHA256 = "a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c"


FAKE_TYPST = """#!/bin/sh
if [ -n "${{TYPST_RUN_MARKER:-}}" ]; then : >> "$TYPST_RUN_MARKER"; fi
echo "typst {version} (test artifact)"
"""


def make_fake_archive(archive_path: Path, version: str) -> str:
    """Build a tar.gz that extracts to a single executable 'typst' which
    prints the given version. Returns its sha256 hex digest."""
    payload = FAKE_TYPST.format(version=version).encode("utf-8")
    with tarfile.open(archive_path, "w:gz") as tar:
        info = tarfile.TarInfo("typst")
        info.size = len(payload)
        info.mode = 0o755
        tar.addfile(info, BytesIO(payload))
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


def make_manifest(tmp: Path, *, url: str, sha256: str,
                  version: str = PINNED_VERSION) -> Path:
    manifest = {
        "name": "typst",
        "version": version,
        "channel": "stable",
        "license": "Apache-2.0",
        "asset": Path(url.split("//")[-1]).name if "://" in url else Path(url).name,
        "url": url,
        "sha256": sha256,
        "binary_in_archive": "typst",
        "platform": {"kernel": "Linux", "arch": "x86_64", "libc": "musl"},
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def run_script(script: Path, manifest: Path, root: Path, marker: Path = None):
    env = dict(os.environ)
    env["TYPST_TOOL_MANIFEST"] = str(manifest)
    env["TYPST_TOOL_ROOT"] = str(root)
    if marker is not None:
        env["TYPST_RUN_MARKER"] = str(marker)
    return subprocess.run(
        ["bash", str(script)],
        env=env, capture_output=True, text=True, timeout=120,
    )


def _add_text(tar: tarfile.TarFile, name: str, payload: bytes) -> None:
    """Add a regular file member, possibly with a malicious name."""
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(payload), 0o644
    tar.addfile(info, BytesIO(payload))


def _add_link(tar: tarfile.TarFile, name: str, kind: bytes, target: str) -> None:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = target
    tar.addfile(info)


class TypstToolchainTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="typst-tool-test-")
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "root"
        self.marker = self.tmp / "executed.marker"
        self.addCleanup(self._tmp.cleanup)

    def _fake_source_archive(self, version: str = PINNED_VERSION):
        archive = self.tmp / PINNED_ASSET.replace(".tar.xz", ".tar.gz")
        sha = make_fake_archive(archive, version)
        return archive, sha

    def _install_ok(self, version: str = PINNED_VERSION):
        """Install a matching fake artifact; returns its manifest path."""
        archive, sha = self._fake_source_archive(version=version)
        manifest = make_manifest(self.tmp, url=str(archive), sha256=sha)
        proc = run_script(INSTALL_SH, manifest, self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return manifest

    def _reset_marker(self):
        """Forget every execution that happened before this point."""
        self.marker.unlink(missing_ok=True)

    def _assert_executed(self):
        self.assertTrue(self.marker.exists(),
                        "the binary was never executed, but a fully verified "
                        "toolchain must still run --version")

    def _assert_never_executed(self):
        self.assertFalse(self.marker.exists(),
                         "the binary was EXECUTED although verification must "
                         "fail before any execution")

    def _state(self) -> Path:
        return self.root / "bin" / ".install-state"

    def _write_state(self, text: str):
        self._state().write_text(text, encoding="utf-8")

    def _patch_state(self, **updates):
        lines = {}
        for line in self._state().read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            lines[key] = value
        lines.update({k: str(v) for k, v in updates.items()})
        self._write_state("".join(f"{k}={v}\n" for k, v in lines.items()))

    # --- happy path -----------------------------------------------------------

    def test_install_success_then_verify_offline_ok(self):
        archive, sha = self._fake_source_archive()
        manifest = make_manifest(self.tmp, url=str(archive), sha256=sha)

        proc = run_script(INSTALL_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout + proc.stderr
        self.assertIn(PINNED_VERSION, out)          # observable version
        self.assertIn(sha, out)                     # observable checksum

        binary = self.root / "bin" / "typst"
        self.assertTrue(binary.is_file() and os.access(binary, os.X_OK))
        state = self.root / "bin" / ".install-state"
        self.assertTrue(state.is_file())
        self.assertIn(f"asset_sha256={sha}", state.read_text())

        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(PINNED_VERSION, proc.stdout)
        self._assert_executed()                     # verified => execution allowed

    def test_installer_is_rerunnable(self):
        archive, sha = self._fake_source_archive()
        manifest = make_manifest(self.tmp, url=str(archive), sha256=sha)
        for attempt in (1, 2):
            proc = run_script(INSTALL_SH, manifest, self.root)
            self.assertEqual(proc.returncode, 0, f"run {attempt}: {proc.stderr}")
            self.assertTrue((self.root / "bin" / "typst").is_file())
        leftovers = sorted(p.name for p in (self.root / "bin").iterdir())
        self.assertEqual(leftovers, [".install-state", "typst"])
        self.assertEqual(sorted(p.name for p in (self.root / "download").iterdir()), [])

    def test_installer_handles_the_official_nested_layout(self):
        # The real asset nests everything under typst-x86_64-unknown-linux-musl/.
        archive = self.tmp / "nested.tar.gz"
        payload = FAKE_TYPST.format(version=PINNED_VERSION).encode("utf-8")
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo("typst-x86_64-unknown-linux-musl/typst")
            info.size, info.mode = len(payload), 0o755
            tar.addfile(info, BytesIO(payload))
            lic = b"Apache-2.0 (fake)"
            info = tarfile.TarInfo("typst-x86_64-unknown-linux-musl/LICENSE")
            info.size, info.mode = len(lic), 0o644
            tar.addfile(info, BytesIO(lic))
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        manifest = make_manifest(self.tmp, url=str(archive), sha256=sha)
        proc = run_script(INSTALL_SH, manifest, self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.root / "bin" / "typst").is_file())
        self.assertIn("Apache-2.0", (self.root / "bin" / "LICENSE").read_text())

    # --- altered / wrong artifacts are rejected ---------------------------------

    def test_corrupted_archive_fails_before_extraction(self):
        archive, _sha = self._fake_source_archive()
        manifest = make_manifest(
            self.tmp, url=str(archive),
            sha256="0" * 64,  # digest does not match the bytes on disk
        )
        proc = run_script(INSTALL_SH, manifest, self.root)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("checksum mismatch", proc.stderr)
        self.assertFalse((self.root / "bin" / "typst").exists())

    def test_wrong_version_binary_is_rejected(self):
        archive, sha = self._fake_source_archive(version="0.14.3")
        manifest = make_manifest(self.tmp, url=str(archive), sha256=sha)
        proc = run_script(INSTALL_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertIn("version mismatch", proc.stderr)
        self.assertFalse((self.root / "bin" / "typst").exists())

    # --- install: unsafe archive members are rejected BEFORE extraction ---------

    def _malicious_manifest(self, add_member):
        """Build an archive whose checksum MATCHES the manifest but that hides
        a dangerous member. Returns the manifest path."""
        archive = self.tmp / "malicious.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            add_member(tar)
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        return make_manifest(self.tmp, url=str(archive), sha256=sha)

    @staticmethod
    def _add_regular(tar, name="typst", version=PINNED_VERSION):
        payload = FAKE_TYPST.format(version=version).encode("utf-8")
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(payload), 0o755
        tar.addfile(info, BytesIO(payload))

    def _assert_malicious_rejected(self, manifest, outside: Path):
        proc = run_script(INSTALL_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("refusing to extract", proc.stderr)
        self._assert_never_executed()
        self.assertFalse((self.root / "bin" / "typst").exists())
        self.assertFalse(outside.exists(),
                         "the archive wrote outside the extraction directory")
        return proc

    def test_install_rejects_parent_traversal_archive(self):
        manifest = self._malicious_manifest(lambda tar: (
            self._add_regular(tar),
            _add_text(tar, "../../../escaped.txt", b"escaped"),
        ))
        self._assert_malicious_rejected(manifest, self.root / "escaped.txt")

    def test_install_rejects_absolute_path_archive(self):
        sentinel = Path("/tmp") / ("typst-tool-test-absolute-%d" % os.getpid())
        sentinel.unlink(missing_ok=True)
        self.addCleanup(sentinel.unlink, missing_ok=True)
        manifest = self._malicious_manifest(lambda tar: (
            self._add_regular(tar),
            _add_text(tar, str(sentinel), b"escaped"),
        ))
        self._assert_malicious_rejected(manifest, sentinel)

    def test_install_rejects_symlink_archive(self):
        # A 'typst' that is a symlink to /etc/passwd: extracting and chmod'ing
        # or executing it would touch a file outside the repo. It must be
        # rejected by the member scan, before extraction and execution.
        passwd = Path("/etc/passwd")
        mode_before = passwd.stat().st_mode
        manifest = self._malicious_manifest(lambda tar: _add_link(
            tar, "typst", tarfile.SYMTYPE, "/etc/passwd"))
        proc = run_script(INSTALL_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("refusing to extract", proc.stderr)
        self._assert_never_executed()
        self.assertFalse((self.root / "bin" / "typst").exists())
        self.assertEqual(passwd.stat().st_mode, mode_before)

    def test_install_rejects_hardlink_and_special_member_archives(self):
        manifest = self._malicious_manifest(lambda tar: (
            self._add_regular(tar),
            _add_link(tar, "typst.link", tarfile.LNKTYPE, "typst"),
        ))
        self._assert_malicious_rejected(
            manifest, self.root / "bin" / "typst.link")

        manifest = self._malicious_manifest(lambda tar: (
            self._add_regular(tar),
            _add_link(tar, "pipe", tarfile.FIFOTYPE, ""),
        ))
        self._assert_malicious_rejected(manifest, self.root / "bin" / "pipe")

    def test_verify_fails_for_missing_binary(self):
        archive, sha = self._fake_source_archive()
        manifest = make_manifest(self.tmp, url=str(archive), sha256=sha)
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("missing", proc.stderr)
        self._assert_never_executed()

    # --- verify: provenance and digests gate EXECUTION ---------------------------

    def test_verify_wrong_version_reports_four_only_after_consistent_provenance(self):
        # A binary from another release whose provenance record was made
        # consistent with it: every byte check passes, so --version may run
        # and the version gate is what rejects it (exit 4).
        manifest = self._install_ok()
        binary = self.root / "bin" / "typst"
        other, _ = self._fake_source_archive(version="0.9.9")
        with tarfile.open(other, "r:gz") as tar:
            payload = tar.extractfile("typst").read()
        binary.write_bytes(payload)
        self._patch_state(binary_sha256=hashlib.sha256(payload).hexdigest())
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertIn("wrong version", proc.stderr)
        self._assert_executed()

    def test_verify_tampered_binary_never_executes(self):
        # Right version string, different bytes: the sha256-vs-provenance
        # check must stop it BEFORE the binary is ever run.
        manifest = self._install_ok()
        binary = self.root / "bin" / "typst"
        binary.write_text(FAKE_TYPST.format(version=PINNED_VERSION) + "# tampered\n",
                          encoding="utf-8")
        binary.chmod(0o755)
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("modified after install", proc.stderr)
        self._assert_never_executed()

    def test_verify_missing_provenance_fails_not_warns(self):
        manifest = self._install_ok()
        self._state().unlink()
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("no provenance record", proc.stderr)
        self.assertNotIn("warning", proc.stderr)
        self._assert_never_executed()

    def test_verify_malformed_provenance_never_executes(self):
        manifest = self._install_ok()
        self._write_state("this is not a key=value line\n")
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("malformed provenance", proc.stderr)
        self._assert_never_executed()

    def test_verify_provenance_without_binary_sha_never_executes(self):
        manifest = self._install_ok()
        lines = [line for line in self._state().read_text().splitlines()
                 if not line.startswith("binary_sha256=")]
        self._write_state("\n".join(lines) + "\n")
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("missing required key 'binary_sha256'", proc.stderr)
        self._assert_never_executed()

    def test_verify_provenance_with_invalid_sha_format_never_executes(self):
        manifest = self._install_ok()
        self._patch_state(binary_sha256="z" * 64)
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("not a SHA-256 digest", proc.stderr)
        self._assert_never_executed()

    def test_verify_provenance_asset_mismatch_never_executes(self):
        manifest = self._install_ok()
        self._patch_state(asset="typst-some-other-thing.tar.xz")
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("does not match the manifest asset", proc.stderr)
        self._assert_never_executed()

    def test_verify_provenance_url_mismatch_never_executes(self):
        manifest = self._install_ok()
        self._patch_state(source_url="https://example.invalid/other-release.tar.xz")
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("source URL does not match", proc.stderr)
        self._assert_never_executed()

    def test_verify_duplicate_or_unknown_provenance_keys_never_execute(self):
        manifest = self._install_ok()
        original = self._state().read_text()
        for extra, expected in (("asset=duplicate\n", "duplicate key"),
                                ("unexpected=value\n", "unknown key")):
            with self.subTest(extra=extra):
                self._write_state(original + extra)
                proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn(expected, proc.stderr)
                self._assert_never_executed()

    def test_failed_reinstall_preserves_the_verified_installation(self):
        manifest = self._install_ok()
        binary = self.root / "bin" / "typst"
        original_binary = binary.read_bytes()
        original_state = self._state().read_bytes()
        archive, _ = self._fake_source_archive(version="0.9.9")
        proc = run_script(INSTALL_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self._assert_never_executed()
        self.assertEqual(binary.read_bytes(), original_binary)
        self.assertEqual(self._state().read_bytes(), original_state)
        self.assertEqual(list((self.root / "download").iterdir()), [])
        proc = run_script(VERIFY_SH, manifest, self.root)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_verify_provenance_archive_digest_mismatch_never_executes(self):
        manifest = self._install_ok()
        self._patch_state(asset_sha256="b" * 64)
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("archive digest does not match", proc.stderr)
        self._assert_never_executed()

    def test_verify_provenance_version_mismatch_fails_before_execution(self):
        # The record names another typst version than the manifest pins: the
        # version verdict (4) comes from provenance, without running anything.
        manifest = self._install_ok()
        self._patch_state(typst_version="0.14.3")
        self._reset_marker()
        proc = run_script(VERIFY_SH, manifest, self.root, marker=self.marker)
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertIn("wrong version", proc.stderr)
        self._assert_never_executed()

    # --- clear errors, no silent fallbacks --------------------------------------

    def test_unsupported_platform_stops_before_any_fetch(self):
        manifest = make_manifest(
            self.tmp, url="https://github.invalid/never-fetched", sha256="ab" * 32,
        )
        env = dict(os.environ)
        env["TYPST_TOOL_MANIFEST"] = str(manifest)
        env["TYPST_TOOL_ROOT"] = str(self.root)
        env["TYPST_TOOL_TEST_OS"] = "Darwin"
        proc = subprocess.run(
            ["bash", str(INSTALL_SH)], env=env, capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("unsupported platform", proc.stderr)

    def test_network_failure_is_explicit(self):
        # Port 9 (discard) on loopback: connection refused, no egress.
        manifest = make_manifest(
            self.tmp, url="http://127.0.0.1:9/typst.tar.gz", sha256="ab" * 32,
        )
        proc = run_script(INSTALL_SH, manifest, self.root)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("download failed", proc.stderr)
        self.assertFalse((self.root / "bin" / "typst").exists())

    # --- production defaults are the pinned ones ---------------------------------

    def test_committed_manifest_matches_the_plan(self):
        manifest = json.loads((TOOL_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], PINNED_VERSION)
        self.assertEqual(manifest["asset"], PINNED_ASSET)
        self.assertEqual(manifest["url"], PINNED_URL)
        self.assertEqual(manifest["sha256"], PINNED_SHA256)
        self.assertEqual(manifest["license"], "Apache-2.0")
        self.assertEqual(manifest["platform"]["kernel"], "Linux")
        self.assertEqual(manifest["platform"]["arch"], "x86_64")
        # No override in the scripts can skip a verification: the checksum
        # comparison and the version comparison are unconditional statements.
        install_src = INSTALL_SH.read_text(encoding="utf-8")
        self.assertIn('if [ "$(printf \'%s\' "$actual_sha"', install_src)
        self.assertIn('if [ "$actual_ver" != "$version" ]; then', install_src)
        # The member safety scan runs before the tar extraction command.
        self.assertLess(install_src.index("archive_is_safe \"$archive\""),
                        install_src.index("tar --no-same-owner -xf"))
        # verify.sh executes the binary only after the provenance/digest gate:
        # the --version execution appears after the binary_sha256 comparison.
        verify_src = VERIFY_SH.read_text(encoding="utf-8")
        self.assertLess(verify_src.index('"$state_binary_sha256")" ]'),
                        verify_src.index('"$bin" --version'))

    def test_downloads_and_binaries_are_git_ignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/tools/typst/bin/", gitignore)
        self.assertIn("/tools/typst/download/", gitignore)

    def test_scripts_pass_bash_syntax_check(self):
        for script in (INSTALL_SH, VERIFY_SH):
            proc = subprocess.run(
                ["bash", "-n", str(script)], capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(proc.returncode, 0, f"{script.name}: {proc.stderr}")


if __name__ == "__main__":
    unittest.main()
