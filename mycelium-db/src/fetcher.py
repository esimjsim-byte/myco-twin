"""NCBI Entrez API wrapper.

Fetches PubMed / PMC records related to mushroom mycelium cultivation
(carbon sources, nitrogen sources, biomass yields, β-glucan content, etc.)
using Biopython's Entrez module plus a small JATS-XML parser for PMC
full-texts.

Typical pipeline::

    pmids = search_pubmed("Ganoderma lucidum beta-glucan", max_results=20)
    records = fetch_abstracts(pmids)
    for rec in records:
        if rec["pmcid"]:
            fulltext = fetch_pmc_fulltext(rec["pmcid"])

Environment variables (loaded via ``python-dotenv``):

* ``NCBI_EMAIL``   — required by NCBI's usage policy.
* ``NCBI_API_KEY`` — optional; raises the per-second rate limit from 3 to 10.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.error import HTTPError, URLError

import requests
from Bio import Entrez
from dotenv import load_dotenv
from lxml import etree

load_dotenv()

_logger = logging.getLogger(__name__)

_NCBI_EMAIL = os.getenv("NCBI_EMAIL")
_NCBI_API_KEY = os.getenv("NCBI_API_KEY")

if _NCBI_EMAIL:
    Entrez.email = _NCBI_EMAIL
if _NCBI_API_KEY:
    Entrez.api_key = _NCBI_API_KEY

_RATE_LIMIT_SECONDS: float = 0.1 if _NCBI_API_KEY else 0.34
_MAX_RETRIES: int = 3
_ID_CONVERTER_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_HTTP_TIMEOUT = 30

T = TypeVar("T")


def _throttle() -> None:
    """Sleep long enough to respect NCBI's per-second request cap."""
    time.sleep(_RATE_LIMIT_SECONDS)


