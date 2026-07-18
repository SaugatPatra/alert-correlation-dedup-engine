"""
PageZero correlation pipeline.

Stages:
  1. load_raw()     - read + clean the BGL structured CSV
  2. vectorize()     - TF-IDF text vectors + pairwise cosine distance
  3. cluster()        - dual-signal (time AND text) DBSCAN clustering
  4. build_clusters()  - pick root cause per cluster, mark suppressed alerts
  5. run_pipeline()     - orchestrate + cache the result in memory

This module has no I/O beyond reading the CSV - it's meant to be imported
by main.py (the FastAPI app) and called once, then served from cache.
"""

import re
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_distances
from sklearn.cluster import DBSCAN

# ---------------- CONFIG ----------------
DATA_PATH = Path(__file__).parent / "data" / "BGL_2k.log_structured.csv"
TIME_WINDOW_SECONDS = 300     # alerts must be within 5 min to even be considered
TEXT_DISTANCE_EPS = 0.35      # DBSCAN eps - max TF-IDF cosine distance to be neighbors
MIN_SAMPLES = 2               # need at least 2 alerts to form a real cluster
UNREACHABLE_DISTANCE = 1000.0 # forces DBSCAN to never bridge alerts outside the time window

SEVERITY_MAP = {"INFO": 1, "WARNING": 2, "ERROR": 3, "FATAL": 4}

_cache = {}


def _clean_text(text: str) -> str:
    """Lowercase + strip hex addresses, IPs, and bare numbers so that two
    alerts of the same *type* with different variable data (an address,
    an IP, a core-dump id) are recognized as textually similar."""
    if pd.isna(text):
        return "—"
    text = str(text).lower()
    text = re.sub(r"0x[0-9a-f]+", " ", text)                       # hex addresses
    text = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", " ", text)          # IPv4 addresses
    text = re.sub(r"\b\d+\b", " ", text)                             # bare numbers
    text = re.sub(r"\s+", " ", text).strip()
    return text or "—"


def load_raw(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]

    # --- timestamps ---
    # loghub BGL structured csv has a `Time` column like 2005-06-03-15.42.50.675872
    if "Time" in df.columns:
        parsed = pd.to_datetime(
            df["Time"].astype(str).str.replace(
                r"(\d{4}-\d{2}-\d{2})-(\d{2})\.(\d{2})\.(\d{2})\.(\d+)",
                r"\1 \2:\3:\4.\5", regex=True
            ),
            errors="coerce",
        )
        df["timestamp"] = parsed
        # Version-safe: don't assume ns vs us precision (pandas 2.x vs 3.x differ) -
        # compute seconds-since-epoch via direct subtraction instead of astype(int64).
        df["unix"] = (parsed - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
    else:
        # fall back to the raw epoch Timestamp column if present
        df["unix"] = pd.to_numeric(df.get("Timestamp"), errors="coerce")
        df["timestamp"] = pd.to_datetime(df["unix"], unit="s", errors="coerce")

    # --- ground truth flag (never used by clustering, only for later validation) ---
    df["is_anomaly"] = df.get("Label", "-").astype(str) != "-"

    # --- fill missing fields ---
    for col in ["Node", "Component", "Level", "Content"]:
        if col not in df.columns:
            df[col] = "—"
        df[col] = df[col].fillna("—")

    # --- clean text for similarity comparison ---
    df["clean_content"] = df["Content"].apply(_clean_text)

    # --- severity ---
    df["severity_rank"] = df["Level"].map(SEVERITY_MAP).fillna(1).astype(int)

    df = df.dropna(subset=["unix"]).reset_index(drop=True)
    return df


def vectorize(df: pd.DataFrame):
    vectorizer = TfidfVectorizer(min_df=1, max_df=0.9, ngram_range=(1, 2))
    tfidf = vectorizer.fit_transform(df["clean_content"])
    text_dist = cosine_distances(tfidf)
    return tfidf, text_dist


def cluster(df: pd.DataFrame, text_dist: np.ndarray) -> np.ndarray:
    unix = df["unix"].to_numpy()
    time_gap = np.abs(unix[:, None] - unix[None, :])
    within_window = time_gap <= TIME_WINDOW_SECONDS

    combined = np.where(within_window, text_dist, UNREACHABLE_DISTANCE)

    model = DBSCAN(eps=TEXT_DISTANCE_EPS, min_samples=MIN_SAMPLES, metric="precomputed")
    labels = model.fit_predict(combined)
    return labels


def build_clusters(df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    df = df.copy()
    df["cluster_id"] = labels
    df["is_root"] = False
    df["suppressed"] = False
    df["cluster_severity"] = df["severity_rank"]

    for cid, group in df.groupby("cluster_id"):
        if cid == -1:
            # noise points: each alert stands alone, always a root cause
            df.loc[group.index, "is_root"] = True
            continue

        root_idx = group["unix"].idxmin()
        df.loc[root_idx, "is_root"] = True
        other_idx = group.index.difference([root_idx])
        df.loc[other_idx, "suppressed"] = True

        max_severity = group["severity_rank"].max()
        df.loc[group.index, "cluster_severity"] = max_severity

    return df


def run_pipeline(force: bool = False) -> pd.DataFrame:
    """Run the full pipeline once and cache the result in memory."""
    if not force and "result" in _cache:
        return _cache["result"]

    df = load_raw()
    _, text_dist = vectorize(df)
    labels = cluster(df, text_dist)
    result = build_clusters(df, labels)

    _cache["result"] = result
    return result


def clear_cache():
    _cache.clear()
