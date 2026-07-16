"""Build the deterministic, API-free manifest for the local import corpus.

The manifest identifies documents by SHA-256, retains every path alias and keeps
manually verified source truth separate from parser output. It deliberately does
not import application parsers and never calls OCR/LLM services.

Usage::

    python tests/corpus/build_manifest.py
    python tests/corpus/build_manifest.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
TEST_ROOT = ROOT / "Test"
ANALYSIS_ROOT = TEST_ROOT / "_analysis"
CORPUS_FIXTURES_ROOT = Path(__file__).resolve().parent
TRUTH_PATH = CORPUS_FIXTURES_ROOT / "truth.json"
MANIFEST_PATH = CORPUS_FIXTURES_ROOT / "manifest.json"
SUPPORTED_SUFFIXES = {".pdf", ".xbrl", ".xml", ".csv"}


def _posix_relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_source_files(test_root: Path) -> Iterable[Path]:
    for path in sorted(test_root.rglob("*"), key=lambda value: value.as_posix().casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative_parts = path.relative_to(test_root).parts
        if "_analysis" in relative_parts or "july_budget" in relative_parts:
            continue
        yield path


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _classification_by_name(analysis_root: Path) -> dict[str, dict[str, Any]]:
    """Return the frozen human classification, when one already exists.

    This metadata is descriptive only. It is never inferred from current parser
    output, so a parser change cannot silently rewrite the expected route.
    """

    records = _load_json(analysis_root / "classifications.json", [])
    return {record["key"].casefold(): record for record in records if record.get("key")}


def _classification_key(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename).casefold()


def _route_metadata(
    paths: list[Path], suffix: str, classifications: dict[str, dict[str, Any]]
) -> tuple[str, str | None]:
    if suffix in {".xbrl", ".xml"}:
        return "xbrl", "native_xbrl"
    if suffix == ".csv":
        return "csv", None

    matches = [
        classifications[_classification_key(path.name)]
        for path in paths
        if _classification_key(path.name) in classifications
    ]
    areas = {record.get("area") for record in matches}
    route = (
        "trial_balance"
        if areas == {"C"}
        else "ivcee"
        if areas and areas <= {"A", "B"}
        else "unsupported"
        if areas == {"OTHER"}
        else "unknown"
    )
    subtypes = sorted(
        {record.get("subcategory") for record in matches if record.get("subcategory")}
    )
    return route, " | ".join(subtypes) if subtypes else None


def build_manifest(
    test_root: Path = TEST_ROOT,
    analysis_root: Path = ANALYSIS_ROOT,
    truth_path: Path | None = None,
) -> dict[str, Any]:
    truth_doc = _load_json(truth_path or TRUTH_PATH, {"records": {}})
    truth_by_hash = truth_doc.get("records", {})
    classifications = _classification_by_name(analysis_root)

    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in _iter_source_files(test_root):
        by_hash[_sha256(path)].append(path)

    records: list[dict[str, Any]] = []
    for digest, paths in sorted(by_hash.items()):
        paths = sorted(paths, key=lambda value: _posix_relative(value, test_root).casefold())
        suffix = paths[0].suffix.lower()
        route, subtype = _route_metadata(paths, suffix, classifications)
        truth = truth_by_hash.get(digest)
        if truth:
            route = truth.get("route_expected", route)
            subtype = truth.get("subtype", subtype)

        record: dict[str, Any] = {
            "sha256": digest,
            "paths": [_posix_relative(path, test_root) for path in paths],
            "format": suffix.lstrip("."),
            "size_bytes": paths[0].stat().st_size,
            "route_expected": route,
            "subtype": subtype,
            "status": truth.get("status", "open") if truth else "open",
        }
        if truth:
            record["truth"] = {
                key: value
                for key, value in truth.items()
                if key not in {"route_expected", "subtype", "status"}
            }
        records.append(record)

    formats = Counter(record["format"] for record in records)
    routes = Counter(record["route_expected"] for record in records)
    present_hashes = set(by_hash)
    return {
        "schema_version": 1,
        "hash_algorithm": "sha256",
        "scope": "Test/**/*.(pdf|xbrl|xml|csv), excluding Test/_analysis",
        "summary": {
            "physical_files": sum(len(record["paths"]) for record in records),
            "unique_contents": len(records),
            "formats": dict(sorted(formats.items())),
            "routes": dict(sorted(routes.items())),
            "verified": sum(record["status"] == "verified" for record in records),
            "truth_orphans": sorted(set(truth_by_hash) - present_hashes),
        },
        "files": records,
    }


def _render(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the committed manifest is stale")
    parser.add_argument("--output", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()

    rendered = _render(build_manifest())
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(f"STALE: regenerate {args.output.relative_to(ROOT)}")
            return 1
        print(f"OK: {args.output.relative_to(ROOT)} is reproducible")
        return 0

    args.output.write_text(rendered, encoding="utf-8")
    manifest = json.loads(rendered)
    summary = manifest["summary"]
    print(
        f"wrote {args.output.relative_to(ROOT)}: "
        f"{summary['unique_contents']} unique / {summary['physical_files']} physical"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
