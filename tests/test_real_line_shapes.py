"""Regression: a real GH Archive file crashed pipeline.ingest.load_day with a DuckDB CSV parser
error ('Expected Number of Columns: 1 Found: 2') on an IssueCommentEvent whose body text happened
to contain a character the old line-counter used as a fake CSV delimiter. Real free-text fields
(issue/PR/comment bodies) can contain any byte, so counting lines must never go through a CSV
parser at all."""
import gzip, json
from pipeline import ingest

LONG_BODY = (
    "Sorry for another long one \u2014 this repo has clearly had a lot of careful work put into it, "
    "and I want to be upfront that some of this is source-reading rather than exhaustive testing.\n\n"
    "## Part 1\n\nA \"quoted\" phrase, a comma, a tab\there, and a backslash \\ for good measure.\n"
    "```rig\nMemFormat=%1.2b %3.1c\n```\n"
)


def _event(i: int) -> dict:
    return {"id": str(i), "type": "IssueCommentEvent",
            "actor": {"id": 6162075, "login": "adecarolis"},
            "repo": {"id": 1163603499, "name": "adecarolis/wfweb"},
            "payload": {"action": "created", "issue": {"number": 108, "body": LONG_BODY}},
            "created_at": "2026-09-22T00:05:41Z"}


def test_a_free_text_body_with_json_escaped_newlines_and_quotes_does_not_crash_the_line_counter(tmp_path):
    p = tmp_path / "2026-09-22-00.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps(_event(i)) + "\n")
    assert ingest.count_lines(str(p)) == 5             # 5 physical lines, regardless of what's inside them
    con = ingest.connect()
    acc = ingest.load_day(con, str(p), "2026-09-22")
    assert acc == {"lines_read": 5, "accepted": 5, "off_day": 0, "rejected": 0}


def test_count_lines_matches_accepted_when_every_row_is_well_formed(tmp_path):
    """The published `events` count and the printed `lines_read` must agree exactly in the normal
    case; count_lines is not an approximation."""
    p = tmp_path / "2026-09-22-01.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        for i in range(37):
            fh.write(json.dumps(_event(100 + i)) + "\n")
    con = ingest.connect()
    acc = ingest.load_day(con, str(p), "2026-09-22")
    assert acc["lines_read"] == 37 == acc["accepted"]
