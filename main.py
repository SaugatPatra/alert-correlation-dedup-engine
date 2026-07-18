"""
PageZero API - serves the cached correlation pipeline result.
Run locally with:  uvicorn main:app --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from pipeline import run_pipeline

app = FastAPI(title="PageZero API")

# CORS wide open - read-only, non-sensitive data, called server-to-server
# by the Next.js frontend during server-side rendering.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_data() -> pd.DataFrame:
    return run_pipeline()


def _paginate(df: pd.DataFrame, page: int, page_size: int):
    start = (page - 1) * page_size
    end = start + page_size
    return df.iloc[start:end]


@app.get("/")
def root():
    return {"service": "pagezero-backend", "status": "ok"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}


@app.get("/api/stats")
def stats():
    df = _get_data()
    raw_count = len(df)
    incident_count = df["cluster_id"].nunique()
    reduction_pct = round((1 - incident_count / raw_count) * 100, 1) if raw_count else 0
    return {
        "raw_alert_count": raw_count,
        "incident_count": incident_count,
        "reduction_pct": reduction_pct,
        "critical_incidents": int((df[df["is_root"]]["cluster_severity"] == 4).sum()),
    }


@app.get("/api/clusters")
def list_clusters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str = Query("", description="Filter by node or message text"),
):
    df = _get_data()
    roots = df[df["is_root"]].copy()

    if search:
        s = search.lower()
        roots = roots[
            roots["Node"].str.lower().str.contains(s)
            | roots["clean_content"].str.lower().str.contains(s)
        ]

    roots = roots.sort_values("unix")
    total = len(roots)
    page_df = _paginate(roots, page, page_size)

    items = []
    for _, row in page_df.iterrows():
        member_count = int((df["cluster_id"] == row["cluster_id"]).sum()) if row["cluster_id"] != -1 else 1
        items.append({
            "cluster_id": int(row["cluster_id"]),
            "root_node": row["Node"],
            "root_message": row["Content"],
            "timestamp": str(row["timestamp"]),
            "severity": int(row["cluster_severity"]),
            "member_count": member_count,
        })

    return {"total": total, "page": page, "page_size": page_size, "clusters": items}


@app.get("/api/clusters/{cluster_id}")
def cluster_detail(cluster_id: int):
    df = _get_data()
    group = df[df["cluster_id"] == cluster_id]
    if group.empty:
        raise HTTPException(status_code=404, detail="Cluster not found")

    members = [
        {
            "node": r["Node"],
            "component": r["Component"],
            "level": r["Level"],
            "message": r["Content"],
            "timestamp": str(r["timestamp"]),
            "is_root": bool(r["is_root"]),
            "suppressed": bool(r["suppressed"]),
        }
        for _, r in group.sort_values("unix").iterrows()
    ]
    return {"cluster_id": cluster_id, "member_count": len(members), "members": members}


@app.get("/api/alerts")
def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    search: str = Query(""),
    surfaced_only: bool = Query(False, description="Only alerts that are root causes (not suppressed)"),
):
    df = _get_data()
    alerts = df.copy()

    if surfaced_only:
        alerts = alerts[alerts["is_root"]]

    if search:
        s = search.lower()
        alerts = alerts[
            alerts["Node"].str.lower().str.contains(s)
            | alerts["clean_content"].str.lower().str.contains(s)
        ]

    alerts = alerts.sort_values("unix")
    total = len(alerts)
    page_df = _paginate(alerts, page, page_size)

    items = [
        {
            "node": r["Node"],
            "component": r["Component"],
            "level": r["Level"],
            "message": r["Content"],
            "timestamp": str(r["timestamp"]),
            "cluster_id": int(r["cluster_id"]),
            "is_root": bool(r["is_root"]),
            "suppressed": bool(r["suppressed"]),
        }
        for _, r in page_df.iterrows()
    ]
    return {"total": total, "page": page, "page_size": page_size, "alerts": items}


@app.get("/api/timeline")
def timeline(granularity: str = Query("hourly", pattern="^(hourly|daily|weekly)$")):
    df = _get_data().copy()
    freq_map = {"hourly": "h", "daily": "D", "weekly": "W"}
    freq = freq_map[granularity]

    df["bucket"] = df["timestamp"].dt.floor(freq)
    raw_counts = df.groupby("bucket").size()
    surfaced_counts = df[df["is_root"]].groupby("bucket").size()

    buckets = sorted(set(raw_counts.index) | set(surfaced_counts.index))
    return {
        "granularity": granularity,
        "points": [
            {
                "bucket": str(b),
                "raw_count": int(raw_counts.get(b, 0)),
                "surfaced_count": int(surfaced_counts.get(b, 0)),
            }
            for b in buckets
        ],
    }


@app.get("/api/components")
def components():
    df = _get_data()
    counts = df["Component"].value_counts()
    return {"components": [{"name": k, "count": int(v)} for k, v in counts.items()]}


@app.get("/api/severity")
def severity():
    df = _get_data()
    counts = df["Level"].value_counts()
    return {"severity": [{"level": k, "count": int(v)} for k, v in counts.items()]}
