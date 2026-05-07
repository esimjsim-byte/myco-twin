"""MYCO-TWIN — β-glucan Corpus Browser (Track A integration).

Reads mycelium.db (24 papers, 131 experiments) and renders search +
case-study charts. Track A and Track B unified.

Run:
    streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from load_from_db import load_curated  # noqa: E402

FIG_DIR = REPO_ROOT / "docs" / "figures" / "case_40826246"

KEEP_CRITERIA = [
    "A. submerged_liquid 배양",
    "B. CDW (mycelial dry weight, g/L) 보고",
    "C. β-glucan-specific 분석법 (Megazyme / enzymatic / NMR)",
    "D. 정량 yield 데이터 (g/L 또는 %DW)",
]

TABLE_COLUMNS = [
    "experiment_id",
    "description",
    "agitation_rpm",
    "cdw_g_per_l",
    "beta_glucan_pct_dw",
]

TABS = [
    ("Burst Frequency", "a_burst_freq_vs_cdw.html"),
    ("Constant Impeller", "b_constant_impeller_vs_beta_glucan.html"),
    ("Burst Speed", "c_burst_speed_vs_beta_glucan.html"),
    ("Batch vs Semicontinuous", "d_batch_vs_semicontinuous.html"),
]


@st.cache_data
def get_dataframe() -> pd.DataFrame:
    return load_curated()


def main() -> None:
    st.set_page_config(
        page_title="MYCO-TWIN — β-glucan Corpus Browser",
        layout="wide",
    )
    df = get_dataframe()

    st.title("MYCO-TWIN — β-glucan Corpus Browser")
    n_papers = df["pmid"].nunique()
    n_experiments = len(df)
    st.caption(f"Curated dataset: {n_papers} papers, {n_experiments} experiments")

    with st.sidebar:
        st.header("Dataset")
        st.metric("Papers", n_papers)
        st.metric("Experiments", n_experiments)

        st.markdown("**KEEP 기준** (4개 중 3개 이상 충족, DROP 없음)")
        for line in KEEP_CRITERIA:
            st.markdown(f"- {line}")

        st.markdown("---")
        st.markdown("**Source PMIDs**")
        for pmid in sorted(df["pmid"].unique()):
            st.markdown(f"- [PMID {pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)")

    query = st.text_input(
        "실험 검색",
        placeholder="예: β-glucan 높은 조건",
        help="description 컬럼에서 부분 일치 검색 (대소문자 무시). 비어있으면 전체 표시.",
    )

    if query.strip():
        mask = df["description"].fillna("").str.contains(
            query.strip(), case=False, regex=False
        )
        view = df[mask]
        st.write(f"**{len(view)}** of {n_experiments} experiments match `{query}`")
    else:
        view = df

    st.dataframe(
        view[TABLE_COLUMNS],
        hide_index=True,
        width="stretch",
    )

    st.subheader("Case study — PMID 40826246")
    tab_objects = st.tabs([label for label, _ in TABS])
    for tab, (_label, html_name) in zip(tab_objects, TABS):
        html_path = FIG_DIR / html_name
        with tab:
            if html_path.exists():
                components.html(
                    html_path.read_text(encoding="utf-8"),
                    height=560,
                    scrolling=True,
                )
            else:
                st.warning(f"Figure not found: {html_path}")


if __name__ == "__main__":
    main()
