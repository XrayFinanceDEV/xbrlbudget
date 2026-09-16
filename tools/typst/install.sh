#!/usr/bin/env bash
# install.sh — pinned Typst dev-toolchain installer (plan 2026-09-13, task M2-00A).
#
# What it does, in order:
#   1. platform gate (Linux x86_64 — the pinned asset is the musl build);
#   2. fetch the release asset named in manifest.json to a temporary file
#      (curl/wget, no curl-pipe-shell; never writes into git-tracked paths);
#   3. verify its SHA-256 against the pinned digest BEFORE any extraction;
#   4. scan the archive members BEFORE extracting — any absolute path, parent
#      traversal ('..'), symlink, hardlink or special-file member is rejected
#      — then extract into a temporary directory (ignoring foreign owners) and
#      check `typst --version` against the pinned version;
#   5. install the binary atomically into bin/typst (ignored, repo-local) and
#      record provenance in bin/.install-state.
#
# Rerunnable: a second run re-verifies and replaces the installed binary in
# place. Nothing here is ever committed — see /tools/typst/ in .gitignore.
# Container/production packaging is a separate milestone (M2-06B); this script
# is for developer machines and the M2-00 spike only.
#
# Test-only environment overrides (they change WHERE things come from, never
# WHETHER they are verified — production defaults are the pinned manifest and
# the real download, and no override disables a check):
#   TYPST_TOOL_MANIFEST   path to an alternate manifest JSON
#   TYPST_TOOL_ROOT       install root; bin/ and download/ are created there
#   TYPST_TOOL_TEST_OS    pretend `uname -s` output (platform-gate tests only)
#   TYPST_TOOL_TEST_ARCH  pretend `uname -m` output (platform-gate tests only)
#
# Exit codes: 0 ok · 1 usage/missing-tool/fetch/extract · 2 unsupported
# platform · 3 checksum mismatch (altered artifact) · 4 wrong version.
set -euo pipefail

tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
manifest="${TYPST_TOOL_MANIFEST:-$tool_dir/manifest.json}"
root="${TYPST_TOOL_ROOT:-$tool_dir}"
bin_dir="$root/bin"
download_root="$root/download"

tmp_bin=""
work_dir=""
cleanup() {
    [ -n "$tmp_bin" ] && rm -f -- "$tmp_bin"
    [ -n "$work_dir" ] && rm -rf -- "$work_dir"
    return 0
}
trap cleanup EXIT

die() { # die <code> <message>
    printf 'install: error: %s\n' "$2" >&2
    exit "$1"
}

need_cmd() { # need_cmd <name>
    command -v "$1" >/dev/null 2>&1 \
        || die 1 "required tool '$1' is not installed; install it and rerun"
}

sha256_of() { # sha256_of <file>
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -- "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -- "$1" | cut -d' ' -f1
    else
        die 1 "no sha256sum/shasum tool found; cannot verify the artifact"
    fi
}

json_get() { # json_get <file> <dotted.key>
    python3 - "$1" "$2" <<'PY' || die 1 "cannot read key '$2' from manifest $1 (missing file or malformed JSON)"
import json, sys
cur = json.load(open(sys.argv[1]))
for part in sys.argv[2].split('.'):
    cur = cur[part]
print(cur)
PY
}

archive_is_safe() { # archive_is_safe <archive> — member scan, BEFORE extraction
    python3 - "$1" <<'PY' || die 1 "refusing to extract: the archive holds unsafe members (absolute paths, parent traversal, symlinks/hardlinks, special files)"
import sys, tarfile

ALLOWED = {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}
with tarfile.open(sys.argv[1], "r:*") as tar:
    for m in tar:
        parts = m.name.split('/')
        if m.name.startswith('/') or '..' in parts:
            print("install: unsafe archive member path: %r" % (m.name,), file=sys.stderr)
            sys.exit(1)
        if m.type not in ALLOWED or m.issym() or m.islnk():
            print("install: unsafe archive member type for: %r" % (m.name,), file=sys.stderr)
            sys.exit(1)
PY
}

# --- dependencies -----------------------------------------------------------
need_cmd tar
need_cmd python3
need_cmd mktemp
need_cmd uname
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
    || die 1 "need curl or wget to fetch the pinned artifact"

[ -f "$manifest" ] || die 1 "manifest not found at $manifest"

# --- 1. platform gate -------------------------------------------------------
want_kernel="$(json_get "$manifest" platform.kernel)"
want_arch="$(json_get "$manifest" platform.arch)"
got_kernel="${TYPST_TOOL_TEST_OS:-$(uname -s)}"
got_arch="${TYPST_TOOL_TEST_ARCH:-$(uname -m)}"
if [ "$got_kernel" != "$want_kernel" ] || [ "$got_arch" != "$want_arch" ]; then
    die 2 "unsupported platform: this toolchain pins ${want_kernel}/${want_arch}, this machine is ${got_kernel}/${got_arch}; see tools/typst/README.md"
