"""GP regression training: agitation_rpm → β-glucan %DW for PMID 40826246.

Stage 1: Train on PMID 40826246 (11 experiments, 400 RPM clustered with
burst frequency variations creating natural noise estimate).

Output: trained model artifact + prediction plot for visual verification.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C, WhiteKernel

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "mycelium.db"


def load_training_data() -> pd.DataFrame:
    """Load the 11 PMID 40826246 experiments with β-glucan measurements."""
    sql = """
        SELECT
            experiment_pk,
            experiment_id,
            agitation_rpm,
            bg_pct_dw,
            description
        FROM v_useful_experiments
        WHERE pmid = '40826246'
          AND bg_reported = 1
        ORDER BY agitation_rpm, bg_pct_dw
    """
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn)


def train_gp_model(X: np.ndarray, y: np.ndarray) -> GaussianProcessRegressor:
    """Fit GP regression with RBF kernel + white noise component."""
    # Kernel: constant * RBF + white noise (estimates measurement noise)
    kernel = (
        C(constant_value=1.0, constant_value_bounds=(1e-2, 1e2))
        * RBF(length_scale=100.0, length_scale_bounds=(10.0, 1e3))
        + WhiteKernel(noise_level=0.5, noise_level_bounds=(1e-3, 1e1))
    )

    gp = GaussianProcessRegressor(
        kernel=kernel,
        normalize_y=True,
        n_restarts_optimizer=10,
        random_state=42,
    )
    gp.fit(X, y)
    return gp


def main() -> None:
    df = load_training_data()

    print(f"Training data: {len(df)} experiments")
    print(df[["agitation_rpm", "bg_pct_dw", "description"]].to_string())

    # Filter out NaN bg_pct_dw rows
    df_clean = df.dropna(subset=["agitation_rpm", "bg_pct_dw"]).copy()
    print(f"\nAfter NaN drop: {len(df_clean)} experiments")

    X = df_clean[["agitation_rpm"]].values
    y = df_clean["bg_pct_dw"].values

    print(f"\nX range: {X.min()} ~ {X.max()} RPM")
    print(f"y range: {y.min():.2f} ~ {y.max():.2f} %DW")

    # Train
    gp = train_gp_model(X, y)
    print(f"\nLearned kernel: {gp.kernel_}")
    print(f"Log-marginal-likelihood: {gp.log_marginal_likelihood(gp.kernel_.theta):.3f}")

    # Predict on a fine grid
    X_pred = np.linspace(150, 700, 200).reshape(-1, 1)
    y_mean, y_std = gp.predict(X_pred, return_std=True)

    # Print key predictions
    print("\nPredictions at key RPM values:")
    for rpm in [200, 300, 400, 500, 600]:
        m, s = gp.predict([[rpm]], return_std=True)
        print(f"  RPM {rpm:3d}: {m[0]:.2f} ± {s[0]:.2f} %DW (95% CI: [{m[0]-1.96*s[0]:.2f}, {m[0]+1.96*s[0]:.2f}])")




    # Save trained model + training data for Streamlit app
    import joblib
    artifact_dir = Path(__file__).resolve().parent.parent / "data" / "models"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact = {
        "model": gp,
        "X_train": X,
        "y_train": y,
        "feature_name": "agitation_rpm",
        "target_name": "beta_glucan_pct_dw",
        "X_min": float(X.min()),
        "X_max": float(X.max()),
        "kernel_params": str(gp.kernel_),
        "log_marginal_likelihood": float(gp.log_marginal_likelihood(gp.kernel_.theta)),
        "n_train": len(X),
    }
    artifact_path = artifact_dir / "gp_rpm_to_beta_glucan.joblib"
    joblib.dump(artifact, artifact_path)
    print(f"\nSaved model artifact: {artifact_path}")

if __name__ == "__main__":
    main()
