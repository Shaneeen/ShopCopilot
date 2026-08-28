#!/usr/bin/env python3
"""Download and verify the official Track 4 product catalog.

Beginner-friendly usage from the repository root:

    python scripts/download_catalog.py

The script downloads only official participant-kit assets, verifies the
published SHA-256 checksum, decompresses the archive, confirms that it has
50,000 JSONL rows, and installs it as ``data/catalog.jsonl``. It refuses to
overwrite an existing catalog.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_BASE_URL = (
    "https://github.com/TechJam2026/techjam-conversational-search/"
    "releases/download/participant-kit"
)
CATALOG_URL = f"{RELEASE_BASE_URL}/catalog.jsonl.gz"
CHECKSUMS_URL = f"{RELEASE_BASE_URL}/SHA256SUMS"
DOWNLOAD_DIR = REPO_ROOT / "data" / "releases"
ARCHIVE_PATH = DOWNLOAD_DIR / "catalog.jsonl.gz"
CHECKSUMS_PATH = DOWNLOAD_DIR / "SHA256SUMS"
CATALOG_PATH = REPO_ROOT / "data" / "catalog.jsonl"
EXPECTED_ROWS = 50_000
REQUIRED_FIELDS = {"parent_asin", "title", "categories"}


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "NeeShops-setup/1.0"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    print(f"Downloading {destination.name} ...")
    try:
        with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _published_checksum(checksums_path: Path, filename: str) -> str:
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    raise ValueError(f"No checksum for {filename} was found in {checksums_path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _install_catalog(archive_path: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    print("Decompressing catalog ...")
    try:
        with gzip.open(archive_path, "rb") as source, temporary.open("wb") as output:
            shutil.copyfileobj(source, output)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_catalog(path: Path) -> tuple[int, set[str]]:
    row_count = 0
    seen_asins: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on catalog line {line_number}: {exc}") from exc
            missing = REQUIRED_FIELDS - row.keys()
            if missing:
                raise ValueError(
                    f"Catalog line {line_number} is missing required fields: {sorted(missing)}"
                )
            parent_asin = str(row["parent_asin"])
            if parent_asin in seen_asins:
                raise ValueError(f"Duplicate parent_asin on line {line_number}: {parent_asin}")
            seen_asins.add(parent_asin)
            row_count += 1
    return row_count, seen_asins


def main() -> int:
    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10 or newer is required.")
        return 1
    if CATALOG_PATH.exists():
        print(f"Catalog already exists at {CATALOG_PATH}")
        print("Nothing was overwritten. Run scripts/check_readiness.py to validate it.")
        return 0

    try:
        if not CHECKSUMS_PATH.exists():
            _download(CHECKSUMS_URL, CHECKSUMS_PATH)
        if not ARCHIVE_PATH.exists():
            _download(CATALOG_URL, ARCHIVE_PATH)

        expected = _published_checksum(CHECKSUMS_PATH, ARCHIVE_PATH.name)
        actual = _sha256(ARCHIVE_PATH)
        if actual != expected:
            print("ERROR: Catalog checksum does not match the organizer's checksum.")
            print(f"Expected: {expected}")
            print(f"Actual:   {actual}")
            print(f"Delete the bad archive at {ARCHIVE_PATH} and run this command again.")
            return 1
        print(f"Checksum verified: {actual}")

        _install_catalog(ARCHIVE_PATH, CATALOG_PATH)
        row_count, seen_asins = validate_catalog(CATALOG_PATH)
        if row_count != EXPECTED_ROWS:
            print(f"ERROR: Expected {EXPECTED_ROWS:,} catalog rows, found {row_count:,}.")
            print(f"The decompressed file was kept at {CATALOG_PATH} for inspection.")
            return 1

        print(f"Catalog ready: {CATALOG_PATH}")
        print(f"Validated {row_count:,} rows and {len(seen_asins):,} unique parent_asin values.")
        print("Next: python scripts/check_readiness.py")
        return 0
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
