# Alert Correlation & Deduplication Engine

Built by Team Hack-a-Throne for the HPE Synergy 2026 Hackathon.

Groups related infrastructure alerts using time + semantic clustering, identifies the most likely root cause within each cluster, and suppresses derivative alerts from the primary view — turning hundreds of raw alerts during an incident into a handful of actionable ones.

---

## Problem Statement

During a significant infrastructure incident, monitoring systems can generate hundreds or thousands of alerts within minutes — most of them downstream symptoms of a single root cause. This engine:

- Groups temporally and semantically related alerts using clustering algorithms
- Identifies the most likely root-cause alert within each cluster
- Suppresses derivative alerts from the primary view
- Visualizes the correlated view alongside the raw alert stream for comparison

## Datasets

- [Loghub](https://github.com/logpai/loghub) — real system log data (BGL dataset used for labeled alert/non-alert lines)
- [AIOps Challenge dataset](https://github.com/NetManAIOps/AIOps-Challenge-2020-Data) — real fault-injection data with ground-truth fault type, time, and location, used to validate root-cause detection

## Approach

1. **Log parsing** — raw log lines → structured templates via [Drain3](https://github.com/logpai/Drain3)
2. **Vectorization** — templates converted to vectors (TF-IDF) for semantic similarity
3. **Distance metric** — combined time-gap + semantic distance
4. **Clustering** — DBSCAN groups related alerts, leaves outliers unclustered
5. **Root cause detection** — earliest alert in each cluster flagged as likely root cause
6. **Dashboard** — raw stream vs. correlated incident view, side by side

> This project uses unsupervised clustering, not supervised model training — no labeled training set or model-fitting step is required for the core engine.

## Tech Stack

- Python (parsing, distance metric, clustering)
- scikit-learn (DBSCAN)
- Drain3 (log parsing)
- [Frontend framework — not decided yet] (dashboard)

## Setup & Run

```bash
git clone https://github.com/<your-username>/alert-correlation-dedup-engine.git
cd alert-correlation-dedup-engine
pip install -r requirements.txt

# run the pipeline
python src/parsing.py
python src/clustering.py
```

*(Update these commands as the actual scripts take shape.)*

## Project Status / Roadmap

- [ ] Log parsing pipeline (Drain3)
- [ ] Time + semantic distance function
- [ ] DBSCAN clustering
- [ ] Root cause heuristic
- [ ] Dashboard (raw vs. correlated view)
- [ ] Validation against AIOps Challenge ground truth

## Team

| Name | Role |
|---|---|
| | |
| | |
| | |
| | |

## License

MIT
