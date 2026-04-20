"""Structured-data extractor powered by the Claude API.

Reads papers produced by :mod:`src.fetcher` (JSON with a ``records`` or
``papers`` array) and asks Claude Opus 4.7 to extract cultivation
experiments for *Lentinula edodes*. Output is JSONL — one paper per line
— to make resume / streaming / partial-failure handling trivial.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger(__name__)

MODEL_ID = "claude-opus-4-7"
MAX_OUTPUT_TOKENS = 4096
MAX_INPUT_CHARS = 600_000  # ~150k tokens at ~4 chars/token
CHARS_PER_TOKEN = 4
INPUT_COST_USD_PER_MTOK = 15.0
OUTPUT_COST_USD_PER_MTOK = 75.0
_MAX_RETRIES = 3

VALID_STATUSES = {"success", "partial", "failed", "not_relevant"}

_SCHEMA_EXAMPLE = """{
  "pmid": "25868404",
  "extraction_status": "success",
  "relevance_score": 0.92,
  "relevance_reason": "RSM study optimizing submerged culture for biomass and polysaccharide production",
  "study_metadata": {
    "strain": "LeS (NCBI JX915793)",
    "strain_notes": "Strain deposited at NCBI accession JX915793",
    "culture_mode": "submerged_liquid",
    "optimization_method": "RSM_Box-Behnken",
    "reactor_scale": "shake_flask",
    "reactor_volume_ml": 250
  },
  "experiments": [
    {
      "experiment_id": "exp_1",
      "description": "RSM-optimized condition",
      "conditions": {
        "carbon_source": "glucose",
        "carbon_concentration_g_L": 20,
        "nitrogen_source": "yeast extract",
        "nitrogen_concentration_g_L": 5,
        "cn_ratio": 15.4,
        "initial_pH": 5.0,
        "temperature_C": 26,
        "agitation_rpm": 52,
        "duration_days": 25,
        "inoculum_percent": 5
      },
      "outcomes": [
        {"metric": "biomass", "value": 5.88, "unit": "mg/mL", "value_g_L": 5.88, "metric_type": "mycelial_dry_weight"},
        {"metric": "EPS", "value": 0.40, "unit": "mg/mL", "value_g_L": 0.40, "metric_type": "exopolysaccharide"},
        {"metric": "IPS", "value": 12.45, "unit": "mg/g", "value_g_L": null, "metric_type": "intracellular_polysaccharide"}
      ],
      "beta_glucan": {
        "reported": false,
        "total_value": null, "total_unit": null, "total_value_pct_dw": null,
        "beta_1_3_value": null, "beta_1_3_unit": null,
        "beta_1_6_value": null, "beta_1_6_unit": null,
        "ratio_1_3_to_1_6": null, "molecular_weight_kDa": null,
        "is_lentinan_specific": false,
        "notes": "Paper measured total polysaccharide, not beta-glucan specifically"
      }
    }
  ],
  "analysis_notes": {
    "beta_glucan_analysis_method": "phenol_sulfuric_acid",
    "statistical_design": "Box-Behnken design, 3 factors"
  },
  "source": {
    "section_used": ["abstract", "results", "table_2"],
    "extractor_model": "claude-opus-4-7",
    "extracted_at": "2026-04-18T10:00:00Z",
    "warnings": []
  }
}"""

_SYSTEM_PROMPT = f"""You are a scientific data extractor for Lentinula edodes cultivation studies.

Read the paper (metadata, abstract, optional PMC full-text sections and tables) and return exactly one JSON object matching the schema below.

## Schema shape and controlled vocabularies

Top-level keys: pmid, extraction_status, relevance_score, relevance_reason, study_metadata, experiments, analysis_notes, source.

- extraction_status: one of "success" | "partial" | "failed" | "not_relevant".
  * success = >=1 experiment with conditions AND outcomes.
  * partial = some conditions or outcomes missing.
  * not_relevant = off-topic (relevance_score < 0.3); experiments MUST be empty.
