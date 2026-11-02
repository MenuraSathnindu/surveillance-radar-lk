"""Polite PDF downloader: crawl listing pages, keep originals, record a manifest.

Usage:
    python -m radar_lk.ingest.download --source wer --years 2022-2026 --dry-run
    python -m radar_lk.ingest.download --source wer --years 2022-2026
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import time
import urllib.robotparser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from radar_lk import RAW_DIR, load_config

MANIFEST = RAW_DIR / "manifest.csv"
MANIFEST_FIELDS = ["source", "url", "file", "sha256", "bytes", "downloaded_at", "listing_url"]
MAX_CONSECUTIVE_FAILURES = 5  # the server has a bandwidth cap; stop rather than hammer it
NON_ENGLISH = re.compile(r"(?i)sinhala|tamil")


class Fetcher:
    def __init__(self, user_agent: str, delay: float):
        self.session = requests.Session()
        # Honest, identifying bot UA plus ordinary Accept headers; no browser impersonation.
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.delay = delay
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last = 0.0

    def _wait(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

    def _robots_for(self, root: str) -> urllib.robotparser.RobotFileParser:
        """Fetch robots.txt with our own session (urllib's default UA gets 403 on some hosts).

        200 -> parse. 404 -> no rules. Anything else -> treat as disallowed, never as a green light.
        """
        if root in self._robots:
            return self._robots[root]
        rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
        self._wait()
        try:
            resp = self.session.get(root + "/robots.txt", timeout=60)
        except requests.RequestException as e:
            print(f"[warn] could not read {root}/robots.txt ({e}); treating as disallowed")
            rp.disallow_all = True
        else:
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            elif resp.status_code == 404:
                rp.allow_all = True
            else:
                print(f"[warn] {root}/robots.txt returned {resp.status_code}; treating as disallowed")
                rp.disallow_all = True
        self._last = time.monotonic()
        self._robots[root] = rp
        return rp

    def allowed(self, url: str) -> bool:
        root = "{0.scheme}://{0.netloc}".format(urlparse(url))
        return self._robots_for(root).can_fetch(self.session.headers["User-Agent"], url)

    def get(self, url: str) -> requests.Response:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt disallows {url}")
        self._wait()
        try:
            resp = self.session.get(url, timeout=60)
        finally:
            self._last = time.monotonic()
        resp.raise_for_status()
        return resp


class Link(NamedTuple):
    url: str
    text: str  # visible text of the listing entry that holds the link (title, week, date range)


def find_pdf_items(html: str, base_url: str, pdf_regex: str) -> list[Link]:
    """PDF links plus the text of the listing entry around each.

    The context is the largest ancestor that still holds exactly one matching link, so a
    listing row (title, "Week 34", "2026.08.15 - 2026.08.21") is read but never its neighbours.
    """
    soup = BeautifulSoup(html, "html.parser")
    pat = re.compile(pdf_regex)

    def matches(a) -> bool:
        return bool(pat.search(urlparse(urljoin(base_url, a["href"].strip())).path))

    items: list[Link] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        if not matches(a):
            continue
        url = urljoin(base_url, a["href"].strip())
        if url in seen:
            continue
        seen.add(url)
        node = a
        for _ in range(4):
            parent = node.parent
            if parent is None or parent.name in ("body", "html", "[document]"):
                break
            if sum(1 for x in parent.find_all("a", href=True) if matches(x)) != 1:
                break
            node = parent
        items.append(Link(url, node.get_text(" ", strip=True)))
    return items


def find_pdf_links(html: str, base_url: str, pdf_regex: str) -> list[str]:
    return [i.url for i in find_pdf_items(html, base_url, pdf_regex)]


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


_VOL = re.compile(r"vol(?:ume)?[\s._-]*(\d{2})(?!\d)", re.I)
_DATE_YMD = re.compile(r"(?<!\d)(20\d{2})[./-]\d{1,2}[./-]\d{1,2}(?!\d)")
_DATE_DMY = re.compile(r"(?<!\d)\d{1,2}[./-]\d{1,2}[./-](20\d{2})(?!\d)")


def link_years(url: str, text: str = "") -> tuple[int | None, set[int]]:
    """(best-guess year, every year the evidence points to).

    WER volume -> year: vol = year - 1973 (Vol 49 = 2022 ... Vol 53 = 2026). From the text only
    dates and "Vol NN" are read, not bare 4-digit numbers, because issue titles mention other
    years ("Immunization survey 2025"). Text is tried before the URL. A week that straddles
    New Year yields two years; both count as evidence so it is not dropped.
    """
    vol_years = [int(m.group(1)) + 1973 for src in (text, url) for m in _VOL.finditer(src)]
    date_years = [int(m.group(1)) for rx in (_DATE_YMD, _DATE_DMY) for m in rx.finditer(text)]
    url_years = [int(m) for m in re.findall(r"(?<!\d)(20\d{2})(?!\d)", url)]
    evidence = set(vol_years) | set(date_years) | set(url_years)
    best = (vol_years or date_years[-1:] or url_years or [None])[0]
    return best, evidence


def year_filter(url: str, years: range | None, text: str = "") -> bool:
    """Keep a link if any evidence points at a wanted year, or if no year can be read."""
    if years is None:
        return True
    _, evidence = link_years(url, text)
    return not evidence or any(y in years for y in evidence)


def select_candidates(
    html: str, listing: str, src: dict, years: range | None
) -> tuple[list[Link], list[Link]]:
    """(links to consider, the subset whose year could not be read)."""
    items = find_pdf_items(html, listing, src["pdf_link_regex"])
    items = [i for i in items if not NON_ENGLISH.search(i.url)]
    if src.get("english_only_regex"):
        english = re.compile(src["english_only_regex"])
        items = [i for i in items if english.search(i.url)]
    items = [i for i in items if year_filter(i.url, years, i.text)]
    unknown = [i for i in items if not link_years(i.url, i.text)[1]]
    return items, unknown


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

    n_new = 0
    failures = 0  # consecutive
    for listing in src["listing_urls"]:
        try:
            html = fetcher.get(listing).text
        except Exception as e:
            raise SystemExit(f"[stop] could not fetch listing {listing}: {e}")
        links, unknown = select_candidates(html, listing, src, years)
        per_year = Counter(link_years(i.url, i.text)[0] for i in links)
        print(f"{listing}: {len(links)} candidate PDFs")
        for y in sorted(k for k in per_year if k is not None):
            print(f"  {y}: {per_year[y]}")
        print(f"  year unknown: {len(unknown)}")
        for i in unknown:
            print(f"    ? {i.url}  [{i.text[:60]}]")
        todo = [i for i in links if i.url not in seen]
        print(f"  already in manifest: {len(links) - len(todo)}; to download: {len(todo)}")
        if dry_run:
            for i in todo:
                print("  would get", i.url)
            continue
        for i in todo:
            url = i.url
            target = out_dir / safe_name(url)
            try:
                data = fetcher.get(url).content
                if not data.startswith(b"%PDF"):
                    raise ValueError("response is not a PDF")
            except Exception as e:  # keep going, but never hammer a struggling server
                failures += 1
                print(f"  [fail {failures}/{MAX_CONSECUTIVE_FAILURES}] {url}: {e}")
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    raise SystemExit(
                        f"[stop] {failures} consecutive failures; the server may be rate-limiting "
                        f"or down. {n_new} file(s) saved so far. Re-run later; the manifest "
                        "skips what is already downloaded."
                    )
                continue
            failures = 0
            target.write_bytes(data)
            row = {
                "source": source,
                "url": url,
                "file": target.relative_to(RAW_DIR).as_posix(),
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
