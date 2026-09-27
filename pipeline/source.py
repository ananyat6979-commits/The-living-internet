"""Acquire one UTC day of GH Archive, verifiably.

Invariants
----------
1. A day is either COMPLETE (all 24 hourly files present, gzip-valid, non-empty)
   or it is not processed at all. There is no "mostly".
2. Every file is hashed; the hashes ship with the published snapshot.
3. Nothing is silently dropped: parse rejects are counted per hour and reported.
"""
from __future__ import annotations
import gzip, hashlib, time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import BASE_URL, RAW

UA = "living-internet/1.0 (+https://github.com; static data documentary)"


class IncompleteDay(RuntimeError):
    def __init__(self, date: str, missing: list[int]):
        super().__init__(f"{date}: {24 - len(missing)}/24 hourly archives available; missing hours {missing}")
        self.date, self.missing = date, missing


@dataclass
class HourFile:
    hour: int
    path: Path
    sha256: str
    bytes: int


@dataclass
class SourceDay:
    date: str
    files: list[HourFile] = field(default_factory=list)

    @property
    def manifest(self) -> list[dict]:
        return [{"hour": f.hour, "sha256": f.sha256, "bytes": f.bytes} for f in self.files]

    def glob(self) -> str:
        return str(RAW / f"{self.date}-*.json.gz")


def url_for(date: str, hour: int) -> str:
    # GH Archive uses an UNPADDED hour: 2026-09-22-5.json.gz
    return f"{BASE_URL}/{date}-{hour}.json.gz"


def path_for(date: str, hour: int) -> Path:
    # Local names are zero-padded so a lexical glob sorts hours correctly.
    return RAW / f"{date}-{hour:02d}.json.gz"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gzip_ok(p: Path) -> bool:
    """Full-stream integrity check (reads to EOF, catching truncation, not just a bad header)."""
    try:
        with gzip.open(p, "rb") as fh:
            while fh.read(1 << 20):
                pass
        return p.stat().st_size > 0
    except (OSError, EOFError):
        return False


def fetch_hour(date: str, hour: int, *, retries: int = 4, opener=urlopen) -> Path | None:
    """Download one hour with backoff. Returns None if it cannot be obtained/validated."""
    RAW.mkdir(parents=True, exist_ok=True)
    out = path_for(date, hour)
    if out.exists() and _gzip_ok(out):
        return out
    tmp = out.with_suffix(".part")
    for attempt in range(retries):
        try:
            req = Request(url_for(date, hour), headers={"User-Agent": UA})
            with opener(req, timeout=120) as r, tmp.open("wb") as fh:
                while chunk := r.read(1 << 20):
                    fh.write(chunk)
            if _gzip_ok(tmp):
                tmp.replace(out)
                return out
        except (HTTPError, URLError, OSError, TimeoutError):
            pass
        finally:
            if tmp.exists() and not out.exists():
                tmp.unlink(missing_ok=True)
        time.sleep(min(60, 3 * 2 ** attempt))
    return None


def acquire_day(date: str, *, fetch=fetch_hour) -> SourceDay:
    """All 24 hours or raise IncompleteDay. `fetch` is injectable for tests."""
    day, missing = SourceDay(date), []
    for h in range(24):
        p = fetch(date, h)
        if p is None:
            missing.append(h)
            continue
        day.files.append(HourFile(h, p, _sha256(p), p.stat().st_size))
    if missing:
        raise IncompleteDay(date, missing)
    return day
