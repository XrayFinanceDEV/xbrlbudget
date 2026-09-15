#!/usr/bin/env bash
# verify.sh — offline verifier for the pinned Typst dev toolchain (M2-00A).
#
# Checks, without touching the network, in this EXACT order. The contract is
# that the installed binary is executed only AFTER it has been proven to be
# the same bytes install.sh measured — a tampered or uncertified binary never
# reaches the --version execution, whatever it would print:
#
#   1. manifest readable (version, asset, pinned archive sha256);
#   2. bin/typst exists and is executable;
#   3. bin/.install-state exists, is well-formed (key=value lines with
#      [A-Za-z0-9_]+ keys), and carries ALL required keys: typst_version,
#      asset, asset_sha256, binary_sha256, source_url. A missing or malformed
#      provenance record is a hard failure — never a warning — because a
#      binary nobody certified is an unverified binary;
#   4. provenance agrees with the pinned manifest: typst_version (exit 4),
#      asset name and asset_sha256 vs the pinned archive digest (exit 1);
#   5. the binary's SHA-256 equals the recorded binary_sha256 (exit 1), i.e.
#      nobody modified the binary after install.sh wrote the record;
#   6. only NOW `bin/typst --version` is executed, and it must report exactly
#      the version pinned in manifest.json (exit 4).
#
# Prints the exact version and checksums so a reviewer can compare them with
# the official release page. Rerunnable; read-only apart from nothing.
#
# Environment overrides (test-only, same policy as install.sh — no check can
# be disabled):
#   TYPST_TOOL_MANIFEST   path to an alternate manifest JSON
#   TYPST_TOOL_ROOT       root where bin/typst lives
#
# Exit codes:
#   0 ok
#   1 missing manifest/tool/binary · provenance missing, malformed, missing a
#     required key, or carrying an asset/archive digest that contradicts the
#     pinned manifest · binary modified after install (sha256 != provenance)
#   4 wrong version: the provenance record names another typst version (the
#     binary is NOT executed on this path), or the fully verified installed
#     binary reports one / refuses to run
set -euo pipefail

tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
manifest="${TYPST_TOOL_MANIFEST:-$tool_dir/manifest.json}"
root="${TYPST_TOOL_ROOT:-$tool_dir}"
bin="$root/bin/typst"
state="$root/bin/.install-state"

die() { printf 'verify: error: %s\n' "$2" >&2; exit "$1"; }

json_get() {
    python3 - "$1" "$2" <<'PY' || die 1 "cannot read key '$2' from manifest $1 (missing file or malformed JSON)"
import json, sys
cur = json.load(open(sys.argv[1]))
for part in sys.argv[2].split('.'):
    cur = cur[part]
print(cur)
PY
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum -- "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 -- "$1" | cut -d' ' -f1
    else
        die 1 "no sha256sum/shasum tool found"
    fi
}

norm_sha() { printf '%s' "$1" | tr 'A-F' 'a-f'; }

is_sha256_hex() { printf '%s' "$1" | grep -Eq '^[0-9a-fA-F]{64}$'; }

command -v python3 >/dev/null 2>&1 || die 1 "required tool 'python3' is not installed"
[ -f "$manifest" ] || die 1 "manifest not found at $manifest"

version="$(json_get "$manifest" version)"
pinned_asset="$(json_get "$manifest" asset)"
pinned_sha="$(json_get "$manifest" sha256)"
pinned_url="$(json_get "$manifest" url)"

# --- 2. presence --------------------------------------------------------------
[ -f "$bin" ] && [ -x "$bin" ] \
    || die 1 "typst binary missing at $bin — run tools/typst/install.sh first"

# --- 3. provenance record: must exist and be well-formed -----------------------
[ -f "$state" ] \
    || die 1 "no provenance record at $state — refusing to certify a binary nobody installed verifiably; rerun tools/typst/install.sh"
# Defaults so the required-key loop and the comparisons below see real
# variables even when the record omits them (they are set from the file later).
state_typst_version="" state_asset="" state_asset_sha256="" state_binary_sha256=""
declare -A seen_keys=()
while IFS= read -r line || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    [ "${line#*=}" != "$line" ] \
        || die 1 "malformed provenance record $state: line without 'key=value': $line"
    key="${line%%=*}"
    printf '%s\n' "$key" | grep -Eq '^[A-Za-z0-9_]+$' \
        || die 1 "malformed provenance record $state: invalid key '$key'"
    case "$key" in
        typst_version|asset|asset_sha256|binary_sha256|source_url) ;;
        *) die 1 "malformed provenance record $state: unknown key '$key'" ;;
    esac
    [ -z "${seen_keys[$key]:-}" ] \
        || die 1 "malformed provenance record $state: duplicate key '$key'"
    seen_keys[$key]=1
    # shellcheck disable=SC2163  # key charset validated immediately above
    printf -v "state_$key" '%s' "${line#*=}"
done < "$state"

for k in typst_version asset asset_sha256 binary_sha256 source_url; do
    var="state_$k"
    [ -n "${!var:-}" ] \
        || die 1 "malformed provenance record $state: missing required key '$k' — rerun tools/typst/install.sh"
done

# --- 4. provenance vs pinned manifest ------------------------------------------
[ "$state_typst_version" = "$version" ] \
    || die 4 "wrong version: provenance records typst $state_typst_version but the manifest pins $version — rerun tools/typst/install.sh"
[ "$state_asset" = "$pinned_asset" ] \
    || die 1 "provenance asset '$state_asset' does not match the manifest asset '$pinned_asset' — rerun tools/typst/install.sh"
[ "$state_source_url" = "$pinned_url" ] \
    || die 1 "provenance source URL does not match the manifest URL — rerun tools/typst/install.sh"
is_sha256_hex "$state_asset_sha256" \
    || die 1 "malformed provenance record $state: asset_sha256 is not a SHA-256 digest"
[ "$(norm_sha "$state_asset_sha256")" = "$(norm_sha "$pinned_sha")" ] \
    || die 1 "provenance archive digest does not match the pinned manifest digest — the manifest was re-pinned after this install; rerun tools/typst/install.sh"
is_sha256_hex "$state_binary_sha256" \
    || die 1 "malformed provenance record $state: binary_sha256 is not a SHA-256 digest"

# --- 5. binary bytes vs provenance — BEFORE any execution ----------------------
bin_sha="$(sha256_of "$bin")"
[ "$(norm_sha "$bin_sha")" = "$(norm_sha "$state_binary_sha256")" ] \
    || die 1 "binary modified after install: sha256 is $bin_sha but provenance records $state_binary_sha256 — rerun tools/typst/install.sh"

# --- 6. only now the verified binary is executed -------------------------------
ver_out="$("$bin" --version 2>&1)" \
    || die 4 "the installed binary refuses to run '--version' (wrong or damaged binary)"
printf '%s\n' "$ver_out" | sed -n '1p'
actual_ver="$(printf '%s\n' "$ver_out" | sed -n 's/^typst \([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -n 1)"
[ -n "$actual_ver" ] || die 4 "cannot parse a version from the installed binary"
[ "$actual_ver" = "$version" ] \
    || die 4 "wrong version: manifest pins typst $version but $bin reports $actual_ver"

printf 'verify: ok\n'
printf '  version:        typst %s\n' "$version"
printf '  pinned asset:   %s\n' "$pinned_asset"
printf '  pinned sha256:  %s\n' "$pinned_sha"
printf '  provenance:     %s (consistent with manifest)\n' "$state"
printf '  installed at:   %s\n' "$bin"
printf '  binary sha256:  %s\n' "$bin_sha"
