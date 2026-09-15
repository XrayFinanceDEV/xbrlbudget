"""Explicit network-only setup, followed by checksum-verified offline extraction.

Package archives and CeTZ's upstream WASM stay in the ignored development cache.
No compilation invokes setup or downloads a package.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def prepare_packages(cache: Path, *, download: bool = False) -> Path:
    manifest = json.loads((HERE / "packages.json").read_text())
    archives = cache / "archives"
    packages = cache / "packages"
    archives.mkdir(parents=True, exist_ok=True)
    for pin in manifest["packages"]:
        filename = f"{pin['name']}-{pin['version']}.tar.gz"
        archive = archives / filename
        if download:
            with urllib.request.urlopen(f"{manifest['registry']}/{filename}", timeout=30) as response:
                data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024:
                raise ValueError(f"oversized package: {filename}")
        else:
            data = archive.read_bytes()
        if hashlib.sha256(data).hexdigest() != pin["sha256"]:
            raise ValueError(f"package checksum mismatch: {filename}")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            members = tar.getmembers()
            if any(m.name.startswith("/") or ".." in m.name.split("/")
                   or not (m.isfile() or m.isdir()) for m in members):
                raise ValueError(f"unsafe package archive: {filename}")
            target = packages / "preview" / pin["name"] / pin["version"]
            target.mkdir(parents=True, exist_ok=True)
            # Fresh extraction on each run makes the verified archive authoritative.
            import shutil
            shutil.rmtree(target)
            target.mkdir(parents=True)
            tar.extractall(target, members=members, filter="data")
        if download:
            archive.write_bytes(data)
    return packages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="explicitly fetch pinned registry archives")
    parser.add_argument("--cache", type=Path, default=HERE / ".packages")
    args = parser.parse_args()
    print(prepare_packages(args.cache, download=args.download))