def _with_retry(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call ``func`` with exponential backoff on transient network errors.

    Retries up to ``_MAX_RETRIES`` times on ``HTTPError``, ``URLError``,
    ``requests.RequestException`` and generic ``OSError``. Non-transient
    errors (e.g. ``ValueError``) propagate immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except (HTTPError, URLError, requests.RequestException, OSError) as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES - 1:
                break
            backoff = 2 ** attempt
            _logger.warning(
                "transient error on attempt %d/%d, sleeping %ds: %s",
                attempt + 1, _MAX_RETRIES, backoff, exc,
            )
            time.sleep(backoff)
    assert last_exc is not None
    raise last_exc


def _require_email() -> None:
    """Fail fast with a helpful message if ``NCBI_EMAIL`` is unset."""
    if not _NCBI_EMAIL:
        raise RuntimeError(
            "NCBI_EMAIL is not set. Copy .env.example to .env and fill it in, "
            "or export NCBI_EMAIL=you@example.com before running."
        )


def search_pubmed(
    query: str,
    max_results: int = 50,
    min_year: int | None = None,
) -> list[str]:
    """Search PubMed and return matching PMIDs.

    Args:
        query: A PubMed query string (supports PubMed's field tags).
        max_results: Maximum number of PMIDs to return.
        min_year: If given, restricts results to articles published on or
            after this calendar year using the ``[dp]`` (date of publication)
            field.

    Returns:
        A list of PMID strings (possibly empty). Ordering follows PubMed's
        default relevance sort.
    """
    _require_email()
    if min_year is not None:
        full_query = f"({query}) AND {min_year}:3000[dp]"
    else:
        full_query = query

    _logger.info("esearch db=pubmed term=%r retmax=%d", full_query, max_results)
    _throttle()
    handle = _with_retry(
        Entrez.esearch, db="pubmed", term=full_query, retmax=max_results
    )
    try:
        record = Entrez.read(handle)
    finally:
        handle.close()
    pmids = list(record.get("IdList", []))
    _logger.info("esearch returned %d PMID(s)", len(pmids))
    return pmids


def _text(node: etree._Element | None) -> str:
    """Return the concatenated, stripped text of an element, or ``""``."""
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _parse_pubmed_article(article: etree._Element) -> dict[str, Any]:
    """Extract a record dict from a single ``<PubmedArticle>`` element."""
    pmid = _text(article.find(".//MedlineCitation/PMID"))
    title = _text(article.find(".//Article/ArticleTitle"))

    abstract_parts: list[str] = []
    for ab in article.findall(".//Article/Abstract/AbstractText"):
        label = ab.get("Label")
        text = _text(ab)
        abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(p for p in abstract_parts if p)

    authors: list[str] = []
    for au in article.findall(".//Article/AuthorList/Author"):
        last = _text(au.find("LastName"))
        fore = _text(au.find("ForeName"))
        collective = _text(au.find("CollectiveName"))
        if last or fore:
            authors.append(f"{fore} {last}".strip())
        elif collective:
            authors.append(collective)

    journal = _text(article.find(".//Article/Journal/ISOAbbreviation"))
    if not journal:
        journal = _text(article.find(".//Article/Journal/Title"))

    year = _text(article.find(".//Article/Journal/JournalIssue/PubDate/Year"))
    if not year:
        medline_date = _text(article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate"))
        if medline_date:
            year = medline_date[:4]

    mesh_terms = [
        _text(mh.find("DescriptorName"))
        for mh in article.findall(".//MeshHeadingList/MeshHeading")
    ]
    mesh_terms = [m for m in mesh_terms if m]

    pub_types = [
        _text(pt) for pt in article.findall(".//Article/PublicationTypeList/PublicationType")
    ]
    pub_types = [p for p in pub_types if p]

    doi = ""
    pmcid = ""
    for aid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        id_type = aid.get("IdType", "").lower()
        value = _text(aid)
        if id_type == "doi":
            doi = value
        elif id_type == "pmc":
            pmcid = value if value.upper().startswith("PMC") else f"PMC{value}"

    return {
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal,
        "year": year,
        "mesh_terms": mesh_terms,
        "publication_types": pub_types,
    }


def fetch_abstracts(pmids: list[str]) -> list[dict[str, Any]]:
    """Fetch abstracts and metadata for a list of PMIDs.

    Args:
        pmids: PubMed IDs to retrieve.

    Returns:
        One dict per successfully parsed article with keys ``pmid``,
        ``pmcid``, ``doi``, ``title``, ``abstract``, ``authors``,
        ``journal``, ``year``, ``mesh_terms``, ``publication_types``.
        PMIDs that fail to parse are logged as warnings and skipped.
    """
    _require_email()
    if not pmids:
        return []

    _logger.info("efetch db=pubmed ids=%d", len(pmids))
    _throttle()
    try:
        handle = _with_retry(
            Entrez.efetch,
            db="pubmed",
            id=",".join(pmids),
            rettype="abstract",
            retmode="xml",
        )
    except Exception as exc:
        _logger.warning("efetch failed for %d PMIDs: %s", len(pmids), exc)
        return []

    try:
        data = handle.read()
    finally:
        handle.close()

    if isinstance(data, str):
        data = data.encode()

    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        _logger.warning("failed to parse PubMed XML: %s", exc)
        return []

    records: list[dict[str, Any]] = []
    for article in root.findall(".//PubmedArticle"):
        try:
            records.append(_parse_pubmed_article(article))
        except Exception as exc:
            pmid_fallback = _text(article.find(".//MedlineCitation/PMID"))
            _logger.warning("failed to parse article PMID=%s: %s", pmid_fallback, exc)
    _logger.info("parsed %d/%d PubMed records", len(records), len(pmids))
    return records


def get_pmc_id_from_pmid(pmid: str) -> str | None:
    """Resolve a PMID to its PMCID via NCBI's ID Converter API.

    Args:
        pmid: A PubMed ID (digits only, as a string).

    Returns:
        The PMCID (``"PMC1234567"``) if the article is deposited in PMC,
        else ``None``. Network or parsing failures are logged and return
        ``None``.
    """
    params: dict[str, str] = {
        "ids": str(pmid),
        "format": "json",
        "tool": "mycelium-db",
    }
    if _NCBI_EMAIL:
        params["email"] = _NCBI_EMAIL
    _throttle()
    try:
        resp = _with_retry(
            requests.get, _ID_CONVERTER_URL, params=params, timeout=_HTTP_TIMEOUT
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        _logger.warning("id-converter failed for PMID=%s: %s", pmid, exc)
        return None

    for rec in payload.get("records", []):
        pmcid = rec.get("pmcid")
        if pmcid:
            return pmcid
    return None


_SECTION_ALIASES: dict[str, str] = {
    "intro": "intro",
    "introduction": "intro",
    "background": "intro",
    "methods": "methods",
    "materials|methods": "methods",
    "materials and methods": "methods",
    "materials-and-methods": "methods",
    "experimental": "methods",
    "results": "results",
    "results and discussion": "results",
    "discussion": "discussion",
    "conclusion": "discussion",
    "conclusions": "discussion",
}


def _classify_section(sec_type: str, title: str) -> str | None:
    """Map a JATS section's ``sec-type`` or title to a canonical bucket."""
    for key in (sec_type.lower().strip(), title.lower().strip()):
        if not key:
            continue
        if key in _SECTION_ALIASES:
            return _SECTION_ALIASES[key]
        for alias, canonical in _SECTION_ALIASES.items():
            if key.startswith(alias):
                return canonical
    return None


def _extract_sections(root: etree._Element) -> dict[str, str]:
    """Group top-level ``<sec>`` elements into intro/methods/results/discussion."""
    buckets: dict[str, list[str]] = {
        "intro": [], "methods": [], "results": [], "discussion": [],
    }
    body = root.find(".//body")
    if body is None:
        return {k: "" for k in buckets}

    for sec in body.findall("./sec"):
        sec_type = sec.get("sec-type", "")
        title = _text(sec.find("./title"))
        bucket = _classify_section(sec_type, title)
        if bucket is None:
            continue
        paragraphs = sec.xpath(
            ".//p[not(ancestor::table-wrap) and not(ancestor::caption)"
            " and not(ancestor::fig) and not(ancestor::boxed-text)]"
        )
        text = "\n\n".join(t for t in (_text(p) for p in paragraphs) if t)
        if text:
            buckets[bucket].append(text)

    return {k: "\n\n".join(v) for k, v in buckets.items()}


def _parse_table_row(tr: etree._Element) -> list[str]:
    """Return the text of each ``<th>``/``<td>`` cell in one row."""
    cells: list[str] = []
    for cell in tr.findall("./th") + tr.findall("./td"):
        cells.append(_text(cell))
    return cells


def _extract_tables(root: etree._Element) -> list[dict[str, Any]]:
    """Extract every ``<table-wrap>`` as ``{"caption", "headers", "rows"}``."""
    tables: list[dict[str, Any]] = []
    for tw in root.findall(".//table-wrap"):
        label = _text(tw.find("./label"))
        caption = _text(tw.find("./caption"))
        full_caption = " ".join(p for p in (label, caption) if p).strip()

        headers: list[list[str]] = []
        rows: list[list[str]] = []
        for table in tw.findall(".//table"):
            for tr in table.findall(".//thead/tr"):
                headers.append(_parse_table_row(tr))
            for tr in table.findall(".//tbody/tr"):
                rows.append(_parse_table_row(tr))
            # Some JATS tables omit thead/tbody; fall back to direct children.
            if not headers and not rows:
                for tr in table.findall("./tr"):
                    rows.append(_parse_table_row(tr))

        tables.append({
            "caption": full_caption,
            "headers": headers,
            "rows": rows,
        })
    return tables


def fetch_pmc_fulltext(pmcid: str) -> dict[str, Any] | None:
    """Download and parse a PMC article's JATS XML full-text.

    Args:
        pmcid: PMC identifier, with or without the ``PMC`` prefix
            (``"PMC1234567"`` and ``"1234567"`` are both accepted).

    Returns:
        Dict with keys ``pmcid``, ``sections``
        (``{"intro", "methods", "results", "discussion"}``), ``tables``
        (list of ``{"caption", "headers", "rows"}``), and ``raw_xml``.
        Returns ``None`` if the article isn't in PMC, the fetch fails,
        or the response isn't parseable XML.
    """
    _require_email()
    canonical = pmcid.upper() if pmcid.upper().startswith("PMC") else f"PMC{pmcid}"
    lookup_id = canonical.removeprefix("PMC")

    _logger.info("efetch db=pmc id=%s", canonical)
    _throttle()
    try:
        handle = _with_retry(
            Entrez.efetch, db="pmc", id=lookup_id, rettype="xml", retmode="xml"
        )
    except Exception as exc:
        _logger.warning("efetch pmc failed for %s: %s", canonical, exc)
        return None

    try:
        data = handle.read()
    finally:
        handle.close()

    if not data:
        _logger.warning("empty PMC response for %s", canonical)
        return None

    if isinstance(data, str):
        raw_xml = data
        xml_bytes = data.encode()
    else:
        xml_bytes = data
        raw_xml = data.decode("utf-8", errors="replace")

    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        _logger.warning("PMC XML parse failed for %s: %s", canonical, exc)
        return None

    # PMC sometimes returns an error envelope instead of an <article>.
    if root.find(".//article") is None and root.tag != "article":
        _logger.warning("no <article> element in PMC response for %s", canonical)
        return None

    sections = _extract_sections(root)
    tables = _extract_tables(root)

    return {
        "pmcid": canonical,
        "sections": sections,
        "tables": tables,
        "raw_xml": raw_xml,
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.fetcher",
        description="Search PubMed and dump abstracts (+ PMC full-texts when available) as JSON.",
    )
    parser.add_argument("--query", required=True, help="PubMed query string.")
    parser.add_argument(
        "--max-results", type=int, default=50,
        help="Maximum number of PMIDs to fetch (default: 50).",
    )
    parser.add_argument(
        "--min-year", type=int, default=None,
        help="Restrict to articles published on or after this year.",
    )
    parser.add_argument(
        "--output", type=Path, required=True,
        help="Path to write the JSON result to.",
    )
    parser.add_argument(
        "--no-fulltext", action="store_true",
        help="Skip PMC full-text fetches (abstracts only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: search PubMed and write results to JSON."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = _build_cli().parse_args(argv)

    pmids = search_pubmed(args.query, max_results=args.max_results, min_year=args.min_year)
    records = fetch_abstracts(pmids)

    fulltext_count = 0
    if not args.no_fulltext:
        for rec in records:
            if not rec.get("pmcid"):
                continue
            ft = fetch_pmc_fulltext(rec["pmcid"])
            if ft is not None:
                rec["fulltext"] = {
                    "pmcid": ft["pmcid"],
                    "sections": ft["sections"],
                    "tables": ft["tables"],
                }
                fulltext_count += 1

    output: dict[str, Any] = {
        "query": args.query,
        "min_year": args.min_year,
        "max_results": args.max_results,
        "pmid_count": len(pmids),
        "record_count": len(records),
        "pmcid_count": sum(1 for r in records if r.get("pmcid")),
        "fulltext_count": fulltext_count,
        "records": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    _logger.info(
        "wrote %s (records=%d, with_pmcid=%d, fulltext=%d)",
        args.output, len(records), output["pmcid_count"], fulltext_count,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