- relevance_score: float 0.0-1.0. Core cultivation study with biomass/beta-glucan data -> >=0.8. Passing mention only -> <0.5. Off-topic -> <0.3.
- study_metadata.culture_mode: "submerged_liquid" | "solid_state" | "plate_agar" | "log_synthetic" | "other".
- study_metadata.optimization_method: "RSM_Box-Behnken" | "RSM_central_composite" | "Plackett-Burman" | "Taguchi" | "OFAT" | "none" | "other".
- study_metadata.reactor_scale: "test_tube" | "shake_flask" | "stirred_tank" | "airlift_bioreactor" | "petri_dish" | "other".
- experiments[]: one object per DISTINCT condition set. If the paper compares 5 carbon sources, emit 5 experiments.
- experiments[].conditions: carbon_source, carbon_concentration_g_L, nitrogen_source, nitrogen_concentration_g_L, cn_ratio, initial_pH, temperature_C, agitation_rpm, duration_days, inoculum_percent. All numeric fields null if not reported.
- experiments[].outcomes: list of {{metric, value, unit, value_g_L, metric_type}}. metric_type in: mycelial_dry_weight, mycelial_wet_weight, exopolysaccharide, intracellular_polysaccharide, total_polysaccharide, protein_content, reducing_sugar_residual, ergothioneine, other.
- experiments[].beta_glucan: dedicated structured field (reported bool + values + units + is_lentinan_specific + notes).
- analysis_notes.beta_glucan_analysis_method: Megazyme_kit | phenol_sulfuric_acid | Congo_red | NMR | HPLC | enzymatic_other | other | not_specified.
- source.section_used: list of sections you actually used (e.g. ["abstract", "results", "table_1"]).

## Normalization

- Concentrations -> g/L. mg/mL == g/L. % (w/v) * 10 = g/L.
- Temperatures -> Celsius.
- Durations -> days.
- beta_glucan.total_value_pct_dw: mg/g DW * 0.1 = %DW; g/100g = %DW; mg/L cannot convert -> leave null and explain in notes.
- is_lentinan_specific: true only if the paper explicitly names "lentinan" AND provides structural evidence (beta-(1->3) main chain + beta-(1->6) branches).

## Critical rules

- null is allowed and REQUIRED when data is absent. NEVER invent numbers or fields.
- Interpret multi-row table headers correctly. Example: headers [[GeneID, Products, log2FC], [T1/T0, T2/T0, T2/T1]] means the log2FC column spans three sub-columns.
- If relevance_score < 0.3, set extraction_status = "not_relevant" and leave experiments as an empty list.
- source.extractor_model, source.extracted_at, and source.warnings may be left empty; the caller overwrites source.extractor_model and source.extracted_at, and appends validation warnings to source.warnings.
- Return ONLY the JSON object. No explanation, no markdown code fences, no greetings.

## Complete example (shape reference — do not copy values)

