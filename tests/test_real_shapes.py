"""Events shaped like the real GitHub Events API: large nested payloads, extra top-level keys, nulls.
The synthetic fixtures only carry the fields we read; these check that everything ELSE is ignored safely."""
import gzip, json
from pipeline import ingest

DAY = "2026-09-22"
URL = "https://api.github.com/repos/o/r"


def _base(i, typ, payload, repo_id=2, name="o/r", actor=(1, "alice"), ts=f"{DAY}T03:17:41Z"):
    return {"id": str(i), "type": typ,
            "actor": {"id": actor[0], "login": actor[1], "display_login": actor[1], "gravatar_id": "", "url": "https://api.github.com/users/x", "avatar_url": "https://avatars.githubusercontent.com/u/1?"},
            "repo": {"id": repo_id, "name": name, "url": URL},
            "payload": payload, "public": True, "created_at": ts,
            "org": {"id": 9, "login": "o", "gravatar_id": "", "url": "https://api.github.com/orgs/o", "avatar_url": "x"}}


PR = {"url": URL + "/pulls/5", "id": 77, "number": 5, "state": "open", "locked": False, "title": "t", "user": {"login": "a", "id": 1},
      "body": None, "labels": [{"name": "bug"}], "head": {"ref": "x", "repo": {"id": 3, "name": "f/r", "owner": {"login": "f"}}},
      "base": {"ref": "main", "repo": {"id": 2, "name": "r"}}, "merged": False, "mergeable": None, "comments": 0, "additions": 3, "deletions": 1}
EVENTS = [
    _base(1, "PushEvent", {"repository_id": 2, "push_id": 9, "size": 1, "distinct_size": 1, "ref": "refs/heads/main", "head": "a", "before": "b",
                           "commits": [{"sha": "s", "author": {"email": "e", "name": "n"}, "message": "m", "distinct": True, "url": URL}]}),
    _base(2, "PullRequestEvent", {"action": "opened", "number": 5, "pull_request": PR}),
    _base(3, "PullRequestEvent", {"action": "closed", "number": 5, "pull_request": {**PR, "merged": True}}),
    _base(4, "CreateEvent", {"ref": None, "ref_type": "repository", "master_branch": "main", "description": None, "pusher_type": "user"}),
    _base(5, "CreateEvent", {"ref": "feature", "ref_type": "branch", "master_branch": "main", "description": None, "pusher_type": "user"}),
    _base(6, "WatchEvent", {"action": "started"}),
    _base(7, "ForkEvent", {"forkee": {"id": 5, "name": "r", "full_name": "z/r", "owner": {"login": "z"}, "fork": True, "topics": []}}),
    _base(8, "IssuesEvent", {"action": "opened", "issue": {"number": 1, "title": "t", "labels": [], "user": {"login": "a"}}}),
    _base(9, "IssueCommentEvent", {"action": "created", "issue": {"number": 1}, "comment": {"id": 4, "body": "hi"}}),
    _base(10, "ReleaseEvent", {"action": "published", "release": {"tag_name": "v1", "assets": []}}),
    _base(11, "DeleteEvent", {"ref": "old", "ref_type": "branch", "pusher_type": "user"}),
    _base(12, "GollumEvent", {"pages": [{"page_name": "Home", "action": "edited"}]}),
    _base(13, "PublicEvent", {}),                                             # empty payload
    _base(14, "MemberEvent", {"action": "added", "member": {"login": "b"}}),
    _base(15, "SomeFutureEvent", {"anything": {"nested": [1, 2, 3]}, "action": None}),   # unknown type must not crash
]


def test_real_shaped_payloads_are_ignored_safely_and_fields_we_need_survive(tmp_path):
    p = tmp_path / f"{DAY}-03.json.gz"
    with gzip.open(p, "wt") as fh:
        for e in EVENTS: fh.write(json.dumps(e, separators=(",", ":")) + "\n")
    con = ingest.connect()
    acc = ingest.load_day(con, str(p), DAY)
    assert acc == {"lines_read": 15, "accepted": 15, "off_day": 0, "rejected": 0}
    got = {r[0]: r[1:] for r in con.execute("SELECT event_id, event_type, action, ref_type FROM events").fetchall()}
    assert got["2"] == ("PullRequestEvent", "opened", None) and got["3"] == ("PullRequestEvent", "closed", None)
    assert got["4"] == ("CreateEvent", None, "repository") and got["5"] == ("CreateEvent", None, "branch")
    assert got["6"][1] == "started" and got["10"][1] == "published"
    assert got["13"] == ("PublicEvent", None, None) and got["15"][0] == "SomeFutureEvent"


def test_windows_style_paths_in_globs_do_not_break_the_sql(tmp_path):
    """Windows paths contain backslashes and drive letters; they are embedded in SQL string literals."""
    d = tmp_path / "work" / "raw"; d.mkdir(parents=True)
    p = d / f"{DAY}-03.json.gz"
    with gzip.open(p, "wt") as fh: fh.write(json.dumps(EVENTS[0]) + "\n")
    con = ingest.connect()
    assert ingest.load_day(con, str(d / f"{DAY}-*.json.gz"), DAY)["accepted"] == 1


def test_free_text_containing_arbitrary_bytes_does_not_crash_line_counting(tmp_path):
    """Regression: the line counter used to fake a CSV read with a rare byte as the delimiter. Real
    GitHub issue/comment bodies are long free text and can contain any byte, including that one, which
    crashed ingestion entirely on real data (DuckDB's CSV parser saw a second 'column' and raised)."""
    import gzip, json
    body_with_the_byte = "line one\x01line two, still one JSON string value"
    ev = _base(1, "IssueCommentEvent", {"action": "created", "comment": {"id": 1, "body": body_with_the_byte}})
    p = tmp_path / f"{DAY}-04.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(ev) + "\n")
        fh.write(json.dumps(_base(2, "PushEvent", {})) + "\n")
    n = ingest.count_lines(str(tmp_path / f"{DAY}-*.json.gz"))
    assert n == 2
    con = ingest.connect()
    acc = ingest.load_day(con, str(tmp_path / f"{DAY}-*.json.gz"), DAY)
    assert acc == {"lines_read": 2, "accepted": 2, "off_day": 0, "rejected": 0}