fi

# --- 2. fetch ---------------------------------------------------------------
url="$(json_get "$manifest" url)"
asset="$(json_get "$manifest" asset)"
version="$(json_get "$manifest" version)"
expected_sha="$(json_get "$manifest" sha256)"

case "$asset" in
    *.xz) need_cmd xz ;;
esac

mkdir -p -- "$download_root"
work_dir="$(mktemp -d "$download_root/run.XXXXXX")" \
    || die 1 "cannot create a temporary directory under $download_root"
archive="$work_dir/$asset"

printf 'install: fetching pinned artifact\n'
printf '  url:     %s\n' "$url" >&2
case "$url" in
    file://*)
        src="${url#file://}"
        [ -f "$src" ] || die 1 "local artifact $src does not exist"
        cp -- "$src" "$archive"
        ;;
    http://*|https://*)
        if command -v curl >/dev/null 2>&1; then
            curl --fail --location --proto '=https' --proto-redir '=https' \
                 --connect-timeout 15 --retry 3 --speed-time 60 \
                 -o "$archive" -- "$url" \
                || die 1 "download failed (network unreachable or artifact gone): $url"
        else
            wget --tries=3 --timeout=30 -O "$archive" -- "$url" \
                || die 1 "download failed (network unreachable or artifact gone): $url"
        fi
        ;;
    *)
        [ -f "$url" ] || die 1 "cannot fetch '$url': not a URL and not an existing file"
        cp -- "$url" "$archive"
        ;;
esac
[ -s "$archive" ] || die 1 "downloaded artifact is empty: $asset"

# --- 3. verify BEFORE extraction ---------------------------------------------
printf 'install: expected sha256 (pinned): %s\n' "$expected_sha"
actual_sha="$(sha256_of "$archive")"
printf 'install: artifact sha256 (actual): %s\n' "$actual_sha"
if [ "$(printf '%s' "$actual_sha" | tr 'A-F' 'a-f')" != "$(printf '%s' "$expected_sha" | tr 'A-F' 'a-f')" ]; then
    die 3 "checksum mismatch: the artifact is altered or is not the pinned release; refusing to extract. Expected $expected_sha, got $actual_sha"
fi

# --- 4. extract + version gate ------------------------------------------------
extract_dir="$work_dir/extract"
mkdir -p -- "$extract_dir"
archive_is_safe "$archive"
tar --no-same-owner -xf "$archive" -C "$extract_dir" \
    || die 1 "extraction failed even though the checksum and the member scan passed; the pinned digest may name a wrong format"
# The official asset nests everything under typst-x86_64-unknown-linux-musl/;
# find the pinned binary wherever the layout puts it (first match only).
binary_name="$(json_get "$manifest" binary_in_archive)"
src_bin="$(find "$extract_dir" -type f -name "$binary_name" -print -quit)"
[ -n "$src_bin" ] || die 1 "archive verified but does not contain a '$binary_name' file as expected"
chmod 0755 -- "$src_bin"

ver_out="$("$src_bin" --version 2>&1)" || die 4 "the extracted binary refuses to run '--version'"
printf '%s\n' "$ver_out" | sed -n '1p'
actual_ver="$(printf '%s\n' "$ver_out" | sed -n 's/^typst \([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -n 1)"
[ -n "$actual_ver" ] || die 4 "cannot parse a version from the binary's --version output"
if [ "$actual_ver" != "$version" ]; then
    die 4 "version mismatch: manifest pins typst $version but the artifact reports $actual_ver"
fi

# --- 5. atomic install ---------------------------------------------------------
mkdir -p -- "$bin_dir"
tmp_bin="$bin_dir/typst.new.$$"
cp -- "$src_bin" "$tmp_bin"
chmod 0755 -- "$tmp_bin"
mv -f -- "$tmp_bin" "$bin_dir/typst"
tmp_bin=""
bin_sha="$(sha256_of "$bin_dir/typst")"
{
    printf 'typst_version=%s\n' "$version"
    printf 'asset=%s\n' "$asset"
    printf 'asset_sha256=%s\n' "$actual_sha"
    printf 'binary_sha256=%s\n' "$bin_sha"
    printf 'source_url=%s\n' "$url"
} > "$bin_dir/.install-state"

# Keep the artifact's license texts beside the binary (Apache-2.0, Typst).
for doc in LICENSE NOTICE; do
    found="$(find "$extract_dir" -maxdepth 2 -type f -name "$doc" -print -quit)"
    [ -n "$found" ] && cp -f -- "$found" "$bin_dir/$doc"
done

printf 'install: ok\n'
printf '  version:  typst %s\n' "$version"
printf '  asset:    %s\n' "$asset"
printf '  sha256:   %s\n' "$actual_sha"
printf '  binary:   %s (sha256 %s)\n' "$bin_dir/typst" "$bin_sha"
