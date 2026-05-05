"""Load curated β-glucan extraction data into a long-format DataFrame.

One row per experiment, across all PMIDs in extracted_curated.jsonl. As more
papers are added to the curated file, the same loader returns a wider frame and
the case-study charts automatically pick up the new rows.

Columns
-------
pmid, experiment_id, description, strain, mode (batch/semicontinuous),
agitation_rpm (constant impeller), bursts_per_day, burst_speed_rpm,
duration_days, dilution_rate_h_inv, cdw_g_per_l,
biomass_productivity_mg_per_h, total_glucan_pct_dw, beta_glucan_pct_dw,
alpha_glucan_pct_dw.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

CURATED_PATH = Path("data/processed/extracted_curated.jsonl")

_BURST_FREQ_RE = re.compile(r"(\d+)\s*bursts?\b", re.IGNORECASE)
_BURST_SPEED_EXPLICIT_RE = re.compile(r"burst speed\s*(\d+)\s*RPM", re.IGNORECASE)
_BURST_SPEED_AT_RE = re.compile(r"bursts?(?:/day)?\s*at\s*(\d+)\s*RPM", re.IGNORECASE)
_BURST_SPEED_PAREN_RE = re.compile(r"\((\d+)\s*RPM\s*,\s*\d+\s*s\)", re.IGNORECASE)
_DILUTION_RE = re.compile(r"D\s*=\s*([\d.]+)\s*h", re.IGNORECASE)

# Greek β/α glucan, possibly with hyphen, allowing range "8–10%" or single "9.9%"
_BG_RANGE_RE = re.compile(r"β-?glucan\s*([\d.]+)\s*[–—\-]\s*([\d.]+)\s*%", re.IGNORECASE)
_BG_SINGLE_RE = re.compile(r"β-?glucan\s*~?\s*([\d.]+)\s*%", re.IGNORECASE)
_AG_RANGE_RE = re.compile(r"α-?glucan\s*([\d.]+)\s*[–—\-]\s*([\d.]+)\s*%", re.IGNORECASE)
_AG_SINGLE_RE = re.compile(r"α-?glucan\s*~?\s*([\d.]+)\s*%", re.IGNORECASE)


def _parse_burst_freq(description: str) -> int | None:
    m = _BURST_FREQ_RE.search(description or "")
    return int(m.group(1)) if m else None


def _parse_burst_speed(description: str) -> int | None:
    for rx in (_BURST_SPEED_EXPLICIT_RE, _BURST_SPEED_AT_RE, _BURST_SPEED_PAREN_RE):
        m = rx.search(description or "")
        if m:
            return int(m.group(1))
    return None


def _parse_mode(description: str) -> str | None:
    d = (description or "").lower()
    if "semicontinuous" in d or "semi-continuous" in d:
        return "semicontinuous"
    if "batch" in d:
        return "batch"
    return None


def _parse_dilution_rate(description: str) -> float | None:
    m = _DILUTION_RE.search(description or "")
    return float(m.group(1)) if m else None


def _extract_glucan_pct(notes: str | None, range_re: re.Pattern, single_re: re.Pattern) -> float | None:
    if not notes:
        return None
    m = range_re.search(notes)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2.0
    m = single_re.search(notes)
    if m:
        return float(m.group(1))
    return None


def _pick_cdw(outcomes: list | None) -> float | None:
    """Prefer 'maximum CDW' or plain 'CDW' over 'average CDW'."""
    if not outcomes:
        return None
    candidates: list[tuple[int, float]] = []
    for o in outcomes:
        if not isinstance(o, dict) or o.get("metric_type") != "mycelial_dry_weight":
            continue
        metric = (o.get("metric") or "").lower()
        if "max" in metric:
            rank = 0
        elif "avg" in metric or "average" in metric:
            rank = 2
        else:
            rank = 1
        value = o.get("value_g_L") if o.get("value_g_L") is not None else o.get("value")
        if value is not None:
            candidates.append((rank, float(value)))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _pick_productivity_mg_per_h(outcomes: list | None) -> float | None:
    for o in outcomes or []:
        if isinstance(o, dict) and (o.get("metric") or "").lower() == "biomass productivity":
            unit = (o.get("unit") or "").lower()
            value = o.get("value")
            if value is None:
                continue
            if "mg" in unit and "/h" in unit:
                return float(value)
            if "g/h" in unit and "mg" not in unit:
                return float(value) * 1000.0
    return None


def load_curated(path: str | Path = CURATED_PATH) -> pd.DataFrame:
    """Return a long-format DataFrame, one row per experiment across all curated papers."""
    rows: list[dict] = []
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            record = json.loads(line)
            sm = record.get("study_metadata") or {}
            pmid = record.get("pmid")
            strain = sm.get("strain")
            for exp in record.get("experiments", []):
                cond = exp.get("conditions") or {}
                bg_block = exp.get("beta_glucan") or {}
                bg_notes = bg_block.get("notes")
                desc = exp.get("description") or ""
                beta_pct = _extract_glucan_pct(bg_notes, _BG_RANGE_RE, _BG_SINGLE_RE)
                alpha_pct = _extract_glucan_pct(bg_notes, _AG_RANGE_RE, _AG_SINGLE_RE)
                rows.append({
                    "pmid": pmid,
                    "experiment_id": exp.get("experiment_id"),
                    "description": desc,
                    "strain": strain,
                    "mode": _parse_mode(desc),
                    "agitation_rpm": cond.get("agitation_rpm"),
                    "bursts_per_day": _parse_burst_freq(desc),
                    "burst_speed_rpm": _parse_burst_speed(desc),
                    "duration_days": cond.get("duration_days"),
                    "dilution_rate_h_inv": _parse_dilution_rate(desc),
                    "cdw_g_per_l": _pick_cdw(exp.get("outcomes")),
                    "biomass_productivity_mg_per_h": _pick_productivity_mg_per_h(exp.get("outcomes")),
                    "total_glucan_pct_dw": bg_block.get("total_value_pct_dw"),
                    "beta_glucan_pct_dw": beta_pct,
                    "alpha_glucan_pct_dw": alpha_pct,
                })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = load_curated()
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(f"Loaded {len(df)} experiments from {df['pmid'].nunique()} paper(s)")
    print(df)
