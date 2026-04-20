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


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * INPUT_COST_USD_PER_MTOK
        + output_tokens * OUTPUT_COST_USD_PER_MTOK
    ) / 1_000_000


def _parse_json_response(text: str) -> dict[str, Any]:
    """Best-effort JSON parser: raw -> code-fence -> first '{' to last '}'."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("response is not valid JSON")


def _failed_record(paper: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "pmid": paper.get("pmid"),
        "extraction_status": "failed",
        "relevance_score": 0.0,
        "relevance_reason": "",
        "study_metadata": {},
        "experiments": [],
        "analysis_notes": {},
        "source": {
            "section_used": [],
            "extractor_model": MODEL_ID,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "warnings": [reason],
        },
    }


def extract_one(client: Any, paper: dict[str, Any]) -> dict[str, Any]:
    """Call Claude once for ``paper`` and return the parsed extraction.

    Retries the API call on transient errors (exponential backoff, up
    to :data:`_MAX_RETRIES`). On persistent failure returns a record
    with ``extraction_status="failed"`` and the error in
    ``source.warnings``.
    """
    system, user = build_prompt(paper)
    pmid = paper.get("pmid", "")
    response_text: str | None = None
    usage = None
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            message = client.messages.create(
                model=MODEL_ID,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            response_text = "".join(
                getattr(block, "text", "")
                for block in getattr(message, "content", [])
                if getattr(block, "type", None) == "text"
            )
            usage = getattr(message, "usage", None)
            break
        except Exception as exc:  # network, rate-limit, overloaded, etc.
            last_exc = exc
            if attempt == _MAX_RETRIES - 1:
                break
            backoff = 2 ** attempt
            _logger.warning(
                "API error on attempt %d/%d for PMID=%s: %s (retry in %ds)",
                attempt + 1, _MAX_RETRIES, pmid, exc, backoff,
            )
            time.sleep(backoff)

    if response_text is None:
        return _failed_record(
            paper, f"API call failed after {_MAX_RETRIES} attempts: {last_exc}"
        )

    try:
        extracted = _parse_json_response(response_text)
    except ValueError as exc:
        rec = _failed_record(paper, f"JSON parse failed: {exc}")
        rec["source"]["warnings"].append(
            "raw_response_head=" + response_text[:300].replace("\n", " ")
        )
        return rec

    extracted.setdefault("pmid", paper.get("pmid"))
    input_tokens = (
        int(getattr(usage, "input_tokens", 0) or 0) or _estimate_tokens(system + user)
    )
    output_tokens = (
        int(getattr(usage, "output_tokens", 0) or 0) or _estimate_tokens(response_text)
    )

    source = extracted.get("source") or {}
    source["extractor_model"] = MODEL_ID
    source["extracted_at"] = datetime.now(timezone.utc).isoformat()
    source.setdefault("section_used", [])
    source.setdefault("warnings", [])
    source["input_tokens"] = input_tokens
    source["output_tokens"] = output_tokens
    source["estimated_cost_usd"] = round(_estimate_cost(input_tokens, output_tokens), 6)
    extracted["source"] = source

    warnings = validate_output(extracted)
    if warnings:
        source["warnings"] = list(source.get("warnings", [])) + warnings
        if extracted.get("extraction_status") == "success":
            extracted["extraction_status"] = "partial"
    return extracted


def _is_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def validate_output(extracted: dict[str, Any]) -> list[str]:
    """Check one extraction against the schema's seven validation rules.

    Returns a list of human-readable warning strings. Empty list means
    the record passes all seven rules.
    """
    warnings: list[str] = []
    status = extracted.get("extraction_status")
    if status not in VALID_STATUSES:
        warnings.append(
            f"extraction_status must be one of {sorted(VALID_STATUSES)}, got {status!r}"
        )

    score = extracted.get("relevance_score")
    if not isinstance(score, (int, float)) or not 0.0 <= float(score) <= 1.0:
        warnings.append(f"relevance_score must be a number in [0.0, 1.0], got {score!r}")

    experiments = extracted.get("experiments")
    if not isinstance(experiments, list):
        warnings.append("experiments must be a list")
        experiments = []

    if status == "success":
        has_both = any(
            isinstance(exp, dict)
            and exp.get("conditions")
            and exp.get("outcomes")
            for exp in experiments
        )
        if not has_both:
            warnings.append(
                "extraction_status=success requires >=1 experiment with both conditions and outcomes"
            )
    if status == "not_relevant" and experiments:
        warnings.append("extraction_status=not_relevant requires empty experiments")

    for i, exp in enumerate(experiments):
        if not isinstance(exp, dict):
            continue
        cond = exp.get("conditions") or {}
        carbon = cond.get("carbon_concentration_g_L")
        if carbon is not None and (
            not isinstance(carbon, (int, float)) or carbon <= 0
        ):
            warnings.append(
                f"experiments[{i}].conditions.carbon_concentration_g_L must be positive if non-null, got {carbon!r}"
            )
        bg = exp.get("beta_glucan") or {}
        pct = bg.get("total_value_pct_dw")
        if pct is not None and (
            not isinstance(pct, (int, float)) or not 0.0 <= float(pct) <= 100.0
        ):
            warnings.append(
                f"experiments[{i}].beta_glucan.total_value_pct_dw must be in [0, 100] if non-null, got {pct!r}"
            )

    extracted_at = (extracted.get("source") or {}).get("extracted_at")
    if extracted_at is not None and not _is_iso8601(extracted_at):
        warnings.append(
            f"source.extracted_at must be ISO 8601 parseable, got {extracted_at!r}"
        )
    return warnings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: iterate papers, call the API, write JSONL."""
    # TODO: implement in 1-D
    raise NotImplementedError


def _build_cli() -> argparse.ArgumentParser:
    # TODO: implement in 1-D
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
