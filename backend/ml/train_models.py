"""
ML model training for ChainMind.

Models trained:
  1. XGBoost cost predictor  → ml/cost_model.pkl
  2. Random Forest transit estimator → ml/transit_model.pkl

Feature engineering mirrors what predict_shipping_cost() uses at inference time,
so feature columns and encodings here MUST stay in sync with agent/tools.py.

Call ensure_models_trained() on startup (idempotent — skips if .pkl files exist).
"""
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except Exception:
    # Catches both ImportError and XGBoostError (missing libomp on macOS)
    XGBOOST_AVAILABLE = False

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import COST_MODEL_PATH, TRANSIT_MODEL_PATH, DB_PATH


# ── Encoding maps — must match agent/tools.py ─────────────────────────────────
MODE_ENCODE = {"truck": 0, "rail": 1, "ocean": 2, "air": 3}
COUNTRY_ENCODE = {"China": 0, "Germany": 1, "Mexico": 2, "USA": 3}

# Canonical feature order — never reorder; joblib model depends on this
FEATURE_COLS = [
    "distance_miles",
    "units",
    "mode_truck",    # one-hot
    "mode_rail",
    "mode_ocean",
    "mode_air",
    "country_enc",
    "season",
    "congestion_factor",
    "base_cost_per_unit",
    "base_transit_days",
]


# ── Data loading ───────────────────────────────────────────────────────────────

def _load_training_data() -> pd.DataFrame:
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT
            s.actual_cost,
            s.actual_transit_days,
            s.units,
            s.congestion_factor,
            s.season,
            r.distance_miles,
            r.mode,
            r.base_cost_per_unit,
            r.transit_days AS base_transit_days,
            sup.country AS origin_country
        FROM shipments s
        JOIN routes r   ON r.id = s.route_id
        JOIN suppliers sup ON sup.id = r.origin_id
    """, conn)
    conn.close()
    return df


# ── Feature engineering ────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Convert raw shipment+route rows into model-ready feature matrix.
    One-hot encode mode; label-encode origin country.
    Returns (X, y_cost, y_transit).
    """
    df = df.copy()

    # One-hot encode mode
    for mode in ("truck", "rail", "ocean", "air"):
        df[f"mode_{mode}"] = (df["mode"] == mode).astype(int)

    df["country_enc"] = df["origin_country"].map(COUNTRY_ENCODE).fillna(3).astype(int)

    X = df[FEATURE_COLS].copy()
    y_cost    = df["actual_cost"]
    y_transit = df["actual_transit_days"]
    return X, y_cost, y_transit


def build_inference_row(
    distance_miles: float,
    units: int,
    mode: str,
    origin_country: str,
    season: int,
    congestion_factor: float,
    base_cost_per_unit: float,
    base_transit_days: float,
) -> pd.DataFrame:
    """
    Build a single-row feature DataFrame for inference.
    Used by agent/tools.py predict_shipping_cost().
    """
    row = {
        "distance_miles": distance_miles,
        "units": units,
        "mode_truck": int(mode == "truck"),
        "mode_rail": int(mode == "rail"),
        "mode_ocean": int(mode == "ocean"),
        "mode_air": int(mode == "air"),
        "country_enc": COUNTRY_ENCODE.get(origin_country, 3),
        "season": season,
        "congestion_factor": congestion_factor,
        "base_cost_per_unit": base_cost_per_unit,
        "base_transit_days": base_transit_days,
    }
    return pd.DataFrame([row], columns=FEATURE_COLS)


# ── Metrics ────────────────────────────────────────────────────────────────────

def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Percentage Error, clipping near-zero actuals."""
    mask = np.abs(y_true) > 1.0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def _print_metrics(label: str, y_test, preds, unit: str = "") -> dict:
    mae  = mean_absolute_error(y_test, preds)
    mape = _mape(np.array(y_test), np.array(preds))
    r2   = r2_score(y_test, preds)
    print(f"   {label:<20} MAE={unit}{mae:.2f}  MAPE={mape:.1f}%  R²={r2:.4f}")
    return {"mae": mae, "mape": mape, "r2": r2}


# ── Training ───────────────────────────────────────────────────────────────────

def train_cost_model(X: pd.DataFrame, y: pd.Series) -> tuple[object, dict]:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    if XGBOOST_AVAILABLE:
        model = XGBRegressor(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.04,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            reg_alpha=0.05,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
    else:
        from sklearn.ensemble import GradientBoostingRegressor
        model = GradientBoostingRegressor(n_estimators=300, max_depth=5, random_state=42)

    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    metrics = _print_metrics("Cost predictor", y_test, preds, unit="$")
    return model, metrics


def train_transit_model(X: pd.DataFrame, y: pd.Series) -> tuple[object, dict]:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=10,
        min_samples_leaf=4,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    metrics = _print_metrics("Transit estimator", y_test, preds, unit="")
    return model, metrics


# ── Public API ─────────────────────────────────────────────────────────────────

def ensure_models_trained() -> None:
    """
    Train and persist both models if .pkl files are missing.
    Safe to call on every startup — no-op if models already exist.
    """
    COST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if COST_MODEL_PATH.exists() and TRANSIT_MODEL_PATH.exists():
        print("✅  ML models already on disk — skipping training.")
        return

    print("🔧  Training ML models on 10,000 synthetic shipments …")
    df = _load_training_data()
    print(f"   Loaded {len(df):,} rows.")

    X, y_cost, y_transit = build_features(df)

    cost_model,    cost_metrics    = train_cost_model(X, y_cost)
    transit_model, transit_metrics = train_transit_model(X, y_transit)

    joblib.dump({"model": cost_model,    "metrics": cost_metrics,    "feature_cols": FEATURE_COLS}, COST_MODEL_PATH)
    joblib.dump({"model": transit_model, "metrics": transit_metrics, "feature_cols": FEATURE_COLS}, TRANSIT_MODEL_PATH)

    print(f"✅  Models saved → {COST_MODEL_PATH.parent}/")


def load_cost_model():
    """Load the saved cost model bundle from disk."""
    bundle = joblib.load(COST_MODEL_PATH)
    return bundle["model"]


def load_transit_model():
    """Load the saved transit model bundle from disk."""
    bundle = joblib.load(TRANSIT_MODEL_PATH)
    return bundle["model"]


def get_model_metrics() -> dict:
    """Return stored evaluation metrics for both models."""
    result = {}
    if COST_MODEL_PATH.exists():
        result["cost"] = joblib.load(COST_MODEL_PATH).get("metrics", {})
    if TRANSIT_MODEL_PATH.exists():
        result["transit"] = joblib.load(TRANSIT_MODEL_PATH).get("metrics", {})
    return result


if __name__ == "__main__":
    ensure_models_trained()
    print("\nStored metrics:", get_model_metrics())
