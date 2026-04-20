"""Structured-data extractor powered by the Claude API.

Reads papers produced by :mod:`src.fetcher` (JSON with a ``records`` or
``papers`` array) and asks Claude Opus 4.7 to extract cultivation
experiments for *Lentinula edodes*. Output is JSONL — one paper per line
— to make resume / streaming / partial-failure handling trivial.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


MODEL_ID = "claude-opus-4-7"
MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_CHARS = 600_000  # ~150k tokens at ~4 chars/token
CHARS_PER_TOKEN = 4
INPUT_COST_USD_PER_MTOK = 15.0
OUTPUT_COST_USD_PER_MTOK = 75.0
_MAX_RETRIES = 3

VALID_STATUSES = {"success", "partial", "failed", "not_relevant"}


def load_papers(input_path: Path, only_pmc: bool) -> list[dict[str, Any]]:
    """Load papers from a fetcher-produced JSON file.

    Supports both ``{"records": [...]}`` (fetcher default) and
    ``{"papers": [...]}`` (sample fixture). When ``only_pmc`` is True,
    keeps only papers that have ``pmcid`` and ``fulltext``.
    """
    # TODO: implement in 1-B
    raise NotImplementedError


def build_prompt(paper: dict[str, Any]) -> tuple[str, str]:
    """Build ``(system_prompt, user_prompt)`` for one paper.

    Assembles metadata, abstract, full-text sections, and tables in a
    deterministic order. Trims content progressively when the total
    would exceed :data:`MAX_INPUT_CHARS`.
    """
    # TODO: implement in 1-B
    raise NotImplementedError


def extract_one(client: Any, paper: dict[str, Any]) -> dict[str, Any]:
    """Call Claude once for ``paper`` and return the parsed extraction.

    Retries the API call on transient errors (exponential backoff, up
    to :data:`_MAX_RETRIES`). On persistent failure returns a record
    with ``extraction_status="failed"`` and the error in ``warnings``.
    """
    # TODO: implement in 1-C
    raise NotImplementedError


def validate_output(extracted: dict[str, Any]) -> list[str]:
    """Check one extraction against the schema's validation rules.

    Returns a list of human-readable warning strings. Empty list means
    the record passes all seven rules.
    """
    # TODO: implement in 1-C
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: iterate papers, call the API, write JSONL."""
    # TODO: implement in 1-D
    raise NotImplementedError


def _build_cli() -> argparse.ArgumentParser:
    # TODO: implement in 1-D
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
