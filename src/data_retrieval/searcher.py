"""
Stage 1: Literature search via Semantic Scholar (with PubMed fallback) and PDF download.

Entry point: run_search(matrix, config_path, output_dir, api_key) -> list[Path]
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

_SS_BASE = "https://api.semanticscholar.org/graph/v1"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_search_config(config_path: Path, matrix: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if matrix not in cfg:
        raise KeyError(f"Matrix '{matrix}' not found in {config_path}")
    return cfg[matrix]


def build_queries(search_config: dict) -> list[str]:
    """Cross-product keywords × query_templates, deduplicated."""
    keywords = search_config.get("keywords", [])
    templates = search_config.get("query_templates", ["{keyword}"])
    seen: set[str] = set()
    queries: list[str] = []
    for kw in keywords:
        for tpl in templates:
            q = tpl.format(keyword=kw)
            if q not in seen:
                seen.add(q)
                queries.append(q)
    return queries


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------

def search_semantic_scholar(
    query: str,
    params: dict,
    api_key: str | None = None,
) -> list[dict]:
    """Return papers that have an open-access PDF URL."""
    ss_cfg = params.get("semantic_scholar", {})
    base_url = ss_cfg.get("base_url", _SS_BASE)
    endpoint = ss_cfg.get("paper_search_endpoint", "/paper/search")
    fields = ss_cfg.get("fields", "title,authors,year,externalIds,openAccessPdf")
    min_year = params.get("min_year", 2000)
    max_results = params.get("max_results_per_query", 20)

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    resp = requests.get(
        f"{base_url}{endpoint}",
        params={
            "query": query,
            "fields": fields,
            "limit": max_results,
            "year": f"{min_year}-",
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    papers = []
    for p in data.get("data", []):
        if params.get("open_access_only", True) and not p.get("openAccessPdf"):
            continue
        papers.append(p)
    return papers


# ---------------------------------------------------------------------------
# PubMed fallback (requires biopython)
# ---------------------------------------------------------------------------

def search_pubmed(query: str, params: dict) -> list[dict]:
    try:
        from Bio import Entrez
    except ImportError:
        return []

    pm_cfg = params.get("pubmed", {})
    Entrez.email = pm_cfg.get("email", "user@example.com")
    handle = Entrez.esearch(
        db=pm_cfg.get("db", "pubmed"),
        term=query,
        retmax=pm_cfg.get("retmax", 20),
        sort=pm_cfg.get("sort", "relevance"),
    )
    record = Entrez.read(handle)
    handle.close()

    ids = record.get("IdList", [])
    if not ids:
        return []

    fetch_handle = Entrez.efetch(db="pubmed", id=",".join(ids), rettype="xml", retmode="xml")
    records = Entrez.read(fetch_handle)
    fetch_handle.close()

    papers = []
    for article in records.get("PubmedArticle", []):
        try:
            medline = article["MedlineCitation"]
            art = medline["Article"]
            title = str(art.get("ArticleTitle", ""))
            year_str = str(
                art.get("Journal", {})
                .get("JournalIssue", {})
                .get("PubDate", {})
                .get("Year", "")
            )
            authors_list = art.get("AuthorList", [])
            authors = [
                f"{a.get('LastName', '')} {a.get('ForeName', '')}".strip()
                for a in authors_list
                if isinstance(a, dict)
            ]
            ids_obj = medline.get("PMID", "")
            papers.append({
                "title": title,
                "authors": [{"name": a} for a in authors],
                "year": int(year_str) if year_str.isdigit() else None,
                "externalIds": {"PubMed": str(ids_obj)},
                "openAccessPdf": None,  # PubMed doesn't supply PDF URLs directly
            })
        except (KeyError, TypeError):
            continue
    return papers


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_pdf(pdf_url: str, dest_path: Path, dl_params: dict) -> bool:
    timeout = dl_params.get("timeout_seconds", 30)
    retries = dl_params.get("retry_attempts", 2)
    chunk_size = dl_params.get("chunk_size_bytes", 8192)

    for attempt in range(retries + 1):
        try:
            resp = requests.get(pdf_url, timeout=timeout, stream=True)
            resp.raise_for_status()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
            return True
        except requests.RequestException as exc:
            if attempt == retries:
                print(f"  [download] Failed after {retries+1} attempts: {exc}")
            else:
                time.sleep(1)
    return False


def save_metadata_sidecar(paper: dict, sidecar_path: Path) -> None:
    authors = paper.get("authors") or []
    author_names = [a.get("name", "") for a in authors if isinstance(a, dict)]
    ext_ids = paper.get("externalIds") or {}
    meta = {
        "title": paper.get("title", ""),
        "authors": author_names,
        "year": paper.get("year"),
        "doi": ext_ids.get("DOI"),
        "semantic_scholar_id": paper.get("paperId"),
    }
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_search(
    matrix: str,
    config_path: Path,
    output_dir: Path,
    api_key: str | None = None,
) -> list[Path]:
    """
    Execute full Stage 1.

    Returns list of successfully downloaded PDF paths.
    """
    search_cfg = load_search_config(config_path, matrix)
    params = search_cfg.get("retrieval_params", {})
    dl_params = params.get("download", {})
    ss_params = params.get("semantic_scholar", {})
    rate_delay = ss_params.get("rate_limit_delay_seconds", 1.0)
    source = params.get("source", "semantic_scholar")

    queries = build_queries(search_cfg)
    print(f"[searcher] {len(queries)} queries generated for matrix '{matrix}'")

    # Collect papers, deduplicating by DOI
    seen_dois: set[str] = set()
    all_papers: list[dict] = []

    for i, query in enumerate(queries):
        try:
            if source == "semantic_scholar":
                papers = search_semantic_scholar(query, params, api_key)
            else:
                papers = search_pubmed(query, params)
        except Exception as exc:
            print(f"  [searcher] Query {i+1}/{len(queries)} failed: {exc}")
            papers = []

        for p in papers:
            ext_ids = p.get("externalIds") or {}
            doi = ext_ids.get("DOI")
            key = doi or p.get("paperId") or p.get("title", "")
            if key and key not in seen_dois:
                seen_dois.add(key)
                all_papers.append(p)

        time.sleep(rate_delay)
        print(f"  [searcher] Query {i+1}/{len(queries)}: +{len(papers)} papers (total unique: {len(all_papers)})")

    print(f"[searcher] {len(all_papers)} unique open-access papers found")

    # Download PDFs
    output_dir.mkdir(parents=True, exist_ok=True)
    meta_dir = output_dir / "metadata"
    meta_dir.mkdir(exist_ok=True)

    downloaded: list[Path] = []
    for idx, paper in enumerate(all_papers):
        oa = paper.get("openAccessPdf")
        if not oa:
            continue
        pdf_url = oa.get("url") if isinstance(oa, dict) else str(oa)
        if not pdf_url:
            continue

        safe_title = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in (paper.get("title") or f"paper_{idx}")[:60]
        )
        pdf_path = output_dir / f"{safe_title}.pdf"
        sidecar_path = meta_dir / f"{safe_title}.json"

        if pdf_path.exists():
            print(f"  [download] Already exists: {pdf_path.name}")
            downloaded.append(pdf_path)
            continue

        print(f"  [download] {pdf_path.name} ...")
        if download_pdf(pdf_url, pdf_path, dl_params):
            save_metadata_sidecar(paper, sidecar_path)
            downloaded.append(pdf_path)

    print(f"[searcher] {len(downloaded)} PDFs downloaded to {output_dir}")
    return downloaded
