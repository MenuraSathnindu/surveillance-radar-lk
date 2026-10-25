"""Polite PDF downloader: crawl listing pages, keep originals, record a manifest.

Usage:
    python -m radar_lk.ingest.download --source wer --years 2022-2026
    python -m radar_lk.ingest.download --source ndcu_weekly --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from radar_lk import RAW_DIR, load_config

MANIFEST = RAW_DIR / "manifest.csv"
MANIFEST_FIELDS = ["source", "url", "file", "sha256", "bytes", "downloaded_at", "listing_url"]


class Fetcher:
    def __init__(self, user_agent: str, delay: float):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.delay = delay
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last = 0.0

    def allowed(self, url: str) -> bool:
        root = "{0.scheme}://{0.netloc}".format(urlparse(url))
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None  # robots.txt unreachable: treat as allowed, but log it
                print(f"[warn] could not read {root}/robots.txt")
            self._robots[root] = rp
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(self.session.headers["User-Agent"], url)

    def get(self, url: str) -> requests.Response:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        resp = self.session.get(url, timeout=60)
        self._last = time.monotonic()
        resp.raise_for_status()
        return resp


def find_pdf_links(html: str, base_url: str, pdf_regex: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    pat = re.compile(pdf_regex)
    links = []
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"].strip())
        if pat.search(urlparse(url).path) and url not in links:
            links.append(url)
    return links


def load_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return {row["url"]: row for row in csv.DictReader(f)}


def append_manifest(row: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def safe_name(url: str) -> str:
    name = Path(urlparse(url).path).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def year_filter(url: str, years: range | None) -> bool:
    """Keep a link if it mentions a wanted year, or if no year can be read from it.

    WER volume -> year: Vol 49 = 2022 ... Vol 53 = 2026 (vol = year - 1973).
    """
    if years is None:
        return True
    m = re.search(r"vol[_\s-]*(\d{2})", url, re.I)
    if m:
        return int(m.group(1)) + 1973 in years
    m = re.search(r"(20\d{2})", url)
    return int(m.group(1)) in years if m else True


def run(source: str, years: range | None, dry_run: bool) -> None:
    cfg = load_config()
    src = cfg["sources"][source]
    if not src["listing_urls"]:
        raise SystemExit(
            f"No listing_urls set for '{source}' in config/sources.yaml. "
            "Open the site in a browser, find the archive page, and paste its URL there."
        )
    fetcher = Fetcher(cfg["user_agent"], cfg["request_delay_seconds"])
    seen = load_manifest()
    out_dir = RAW_DIR / source
    out_dir.mkdir(parents=True, exist_ok=True)

    english = re.compile(src["english_only_regex"]) if src.get("english_only_regex") else None
    n_new = 0
    for listing in src["listing_urls"]:
        links = find_pdf_links(fetcher.get(listing).text, listing, src["pdf_link_regex"])
        links = [u for u in links if year_filter(u, years)]
        if english:
            links = [u for u in links if english.search(u)]
        print(f"{listing}: {len(links)} candidate PDFs")
        for url in links:
            if url in seen:
                continue
            target = out_dir / safe_name(url)
            if dry_run:
                print("  would get", url)
                continue
            try:
                data = fetcher.get(url).content
            except Exception as e:  # keep going; failures are reported, not fatal
                print(f"  [fail] {url}: {e}")
                continue
            if not data.startswith(b"%PDF"):
                print(f"  [skip] not a PDF: {url}")
                continue
            target.write_bytes(data)
            row = {
                "source": source,
                "url": url,
                "file": str(target.relative_to(RAW_DIR)),
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "listing_url": listing,
            }
            append_manifest(row)
            seen[url] = row
            n_new += 1
            print("  got", target.name)
    print(f"done: {n_new} new file(s)")


def parse_years(s: str | None) -> range | None:
    if not s:
        return None
    a, _, b = s.partition("-")
    return range(int(a), int(b or a) + 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--source", required=True, choices=["wer", "ndcu_weekly", "ndcu_daily"])
    p.add_argument("--years", help="e.g. 2022-2026")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    run(a.source, parse_years(a.years), a.dry_run)


if __name__ == "__main__":
    main()
