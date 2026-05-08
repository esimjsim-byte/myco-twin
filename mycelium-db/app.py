"""MYCO-TWIN — β-glucan Corpus Browser + ML Prediction (Track A integration).

Reads mycelium.db (24 papers, 131 experiments) and renders search +
case-study charts + GP regression prediction tab.

Run:
    streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from load_from_db import load_curated  # noqa: E402

FIG_DIR = REPO_ROOT / "docs" / "figures" / "case_40826246"
MODEL_PATH = REPO_ROOT / "data" / "models" / "gp_rpm_to_beta_glucan.joblib"

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

CASE_TABS = [
    ("Burst Frequency", "a_burst_freq_vs_cdw.html"),
    ("Constant Impeller", "b_constant_impeller_vs_beta_glucan.html"),
    ("Burst Speed", "c_burst_speed_vs_beta_glucan.html"),
    ("Batch vs Semicontinuous", "d_batch_vs_semicontinuous.html"),
]


@st.cache_data
def get_dataframe() -> pd.DataFrame:
    return load_curated()


@st.cache_resource
def load_gp_model() -> dict | None:
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def render_corpus_browser(df: pd.DataFrame) -> None:
    n_papers = df["pmid"].nunique()
    n_experiments = len(df)

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

    st.dataframe(view[TABLE_COLUMNS], hide_index=True, width="stretch")


def render_case_study() -> None:
    st.subheader("Case study — PMID 40826246")
    tab_objects = st.tabs([label for label, _ in CASE_TABS])
    for tab, (_label, html_name) in zip(tab_objects, CASE_TABS):
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


def render_ml_prediction() -> None:
    st.subheader("🔮 ML Prediction — RPM → β-glucan %DW")

    artifact = load_gp_model()
    if artifact is None:
        st.warning(
            f"Model not found at {MODEL_PATH}. "
            "Run `uv run python scripts/gp_train.py` to train."
        )
        return

    gp = artifact["model"]
    X_train = artifact["X_train"]
    y_train = artifact["y_train"]

    st.caption(
        f"Trained on PMID 40826246 ({artifact['n_train']} experiments) · "
        f"Kernel: `{artifact['kernel_params']}`"
    )

    # Slider for user input
    col_left, col_right = st.columns([1, 2])
    with col_left:
        rpm = st.slider(
            "Agitation RPM",
            min_value=150,
            max_value=700,
            value=400,
            step=10,
            help="Constant impeller agitation rate. Training data: 200, 400, 600 RPM.",
        )

        # Predict at this RPM
        mean, std = gp.predict([[rpm]], return_std=True)
        ci_low = mean[0] - 1.96 * std[0]
        ci_high = mean[0] + 1.96 * std[0]

        st.metric(
            label=f"Predicted β-glucan at {rpm} RPM",
            value=f"{mean[0]:.2f} %DW",
            delta=f"± {std[0]:.2f} (1σ)",
        )
        st.caption(f"95% CI: [{ci_low:.2f}, {ci_high:.2f}] %DW")

        if rpm < artifact["X_min"] or rpm > artifact["X_max"]:
            st.warning(
                f"⚠️ Extrapolation: training data covers {artifact['X_min']:.0f}–{artifact['X_max']:.0f} RPM. "
                "Predictions outside this range have inflated uncertainty."
            )

    with col_right:
        # Generate prediction curve
        X_pred = np.linspace(150, 700, 200).reshape(-1, 1)
        y_mean, y_std = gp.predict(X_pred, return_std=True)
        y_upper = y_mean + 1.96 * y_std
        y_lower = y_mean - 1.96 * y_std

        fig = go.Figure()

        # 95% CI band
        fig.add_trace(go.Scatter(
            x=np.concatenate([X_pred.flatten(), X_pred.flatten()[::-1]]),
            y=np.concatenate([y_upper, y_lower[::-1]]),
            fill="toself",
            fillcolor="rgba(99, 110, 250, 0.2)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="skip",
            name="95% CI",
        ))

        # GP mean
        fig.add_trace(go.Scatter(
            x=X_pred.flatten(),
            y=y_mean,
            mode="lines",
            line=dict(color="rgb(99, 110, 250)", width=2),
            name="GP mean",
        ))

        # Training data
        fig.add_trace(go.Scatter(
            x=X_train.flatten(),
            y=y_train,
            mode="markers",
            marker=dict(color="red", size=10, symbol="circle"),
            name="Training data",
        ))

        # User's selected RPM
        fig.add_trace(go.Scatter(
            x=[rpm],
            y=[mean[0]],
            mode="markers",
            marker=dict(color="green", size=15, symbol="diamond"),
            name=f"Selected: {rpm} RPM",
        ))

        fig.update_layout(
            xaxis_title="Agitation RPM",
            yaxis_title="β-glucan (%DW)",
            height=450,
            showlegend=True,
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        )

        st.plotly_chart(fig, use_container_width=True)


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

    # Top-level tabs: Corpus Browser | Case Study | ML Prediction
    tab_corpus, tab_case, tab_ml = st.tabs([
        "📚 Corpus",
        "📊 Case Study",
        "🔮 ML Prediction",
    ])
    with tab_corpus:
        render_corpus_browser(df)
    with tab_case:
        render_case_study()
    with tab_ml:
        render_ml_prediction()


if __name__ == "__main__":
    main()