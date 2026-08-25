#!/usr/bin/env python
"""
Resolve a representative photo for each cheese in the V6 catalog via the
public Wikipedia REST/Action APIs (no API key, no scraping -- these are
documented, stable, publicly-supported endpoints). Only Wikimedia Commons /
Wikipedia content is used, which carries genuine open licenses (CC-BY-SA or
public domain) and requires only attribution -- never hotlinks to arbitrary
sites with no redistribution rights.

For each base_cheese_name:
  1. Search Wikipedia for the name (search API, appending "cheese" only when
     the name doesn't already contain it -- a doubled-up query like
     "processed cheese cheese" visibly confuses the search ranking).
  2. Fetch the top result's page summary (REST API) for its thumbnail +
     description + canonical URL.
  3. Sanity-check the result is actually about cheese (the word "cheese" or
     "milk" appears in the extract) before accepting it, and require at
     least one non-trivial word overlap between the query name and the
     resolved title (unless the title came from a verified
     DIRECT_TITLE_OVERRIDES synonym) -- rejects unrelated-but-cheese-related
     false positives.

Writes frontend/src/data/cheese-images.json: { [base_cheese_name]: {
  imageUrl, thumbUrl, title, pageUrl, license } | null }
A null entry means no confident match was found -- the frontend renders a
graceful fallback (no fabricated/guessed image), not a broken link.

Usage: python resolve_cheese_images.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "frontend" / "src" / "data" / "cheese-images.json"
HEADERS = {"User-Agent": "ShelfLifeStudio/1.0 (McGill research platform; cheese-catalog-images)"}
SEARCH_API = "https://en.wikipedia.org/w/api.php"
SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"

# A few names are garbled in the source data or too generic to search
# directly -- clean/skip them explicitly rather than let a bad string leak
# into a search query.
NAME_OVERRIDES: dict[str, str | None] = {
    "regional” cheese": None,  # garbled source value, no clean search term
    "ultrafiltered cheese": None,   # a processing method, not a specific cheese
}

# Cases where the correct Wikipedia title is a known synonym/renaming that
# the word-overlap sanity check below would otherwise (wrongly) reject, or
# where free-text search returned a wrong result on inspection -- bypasses
# search entirely and fetches this exact title. A miss here just falls
# through to "unresolved" (fetch_summary returns None on a 404), never a
# silently wrong photo.
DIRECT_TITLE_OVERRIDES: dict[str, str] = {
    "parmigiano reggiano": "Parmigiano Reggiano",  # search ranked the generic "Parmesan" page first
    "requeijão cream cheese": "Requeijão",  # search matched unrelated "Brunost" (Norwegian brown cheese)
    "processed cheese": "Processed cheese",  # doubled-word query previously matched "Macaroni and cheese"
    "fior di latte": "Mozzarella",  # fior di latte is a genuine fresh-mozzarella variant; word-overlap check would reject it
    "fresh chèvre": "Goat cheese",  # chèvre means goat cheese; word-overlap check would reject it
}


def load_catalog() -> list[str]:
    import pandas as pd

    frames = [
        pd.read_csv(ROOT / "data" / "raw" / f"CHEESE_SHELF_LIFE_V6_{n}_SPECIALIST.csv")
        for n in ("SOFT", "SEMI_HARD", "HARD")
    ]
    names = sorted(pd.concat(frames)["base_cheese_name"].unique().tolist())
    return names


REJECT_TITLE_PREFIXES = ("List of", "Category:", "Wikipedia:", "Talk:")


def _get_with_retry(url: str, params: dict | None = None, max_retries: int = 5) -> requests.Response:
    delay = 2.0
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 429:
            return resp
        time.sleep(delay)
        delay *= 2
    resp.raise_for_status()
    return resp


def search_title(query: str) -> str | None:
    resp = _get_with_retry(
        SEARCH_API,
        params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 3},
    )
    resp.raise_for_status()
    results = resp.json().get("query", {}).get("search", [])
    for r in results:
        title = r["title"]
        if not title.startswith(REJECT_TITLE_PREFIXES):
            return title
    return None


def fetch_summary(title: str) -> dict | None:
    resp = _get_with_retry(SUMMARY_API.format(title=title.replace(" ", "_")))
    if resp.status_code != 200:
        return None
    return resp.json()


STOPWORDS = {"cheese", "type", "fresh", "cream", "soft", "white", "regional", "sterilized", "processed"}


def _significant_words(name: str) -> set[str]:
    return {w for w in name.lower().replace("(", " ").replace(")", " ").replace("-", " ").split() if len(w) > 3 and w not in STOPWORDS}


def resolve_one(name: str) -> dict | None:
    if name in NAME_OVERRIDES and NAME_OVERRIDES[name] is None:
        return None

    if name in DIRECT_TITLE_OVERRIDES:
        title = DIRECT_TITLE_OVERRIDES[name]
        skip_word_check = True
    else:
        # Don't blindly append "cheese" -- if the name already contains it, a
        # doubled-up query ("processed cheese cheese") visibly confuses the
        # search ranking. Search the name as-is first in that case.
        query = name if "cheese" in name.lower() else f"{name} cheese"
        title = search_title(query)
        skip_word_check = False
    if not title:
        return None

    summary = fetch_summary(title)
    if not summary:
        return None
    extract = (summary.get("extract") or "").lower()
    if "cheese" not in extract and "milk" not in extract:
        return None  # sanity check failed -- likely an unrelated disambiguation

    # Word-overlap sanity check: at least one non-trivial word from the
    # query name should appear in the resolved title, unless the name has no
    # significant words at all (e.g. "fresh cheese" -> generic "Cheese" is
    # fine) or the title was a verified DIRECT_TITLE_OVERRIDES synonym.
    # Rejects unrelated-but-cheese-related false positives like
    # "requeijão cream cheese" -> "Brunost" (zero word overlap, before that
    # case got its own override above).
    if not skip_word_check:
        sig_words = _significant_words(name)
        if sig_words:
            title_words = set(title.lower().replace("(", " ").replace(")", " ").split())
            if not (sig_words & title_words):
                return None

    thumb = summary.get("thumbnail") or {}
    original = summary.get("originalimage") or {}
    if not thumb.get("source"):
        return None
    return {
        "imageUrl": original.get("source") or thumb.get("source"),
        "thumbUrl": thumb.get("source"),
        "title": summary.get("title"),
        "pageUrl": summary.get("content_urls", {}).get("desktop", {}).get("page"),
        "license": "Wikipedia / Wikimedia Commons",
    }


def main() -> None:
    names = load_catalog()
    print(f"Resolving images for {len(names)} cheese names via Wikipedia API ...")
    out: dict[str, dict | None] = {}
    resolved, unresolved = 0, 0
    for i, name in enumerate(names, 1):
        try:
            entry = resolve_one(name)
        except requests.RequestException as exc:
            print(f"  [{i}/{len(names)}] {name!r}: request error ({exc}), leaving unresolved")
            entry = None
        out[name] = entry
        if entry:
            resolved += 1
            print(f"  [{i}/{len(names)}] {name!r} -> {entry['title']!r}")
        else:
            unresolved += 1
            print(f"  [{i}/{len(names)}] {name!r} -> no confident match")
        time.sleep(1.2)  # be a polite API client -- the search endpoint 429s aggressively below ~1s

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResolved {resolved}/{len(names)} ({unresolved} unresolved). Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
