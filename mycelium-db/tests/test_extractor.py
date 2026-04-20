"""Tests for the Claude-powered extractor.

All tests run offline: the Anthropic client is replaced with fakes, and
the dry-run integration tests confirm no network path is exercised.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src import extractor


SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "sample.json"


# ---- fixture: a canonical, schema-compliant response ----

SCHEMA_EXAMPLE_RESPONSE: dict = {
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
        "reactor_volume_ml": 250,
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
                "inoculum_percent": 5,
            },
            "outcomes": [
                {
                    "metric": "biomass", "value": 5.88, "unit": "mg/mL",
                    "value_g_L": 5.88, "metric_type": "mycelial_dry_weight",
                },
            ],
            "beta_glucan": {
                "reported": False,
                "total_value": None, "total_unit": None,
                "total_value_pct_dw": None,
                "beta_1_3_value": None, "beta_1_3_unit": None,
                "beta_1_6_value": None, "beta_1_6_unit": None,
                "ratio_1_3_to_1_6": None, "molecular_weight_kDa": None,
                "is_lentinan_specific": False,
                "notes": "Paper measured total polysaccharide",
            },
        }
    ],
    "analysis_notes": {
        "beta_glucan_analysis_method": "phenol_sulfuric_acid",
        "statistical_design": "Box-Behnken, 3 factors",
    },
    "source": {
        "section_used": ["abstract", "results", "table_2"],
        "extractor_model": "claude-opus-4-7",
        "extracted_at": "2026-04-18T10:00:00Z",
        "warnings": [],
    },
}


def _fake_client(response_text: str, input_tokens: int = 1200, output_tokens: int = 400):
    msg = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=response_text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


# ---- (a) load_papers filters by PMC full-text ----

def test_load_papers_only_pmc_returns_only_records_with_pmcid_and_fulltext():
    all_papers = extractor.load_papers(SAMPLE_PATH, only_pmc=False)
    pmc_papers = extractor.load_papers(SAMPLE_PATH, only_pmc=True)
    assert len(all_papers) == 10
    assert len(pmc_papers) == 4
    assert all(p.get("pmcid") and p.get("fulltext") for p in pmc_papers)


# ---- (b) build_prompt structure matches schema ----

def test_build_prompt_system_prompt_covers_schema_keys_and_user_prompt_is_ordered():
    paper = extractor.load_papers(SAMPLE_PATH, only_pmc=True)[0]
    system, user = extractor.build_prompt(paper)

    for key in (
        "pmid", "extraction_status", "relevance_score",
        "study_metadata", "experiments", "analysis_notes", "source",
    ):
        assert key in system, f"system prompt missing schema key: {key!r}"

    order_markers = [
        "--- PAPER METADATA ---",
        "--- ABSTRACT ---",
        "--- FULLTEXT SECTIONS ---",
        "--- TABLES ---",
        "Return only the JSON object.",
    ]
    positions = [user.find(m) for m in order_markers]
    assert all(p > -1 for p in positions), f"missing markers: {positions}"
    assert positions == sorted(positions), "user prompt sections out of order"

    assert f"PMID: {paper['pmid']}" in user


# ---- (c) validate_output flags broken records ----

def test_validate_output_reports_multiple_rule_violations_on_broken_record():
    broken = {
        "pmid": "999",
        "extraction_status": "ok",           # enum violation
        "relevance_score": 1.5,               # range violation
        "experiments": [
            {
                "conditions": {"carbon_concentration_g_L": -3},   # must be positive
                "outcomes": [],
                "beta_glucan": {"total_value_pct_dw": 150},       # must be in [0, 100]
            }
        ],
        "source": {"extracted_at": "not-a-date"},  # ISO 8601 violation
    }
    warnings = extractor.validate_output(broken)
    joined = "\n".join(warnings)
    assert "extraction_status" in joined
    assert "relevance_score" in joined
    assert "carbon_concentration_g_L" in joined
    assert "total_value_pct_dw" in joined
    assert "extracted_at" in joined


def test_validate_output_accepts_canonical_example():
    assert extractor.validate_output(SCHEMA_EXAMPLE_RESPONSE) == []


def test_validate_output_flags_success_without_conditions_and_outcomes():
    bad = {
        "pmid": "1",
        "extraction_status": "success",
        "relevance_score": 0.9,
        "experiments": [{"conditions": {}, "outcomes": []}],
        "source": {"extracted_at": "2026-04-20T00:00:00Z"},
    }
    warnings = extractor.validate_output(bad)
    assert any("success" in w and "conditions" in w for w in warnings)


# ---- (d) JSON parse fallbacks ----

def test_extract_one_recovers_from_markdown_fenced_response():
    paper = extractor.load_papers(SAMPLE_PATH, only_pmc=True)[0]
    fenced = (
        "Here is the extraction result:\n"
        "```json\n" + json.dumps(SCHEMA_EXAMPLE_RESPONSE) + "\n```\n"
        "(end of response)"
    )
    client = _fake_client(fenced)
    result = extractor.extract_one(client, paper)
    assert result["extraction_status"] == "success"
    assert result["source"]["extractor_model"] == extractor.MODEL_ID
    assert result["source"]["warnings"] == []


def test_parse_json_response_handles_first_brace_to_last_brace():
    raw = 'prefix junk {"pmid": "1", "extraction_status": "success"} trailing'
    parsed = extractor._parse_json_response(raw)
    assert parsed["pmid"] == "1"
    assert parsed["extraction_status"] == "success"


# ---- (e) dry-run performs no API call ----

def test_dry_run_does_not_call_anthropic(tmp_path, capsys, monkeypatch):
    # Poison the anthropic module: if main() ever tries to construct the
    # client under --dry-run, this test explodes.
    fake = types.ModuleType("anthropic")

    def _boom(*args, **kwargs):  # pragma: no cover - only runs on regression
        raise AssertionError("dry-run must not instantiate anthropic.Anthropic")

    fake.Anthropic = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    out = tmp_path / "should-not-exist.jsonl"
    rc = extractor.main([
        "--input", str(SAMPLE_PATH),
        "--output", str(out),
        "--only-pmc",
        "--limit", "1",
        "--dry-run",
    ])
    assert rc == 0
    assert not out.exists(), "dry-run must not write JSONL output"
    captured = capsys.readouterr().out
    assert "--- SYSTEM PROMPT ---" in captured
    assert "--- USER PROMPT ---" in captured


# ---- (f) dry-run integration over sample.json ----

def test_dry_run_limit_3_on_sample_prints_all_three_papers(tmp_path, capsys):
    out = tmp_path / "unused.jsonl"
    rc = extractor.main([
        "--input", str(SAMPLE_PATH),
        "--output", str(out),
        "--limit", "3",
        "--dry-run",
    ])
    assert rc == 0

    captured = capsys.readouterr().out
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    expected_pmids = [p["pmid"] for p in sample["papers"][:3]]
    for pmid in expected_pmids:
        assert f"PMID {pmid}" in captured, f"dry-run missing paper PMID={pmid}"
