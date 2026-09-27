# Architecture

```
GH Archive hourly .json.gz ──► source.py   all 24 or nothing · gzip-verified · sha256
                                 │
                                 ▼
                              ingest.py    DuckDB, explicit schema, every reject counted
                                 │
                                 ▼
                              ledger.py    one Parquet row per (repo_id, day)  ──►  Release asset (durable) + Actions cache
                                 │
                 ┌───────────────┴────────────────┐
                 ▼                                ▼
              detect.py  (SQL over ledger)     pulse.py (latest complete hours)
                 │
                 ▼
              stories.py + claims.py   words only via compiled claims; automation set aside
                 │
                 ▼
              publish.py   validate → stage → atomic swap · worlds/<day> (14 kept) · archive index
                 │
                 ▼
   site/public/data/*.json ─► Vite build ─► GitHub Pages     (previous data restored from the `data` branch each run)
```

## Invariants (each has a test)

1. Incomplete or >1% unparseable day ⇒ nothing is published.
2. Same source bytes + same versions ⇒ byte-identical output.
3. Every observed/derived claim carries evidence; forbidden wording raises.
4. Unobserved days are `null`, never `0`.
5. Every evidence event id exists in the archive file it cites.
6. Story repo is always on the world map; chart gap == stated silent days.
7. The UI renders data only as text nodes; only GitHub-grammar repo names become links.
8. Synthetic data is banner-labelled and CI refuses to deploy it.
