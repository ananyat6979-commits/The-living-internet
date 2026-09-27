"""Raw GH Archive -> normalized `events` table in DuckDB.

Design rules
------------
* We only read fields that exist in EVERY era of the archive (2015 -> now):
  id, type, created_at, actor.{id,login}, repo.{id,name}, payload.{action,ref_type}.
  The Oct-2025 payload trim removed commit counts, PR merge flags, author_association.
  We therefore count EVENTS, never "commits" or "merged PRs".
* Repo identity is repo.id (names change; ids don't). Falls back to a name hash only
  when id is absent (very old data).
* Every rejected/malformed row is counted. Publication logic can refuse a day whose
  reject rate is too high.
"""
from __future__ import annotations
import duckdb

# Explicit schema => stable across days (auto-detect can flip types between files).
_COLUMNS = """{
    'id': 'VARCHAR',
    'type': 'VARCHAR',
    'created_at': 'VARCHAR',
    'actor': 'STRUCT(id BIGINT, login VARCHAR)',
    'repo': 'STRUCT(id BIGINT, name VARCHAR)',
    'payload': 'STRUCT(action VARCHAR, ref_type VARCHAR)'
}"""


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("PRAGMA threads=4")
    return con


def count_lines(glob_pattern: str) -> int:
    """Count physical (newline-delimited) lines across every file matched by `glob_pattern`,
    without interpreting their content in any way.

    A prior version used read_csv() with a rare byte as a fake delimiter, purely to get a cheap
    count. Real GitHub issue/comment bodies are long free text and can legitimately contain any
    byte, including the one chosen, which crashed the whole pipeline on real data (the CSV parser
    saw an unexpected second "column" and raised). Counting lines is not a CSV problem, so this no
    longer goes through a CSV reader at all: it reads each file as raw bytes and counts newlines."""
    import glob as globmod
    import gzip
    total = 0
    for path in sorted(globmod.glob(glob_pattern)):
        with gzip.open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                total += chunk.count(b"\n")
    return total


def load_day(con, glob: str, date: str) -> dict:
    """Load one UTC day. Returns read/accepted/rejected accounting."""
    lines = count_lines(glob)

    con.execute("DROP TABLE IF EXISTS events")
    con.execute(f"""
        CREATE TABLE events AS
        SELECT
            id                                            AS event_id,
            type                                          AS event_type,
            CAST(created_at AS TIMESTAMP)                 AS ts,
            CAST(CAST(created_at AS TIMESTAMP) AS DATE)   AS day,
            EXTRACT(hour FROM CAST(created_at AS TIMESTAMP))::INTEGER AS hour,
            actor.id                                      AS actor_id,
            actor.login                                   AS actor_login,
            repo.id                                       AS repo_id,
            repo.name                                     AS repo_name,
            payload.action                                AS action,
            payload.ref_type                              AS ref_type
        FROM read_ndjson('{glob}', columns={_COLUMNS}, ignore_errors=true, compression='gzip')
        WHERE id IS NOT NULL AND type IS NOT NULL AND created_at IS NOT NULL
          AND repo.id IS NOT NULL AND repo.name IS NOT NULL
    """)
    # De-duplicate defensively (archives occasionally overlap at hour boundaries).
    con.execute("""
        CREATE OR REPLACE TABLE events AS
        SELECT DISTINCT ON (event_id) * FROM events ORDER BY event_id
    """)
    accepted_all = con.execute("SELECT count(*) FROM events").fetchone()[0]
    # Events whose timestamp falls on a different UTC day belong to that other day; keep them
    # out of THIS day's tables but account for them.
    off_day = con.execute("SELECT count(*) FROM events WHERE day <> CAST(? AS DATE)", [date]).fetchone()[0]
    con.execute("DELETE FROM events WHERE day <> CAST(? AS DATE)", [date])
    accepted = con.execute("SELECT count(*) FROM events").fetchone()[0]
    return {
        "lines_read": int(lines),
        "accepted": int(accepted),
        "off_day": int(off_day),
        "rejected": int(max(0, lines - accepted_all)),
    }