{_SCHEMA_EXAMPLE}
"""


def load_papers(input_path: Path, only_pmc: bool) -> list[dict[str, Any]]:
    """Load papers from a fetcher-produced JSON file.

    Supports both ``{"records": [...]}`` (fetcher default) and
    ``{"papers": [...]}`` (sample fixture). When ``only_pmc`` is True,
    keeps only papers that have ``pmcid`` and ``fulltext``.
    """
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        papers = data
    elif isinstance(data, dict):
        if "records" in data:
            papers = data["records"]
        elif "papers" in data:
            papers = data["papers"]
        else:
            raise ValueError(
                f"{input_path}: expected a list or a dict with 'records'/'papers' key"
            )
    else:
        raise ValueError(f"{input_path}: top-level JSON must be list or object")

    if not isinstance(papers, list):
        raise ValueError(f"{input_path}: 'records'/'papers' value must be a list")

    if only_pmc:
        papers = [p for p in papers if p.get("pmcid") and p.get("fulltext")]
    return papers


_SECTION_ORDER: list[tuple[str, tuple[str, ...]]] = [
    ("introduction", ("intro", "introduction", "background")),
    ("methods", ("methods", "materials_and_methods")),
    ("results", ("results",)),
    ("discussion", ("discussion", "conclusion", "conclusions")),
]


def _format_metadata(paper: dict[str, Any]) -> list[str]:
    lines = [f"PMID: {paper.get('pmid') or '(none)'}"]
    if paper.get("pmcid"):
        lines.append(f"PMCID: {paper['pmcid']}")
    if paper.get("doi"):
        lines.append(f"DOI: {paper['doi']}")
    if paper.get("title"):
        lines.append(f"Title: {paper['title']}")
    authors = paper.get("authors") or []
    if authors:
        shown = ", ".join(authors[:10]) + ("..." if len(authors) > 10 else "")
        lines.append(f"Authors: {shown}")
    if paper.get("journal"):
        lines.append(f"Journal: {paper['journal']}")
    if paper.get("year"):
        lines.append(f"Year: {paper['year']}")
    return lines


def _iter_sections(sections: dict[str, Any]):
    yielded: set[str] = set()
    for canonical, aliases in _SECTION_ORDER:
        for alias in aliases:
            text = sections.get(alias)
            if text:
                yielded.add(alias)
                yield canonical, str(text)
                break
    for key, text in sections.items():
        if key in yielded or not text:
            continue
        yield key, str(text)


def _table_to_markdown(table: dict[str, Any]) -> str:
    caption = table.get("caption") or ""
    headers = table.get("headers") or []
    rows = table.get("rows") or []

    if headers:
        width = max((len(h) for h in headers), default=0)
        flat_header = []
        for col in range(width):
            parts = [h[col] for h in headers if col < len(h) and h[col]]
            flat_header.append(" / ".join(parts))
        header_row: list[Any] = flat_header
        body_rows = list(rows)
    elif rows:
        header_row = list(rows[0])
        body_rows = list(rows[1:])
    else:
        header_row = []
        body_rows = []

    lines: list[str] = []
    if caption:
        lines.append(f"**{caption}**")
    if header_row:
        lines.append("| " + " | ".join(str(c) for c in header_row) + " |")
        lines.append("| " + " | ".join("---" for _ in header_row) + " |")
    for row in body_rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _trim_discussion_numeric_only(text: str) -> str:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    kept = [p for p in paragraphs if re.search(r"\d", p)]
    return "\n\n".join(kept) if kept else text


def _format_user_prompt(
    paper: dict[str, Any],
    *,
    drop_intro: bool = False,
    trim_discussion: bool = False,
    only_methods_results: bool = False,
    abstract_tables_only: bool = False,
) -> str:
    parts: list[str] = [
        "Extract structured data from this paper according to the schema.",
        "",
        "--- PAPER METADATA ---",
    ]
    parts.extend(_format_metadata(paper))
    parts.append("")

    abstract = (paper.get("abstract") or "").strip()
    if abstract:
        parts.append("--- ABSTRACT ---")
        parts.append(abstract)
        parts.append("")

    fulltext = paper.get("fulltext") or {}
    sections = {} if abstract_tables_only else (fulltext.get("sections") or {})
    if sections:
        parts.append("--- FULLTEXT SECTIONS ---")
        for name, text in _iter_sections(sections):
            if only_methods_results and name not in ("methods", "results"):
                continue
            if drop_intro and name == "introduction":
                continue
            if trim_discussion and name == "discussion":
                text = _trim_discussion_numeric_only(text)
            parts.append(f"## {name}")
            parts.append(text)
            parts.append("")

    tables = fulltext.get("tables") or []
    if tables:
        parts.append("--- TABLES ---")
        for table in tables:
            parts.append(_table_to_markdown(table))
            parts.append("")

    parts.append("Return only the JSON object.")
    return "\n".join(parts)


def build_prompt(paper: dict[str, Any]) -> tuple[str, str]:
    """Build ``(system_prompt, user_prompt)`` for one paper.

    Assembles metadata, abstract, full-text sections, and tables in a
    deterministic order. Trims content progressively when the total
    would exceed :data:`MAX_INPUT_CHARS`.
    """
    trim_levels: list[dict[str, bool]] = [
        {},
        {"drop_intro": True},
        {"drop_intro": True, "trim_discussion": True},
        {"only_methods_results": True},
        {"abstract_tables_only": True},
    ]
    user = _format_user_prompt(paper)
    for kwargs in trim_levels:
        user = _format_user_prompt(paper, **kwargs)
        if len(user) <= MAX_INPUT_CHARS:
            break
    return _SYSTEM_PROMPT, user


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
