"""Load mycelium.db into a long-format DataFrame compatible with app.py.

Track A integration: replaces load_curated.py for the Streamlit app.
Reads from data/processed/mycelium.db and returns the same column shape
that app.py's TABLE_COLUMNS expects.

Columns returned (compatible with app.py):
    pmid, experiment_id, description, strain, mode,
    agitation_rpm, bursts_per_day, burst_speed_rpm,
    duration_days, dilution_rate_h_inv,
    cdw_g_per_l, biomass_productivity_mg_per_h,
    total_glucan_pct_dw, beta_glucan_pct_dw, alpha_glucan_pct_dw

Drop-in replacement: same `load_curated()` function name and signature,
so app.py only needs an import-line change.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "mycelium.db"

# ---------- Description-parsing regex (reused from load_curated.py) ----------
_BURST_FREQ_RE = re.compile(r"(\d+)\s*bursts?\b", re.IGNORECASE)
_BURST_SPEED_EXPLICIT_RE = re.compile(r"burst speed\s*(\d+)\s*RPM", re.IGNORECASE)
_BURST_SPEED_AT_RE = re.compile(r"bursts?(?:/day)?\s*at\s*(\d+)\s*RPM", re.IGNORECASE)
_BURST_SPEED_PAREN_RE = re.compile(r"\((\d+)\s*RPM\s*,\s*\d+\s*s\)", re.IGNORECASE)
_DILUTION_RE = re.compile(r"D\s*=\s*([\d.]+)\s*h", re.IGNORECASE)


def _parse_burst_freq(description: str | None) -> int | None:
    if not description:
        return None
    m = _BURST_FREQ_RE.search(description)
    return int(m.group(1)) if m else None


def _parse_burst_speed(description: str | None) -> int | None:
    if not description:
        return None
    for rx in (_BURST_SPEED_EXPLICIT_RE, _BURST_SPEED_AT_RE, _BURST_SPEED_PAREN_RE):
        m = rx.search(description)
        if m:
            return int(m.group(1))
    return None


def _parse_mode(description: str | None) -> str | None:
    if not description:
        return None
    d = description.lower()
    if "semicontinuous" in d or "semi-continuous" in d:
        return "semicontinuous"
    if "batch" in d:
        return "batch"
    return None


def _parse_dilution_rate(description: str | None) -> float | None:
    if not description:
        return None
    m = _DILUTION_RE.search(description)
    return float(m.group(1)) if m else None


# ---------- Main loader ----------

_SQL = """
SELECT
    ue.pmid,
    ue.experiment_pk,
    ue.experiment_id,
    ue.description,
    ue.strain,
    ue.culture_mode,
    ue.agitation_rpm,
    ue.duration_days,
    ue.bg_pct_dw AS beta_glucan_pct_dw,
    ue.bg_total_value AS total_glucan_pct_dw,
    -- CDW: prefer max value over avg, from outcomes EAV table
    (
        SELECT o.value_g_L
        FROM outcomes o
        WHERE o.experiment_pk = ue.experiment_pk
          AND o.metric_type = 'mycelial_dry_weight'
          AND o.value_g_L IS NOT NULL
        ORDER BY
            CASE
                WHEN LOWER(o.metric) LIKE '%max%' THEN 0
                WHEN LOWER(o.metric) LIKE '%avg%' OR LOWER(o.metric) LIKE '%average%' THEN 2
                ELSE 1
            END,
            o.value_g_L DESC
        LIMIT 1
    ) AS cdw_g_per_l,
    -- biomass productivity in mg/h, if available
    (
        SELECT
            CASE
                WHEN LOWER(o.unit) LIKE '%mg%/h%' THEN o.value
                WHEN LOWER(o.unit) LIKE '%g/h%' AND LOWER(o.unit) NOT LIKE '%mg%' THEN o.value * 1000.0
                ELSE NULL
            END
        FROM outcomes o
        WHERE o.experiment_pk = ue.experiment_pk
          AND LOWER(o.metric) = 'biomass productivity'
          AND o.value IS NOT NULL
        LIMIT 1
    ) AS biomass_productivity_mg_per_h
FROM v_useful_experiments ue
ORDER BY ue.pmid, ue.experiment_pk
"""


def load_curated(_path=None) -> pd.DataFrame:
    """Load experiments from mycelium.db.

    The `_path` argument is accepted for backward compatibility with the
    original `load_curated(CURATED_PATH)` signature but is ignored —
    this loader always reads from mycelium.db.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(_SQL, conn)

    # Description-derived columns (parsed from text, not in DB)
    df["mode"] = df["description"].apply(_parse_mode)
    df["bursts_per_day"] = df["description"].apply(_parse_burst_freq)
    df["burst_speed_rpm"] = df["description"].apply(_parse_burst_speed)
    df["dilution_rate_h_inv"] = df["description"].apply(_parse_dilution_rate)

    # alpha_glucan: not separately tracked in mycelium.db schema yet
    df["alpha_glucan_pct_dw"] = None

    # Reorder columns to match app.py expectations
    column_order = [
        "pmid",
        "experiment_id",
        "description",
        "strain",
        "mode",
        "agitation_rpm",
        "bursts_per_day",
        "burst_speed_rpm",
        "duration_days",
        "dilution_rate_h_inv",
        "cdw_g_per_l",
        "biomass_productivity_mg_per_h",
        "total_glucan_pct_dw",
        "beta_glucan_pct_dw",
        "alpha_glucan_pct_dw",
    ]
    df = df[column_order]

    return df


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 250)
    df = load_curated()
    n_papers = df["pmid"].nunique()
    print(f"Loaded {len(df)} experiments from {n_papers} paper(s)\n")
    print("Sample (first 5 rows):")
    print(df.head())
    print(f"\nColumn dtypes:")
    print(df.dtypes)
    print(f"\nNon-null counts:")
    print(df.count())
