"""The Claim compiler: the ONLY place words are attached to numbers.

A Claim is a typed, sourced assertion. The story text shown to visitors is assembled
exclusively from Claims. The compiler REFUSES to build a claim whose verb is not permitted
for its epistemic class.

Epistemic classes
-----------------
OBSERVED       directly counted in the public event stream
DERIVED        arithmetic on observed values (ratios, percentiles, gaps)
INTERPRETATION restrained pattern language ("looks unusual")
UNKNOWN        what the stream cannot establish (motive, quality, privacy, location...)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict

CLASSES = ("observed", "derived", "interpretation", "unknown")

# Verbs/phrases we refuse in OBSERVED/DERIVED claims because the event stream cannot support them.
FORBIDDEN_IN_FACTS = [
    r"\bcommits?\b",            # payload commit counts were removed Oct 2025 -> we count push EVENTS
    r"\bmerged\b",              # PR merge flag removed
    r"\b(decided|wanted|chose|felt|hoped|realised|realized)\b",
    r"\b(abandon\w*|fail\w*|died|dead|revived|rescued)\b",
    r"\b(collaborat\w*|teamed|together)\b",     # co-presence != collaboration
    r"\b(flow state|worked all night|overnight|midnight)\b",   # UTC != local time
    r"\b(east asia|europe|north america|timezone|time zone|across the globe|worldwide)\b",  # no location data
    r"\b(genius|brilliant|important|best|top)\b",
]
_FORBID = [re.compile(p, re.I) for p in FORBIDDEN_IN_FACTS]


class ClaimError(ValueError):
    pass


@dataclass
class Claim:
    id: str
    cls: str                      # observed | derived | interpretation | unknown
    text: str                     # the sentence a visitor reads
    metric: str | None = None     # machine name, e.g. "events_today"
    value: float | int | str | None = None
    unit: str | None = None
    evidence: dict = field(default_factory=dict)   # how to re-derive it: table, filter, sql

    def __post_init__(self):
        if self.cls not in CLASSES:
            raise ClaimError(f"bad class {self.cls}")
        if self.cls in ("observed", "derived"):
            if self.metric is None or self.value is None:
                raise ClaimError(f"{self.id}: observed/derived claims must carry metric+value")
            if not self.evidence:
                raise ClaimError(f"{self.id}: observed/derived claims must carry evidence")
            for rx in _FORBID:
                if rx.search(self.text):
                    raise ClaimError(f"{self.id}: unsupported wording {rx.pattern!r} in {self.cls} claim: {self.text!r}")
        if self.cls == "unknown" and not re.search(r"\b(cannot|can't|does not|do not|don't|unknown|not observable|not shown)\b", self.text, re.I):
            raise ClaimError(f"{self.id}: 'unknown' claims must state a limit, got {self.text!r}")

    def to_dict(self):
        return asdict(self)


def fmt_int(n) -> str:
    return f"{int(round(n)):,}"


def fmt_fold(x: float) -> str:
    return f"{x:.0f}×" if x >= 10 else f"{x:.1f}×"


def plural(n, word: str, plural_word: str | None = None) -> str:
    """'1 account' / '2 accounts', without a caller having to remember every time."""
    n = int(n)
    return f"{fmt_int(n)} {word if n == 1 else (plural_word or word + 's')}"
