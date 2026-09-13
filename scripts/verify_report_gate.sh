#!/usr/bin/env bash
# verify_report_gate.sh — repeatable regression gate for the final-report
# milestones (plan 2026-09-13, task M1-00).
#
# Encodes, in one fail-fast script, the exact verification commands used at the
# M1/M2 integration gates (plan section 7, M1-10): the documented backend
# pytest command, the full Vitest run, the TypeScript typecheck and the
# production frontend build. Each subcommand's exit code is preserved.
#
# The script never installs dependencies and never reads the production
# database: DATABASE_PATH is forced to a throwaway file and ANTHROPIC_API_KEY
# is unset for the backend run, exactly as in the documented command.
#
# Usage (from anywhere in the repo; the script is root-relative):
#   scripts/verify_report_gate.sh                  # full: all four gates
#   scripts/verify_report_gate.sh full             # same as above
#   scripts/verify_report_gate.sh backend [args]   # targeted: pytest only; args, when given,
#                                                  # fully replace the "tests" selection
#   scripts/verify_report_gate.sh vitest  [args]   # targeted: Vitest only, extra args appended
#   scripts/verify_report_gate.sh types            # targeted: tsc --noEmit only
#   scripts/verify_report_gate.sh build            # targeted: next production build only
#
# Environment overrides:
#   GATE_PYTHON     Python interpreter that has the backend dependencies.
#                   It is validated with an import-pytest sentinel, so a no-op
#                   binary (e.g. /bin/true) can never fake a green backend gate.
#                   Default order: backend/venv/bin/python,
#                   backend/venv/Scripts/python.exe, then python3 on PATH.
#
# The frontend gates always run against <repo root>/frontend — there is no
# source-directory override — and invoke node_modules/.bin binaries directly:
# nothing is installed and nothing is ever fetched through npx at run time.
#
# Exit codes: 0 on success; otherwise the exit code of the first failing
# subcommand; 2 for gate misuse (bad mode, unusable interpreter, missing
# local frontend binaries).

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2
FRONTEND="$ROOT/frontend"

# Sentinel printed by a validated interpreter; guards against a no-op binary
# (e.g. GATE_PYTHON=/bin/true) exiting 0 without ever importing pytest.
PYTHON_SENTINEL="verify_report_gate.python_ok"

die() {
    echo "verify_report_gate: $*" >&2
    exit 2
}

TMP_DB=""
cleanup_tmp_db() {
    if [ -n "$TMP_DB" ]; then
        rm -f -- "$TMP_DB"
    fi
}
trap cleanup_tmp_db EXIT

pick_python() {
    if [ -n "${GATE_PYTHON:-}" ]; then
        command -v "$GATE_PYTHON" >/dev/null 2>&1 || die "GATE_PYTHON=$GATE_PYTHON not executable"
        echo "$GATE_PYTHON"
        return
    fi
    for p in backend/venv/bin/python backend/venv/Scripts/python.exe; do
        if [ -x "$p" ]; then echo "$p"; return; fi
    done
    command -v python3 || command -v python || return 1
}

require_frontend_bin() {
    [ -d "$FRONTEND/node_modules" ] || \
        die "no node_modules in $FRONTEND — run 'npm install' there first (this gate never installs and never fetches anything)"
    [ -x "$FRONTEND/node_modules/.bin/$1" ] || \
        die "frontend dependency '$1' missing from $FRONTEND/node_modules/.bin — run 'npm install' in frontend/ (this gate has no npx download fallback)"
    command -v node >/dev/null 2>&1 || die "node not on PATH"
}

# run_gate <label> <command...> — fail-fast, preserves the command's exit code.
run_gate() {
    label="$1"
    shift
    echo "==> [$label]"
    "$@"
    code=$?
    if [ "$code" -ne 0 ]; then
        echo "GATE FAILED [$label] with exit code $code — stopping (fail-fast)." >&2
        exit "$code"
    fi
    echo "OK [$label]"
}

gate_backend() {
    py="$(pick_python)" || die "no Python interpreter found (set GATE_PYTHON or create backend/venv)"
    sentinel="$(GATE_PY_SENTINEL="$PYTHON_SENTINEL" "$py" -c 'import os, pytest; print(os.environ["GATE_PY_SENTINEL"])' 2>/dev/null || true)"
    [ "$sentinel" = "$PYTHON_SENTINEL" ] || \
        die "'$py' is not a Python interpreter that can import pytest (set GATE_PYTHON or create backend/venv)"
    TMP_DB="$(mktemp "${TMPDIR:-/tmp}/verify_report_gate.XXXXXX.db")" || die "mktemp failed"
    # The test suite builds its own engines; the throwaway DATABASE_PATH is a
    # belt-and-braces guard so this gate can never touch a production DB file.
    # (TMP_DB is removed on exit by cleanup_tmp_db, safely for odd paths.)
    if [ $# -eq 0 ]; then
        set -- tests
    fi
    env -u ANTHROPIC_API_KEY DATABASE_PATH="$TMP_DB" \
        "$py" -m pytest "$@" -q --ignore=tests/corpus -p no:cacheprovider \
        -W ignore::DeprecationWarning
}

gate_vitest() {
    require_frontend_bin vitest
    ( cd "$FRONTEND" && ./node_modules/.bin/vitest run "$@" )
}

gate_types() {
    require_frontend_bin tsc
    ( cd "$FRONTEND" && ./node_modules/.bin/tsc --noEmit )
}

gate_build() {
    require_frontend_bin next
    ( cd "$FRONTEND" && ./node_modules/.bin/next build )
}

mode="${1:-full}"
[ $# -gt 0 ] && shift

case "$mode" in
    full)
        echo "verify_report_gate: FULL mode (backend suite, vitest, typecheck, production build)"
        run_gate "backend: pytest tests (full suite)" gate_backend
        run_gate "frontend: vitest run" gate_vitest
        run_gate "frontend: tsc --noEmit" gate_types
        run_gate "frontend: next production build" gate_build
        ;;
    backend)
        echo "verify_report_gate: TARGETED backend gate (pytest)"
        run_gate "backend: pytest (targeted)" gate_backend "$@"
        ;;
    vitest)
        echo "verify_report_gate: TARGETED frontend unit gate (vitest)"
        run_gate "frontend: vitest (targeted)" gate_vitest "$@"
        ;;
    types)
        echo "verify_report_gate: TARGETED typecheck gate (tsc --noEmit)"
        run_gate "frontend: tsc --noEmit" gate_types
        ;;
    build)
        echo "verify_report_gate: TARGETED production build gate (next build)"
        run_gate "frontend: next production build" gate_build
        ;;
    -h|--help|help)
        awk 'NR>1 && /^set -u/{exit} /^#/{print}' "${BASH_SOURCE[0]}"
        ;;
    *)
        echo "usage: scripts/verify_report_gate.sh [full|backend|vitest|types|build] [extra args]" >&2
        exit 2
        ;;
esac

echo "verify_report_gate: all executed gates passed."
