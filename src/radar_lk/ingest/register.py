"""Register PDFs dropped manually into data/raw/<source>/ in the manifest.

Usage:
    python -m radar_lk.ingest.register --source wer
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from radar_lk import RAW_DIR
from radar_lk.ingest import download


def register(source: str, raw_dir: Path = RAW_DIR) -> list[str]:
    """Add unregistered PDFs under raw_dir/source to the manifest; return the files added."""
    rows = download.load_manifest().values()
    known_files = {r["file"] for r in rows}
    known_hashes = {r["sha256"] for r in rows}
    added = []
    for path in sorted((raw_dir / source).glob("*.pdf")):
        rel = path.relative_to(raw_dir).as_posix()
        if rel in known_files:
            continue
        data = path.read_bytes()
        if not data.startswith(b"%PDF"):
            print(f"  [skip] not a PDF: {rel}")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in known_hashes:
            print(f"  [skip] same content already in manifest: {rel}")
            continue
        download.append_manifest(
            {
                "source": source,
                "url": f"manual://{rel}",
                "file": rel,
                "sha256": digest,
                "bytes": len(data),
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "listing_url": "manual",
            }
        )
        known_hashes.add(digest)
        added.append(rel)
        print("  registered", rel)
    print(f"done: {len(added)} file(s) registered")
    return added


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--source", required=True, choices=["wer", "ndcu_weekly", "ndcu_daily"])
    a = p.parse_args()
    register(a.source)


if __name__ == "__main__":
    main()
