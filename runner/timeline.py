"""Chronology validator.

Catches the arithmetic contradictions a reader notices and a drafting model does
not: ages that imply two different birth years, stated intervals that disagree
with their anchors, events asserted twice at different points, and day counts
that cannot fit the span they are placed in.

Authoring format is a flat record syntax - deliberately not nested YAML, so it
parses deterministically with no dependencies and stays easy to hand-edit.

    # TIMELINE.md  (or TIMELINE.txt)
    event  id=yonah_death      day=-3650   label="Yonah dies"
    event  id=story_open       day=0       label="Chapter 1 opens"
    event  id=last_supper      day=120     label="The supper"
    event  id=crucifixion      day=121     label="Crucifixion"

    age    person=john_mark    at=yonah_death   years=9    src="Ch1"
    age    person=john_mark    at=story_open    years=19   src="Ch1"

    span   from=yonah_death    to=story_open    stated=9y  src="Ch1 'dead nine years'"
    span   from=last_supper    to=crucifixion   stated=1d  src="Ch5"

    once   id=barnabas_sells_field  at=post_pentecost  src="Ch9"

Every assertion carries `src` so a failure points at the chapter to fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional

DAYS_PER_YEAR = 365.25

# Tolerance for age arithmetic. A person stated as 9 at one event and 19 at
# another 10 years later is consistent; birthdays make exact matching wrong.
AGE_TOLERANCE_YEARS = 1.0

RECORD = re.compile(r"^\s*(\w+)\s+(.*)$")
PAIR = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\S+)')
DURATION = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([dwmy])\s*$", re.IGNORECASE)


@dataclass
class Event:
    id: str
    day: float
    label: str = ""
    src: str = ""


@dataclass
class AgeClaim:
    person: str
    at: str
    years: float
    src: str = ""


@dataclass
class SpanClaim:
    frm: str
    to: str
    stated_days: float
    stated_raw: str
    src: str = ""


@dataclass
class OnceClaim:
    id: str
    at: str
    src: str = ""


@dataclass
class TimelineIssue:
    kind: str
    severity: str          # "fail" | "warn"
    message: str
    sources: List[str] = field(default_factory=list)


@dataclass
class Timeline:
    events: Dict[str, Event] = field(default_factory=dict)
    ages: List[AgeClaim] = field(default_factory=list)
    spans: List[SpanClaim] = field(default_factory=list)
    onces: List[OnceClaim] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_duration(raw: str) -> Optional[float]:
    """Return days. Accepts 9y, 14d, 3w, 2m, or a bare number (days)."""
    m = DURATION.match(raw)
    if m:
        n, unit = float(m.group(1)), m.group(2).lower()
        return n * {"d": 1.0, "w": 7.0, "m": 30.44, "y": DAYS_PER_YEAR}[unit]
    try:
        return float(raw)
    except ValueError:
        return None


def parse_timeline(text: str) -> Timeline:
    tl = Timeline()
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = RECORD.match(stripped)
        if not m:
            tl.parse_errors.append(f"line {lineno}: unparsable: {stripped}")
            continue
        kind, rest = m.group(1).lower(), m.group(2)
        kv = {k: _unquote(v) for k, v in PAIR.findall(rest)}

        try:
            if kind == "event":
                day = parse_duration(kv.get("day", ""))
                if day is None:
                    tl.parse_errors.append(f"line {lineno}: event needs numeric day=")
                    continue
                eid = kv["id"]
                if eid in tl.events:
                    tl.parse_errors.append(f"line {lineno}: duplicate event id {eid!r}")
                    continue
                tl.events[eid] = Event(eid, day, kv.get("label", ""), kv.get("src", ""))
            elif kind == "age":
                tl.ages.append(AgeClaim(
                    kv["person"], kv["at"], float(kv["years"]), kv.get("src", "")))
            elif kind == "span":
                days = parse_duration(kv.get("stated", ""))
                if days is None:
                    tl.parse_errors.append(f"line {lineno}: span needs stated=")
                    continue
                tl.spans.append(SpanClaim(
                    kv["from"], kv["to"], days, kv.get("stated", ""), kv.get("src", "")))
            elif kind == "once":
                tl.onces.append(OnceClaim(kv["id"], kv["at"], kv.get("src", "")))
            else:
                tl.parse_errors.append(f"line {lineno}: unknown record type {kind!r}")
        except KeyError as exc:
            tl.parse_errors.append(f"line {lineno}: {kind} missing field {exc}")
        except ValueError as exc:
            tl.parse_errors.append(f"line {lineno}: {kind} bad value ({exc})")

    return tl


def validate(tl: Timeline) -> List[TimelineIssue]:
    issues: List[TimelineIssue] = []

    for err in tl.parse_errors:
        issues.append(TimelineIssue("parse", "fail", err))

    def known(eid: str) -> bool:
        return eid in tl.events

    # -- unresolved references -------------------------------------------
    for a in tl.ages:
        if not known(a.at):
            issues.append(TimelineIssue(
                "unknown_event", "fail",
                f"age claim for {a.person!r} references undefined event {a.at!r}",
                [a.src]))
    for s in tl.spans:
        for eid in (s.frm, s.to):
            if not known(eid):
                issues.append(TimelineIssue(
                    "unknown_event", "fail",
                    f"span references undefined event {eid!r}", [s.src]))
    for o in tl.onces:
        if not known(o.at):
            issues.append(TimelineIssue(
                "unknown_event", "fail",
                f"once-claim {o.id!r} references undefined event {o.at!r}", [o.src]))

    # -- age consistency (findings 2, 14) ---------------------------------
    by_person: Dict[str, List[AgeClaim]] = {}
    for a in tl.ages:
        if known(a.at):
            by_person.setdefault(a.person, []).append(a)

    for person, claims in by_person.items():
        claims = sorted(claims, key=lambda c: tl.events[c.at].day)
        for i in range(len(claims) - 1):
            c1, c2 = claims[i], claims[i + 1]
            elapsed_years = (tl.events[c2.at].day - tl.events[c1.at].day) / DAYS_PER_YEAR
            implied = c2.years - c1.years
            drift = abs(implied - elapsed_years)
            if drift > AGE_TOLERANCE_YEARS:
                issues.append(TimelineIssue(
                    "age_contradiction", "fail",
                    f"{person}: aged {c1.years:.0f}->{c2.years:.0f} "
                    f"({implied:+.0f}y) across {elapsed_years:.1f}y "
                    f"between {c1.at!r} and {c2.at!r} - off by {drift:.1f}y",
                    [s for s in (c1.src, c2.src) if s]))

    # -- stated span vs anchors (findings 3, 9, 10) -----------------------
    for s in tl.spans:
        if not (known(s.frm) and known(s.to)):
            continue
        actual = tl.events[s.to].day - tl.events[s.frm].day
        # Tolerance scales with magnitude: exact for day-level Passion Week
        # claims, a year of slack on decade-long spans.
        tol = 0.5 if abs(s.stated_days) < 60 else DAYS_PER_YEAR / 2
        if abs(actual - s.stated_days) > tol:
            issues.append(TimelineIssue(
                "span_contradiction", "fail",
                f"stated {s.stated_raw} between {s.frm!r} and {s.to!r}, "
                f"but anchors are {actual:.0f}d apart "
                f"({actual / DAYS_PER_YEAR:.1f}y)",
                [s.src]))
        if actual < 0:
            issues.append(TimelineIssue(
                "reversed_span", "fail",
                f"{s.to!r} precedes {s.frm!r} - span runs backwards", [s.src]))

    # -- event asserted twice (finding 4: Barnabas sells the field twice) --
    seen: Dict[str, List[OnceClaim]] = {}
    for o in tl.onces:
        seen.setdefault(o.id, []).append(o)
    for oid, claims in seen.items():
        anchors = {c.at for c in claims if known(c.at)}
        if len(anchors) > 1:
            issues.append(TimelineIssue(
                "duplicate_occurrence", "fail",
                f"{oid!r} is asserted to occur at {len(anchors)} different points: "
                f"{', '.join(sorted(anchors))} - a once-only event happens once",
                [c.src for c in claims if c.src]))

    return issues


def render_issues(tl: Timeline, issues: List[TimelineIssue]) -> str:
    lines = ["# Chronology Check", ""]
    lines.append(f"- Events: {len(tl.events)}")
    lines.append(f"- Age claims: {len(tl.ages)}")
    lines.append(f"- Stated spans: {len(tl.spans)}")
    lines.append(f"- Once-only events: {len(tl.onces)}")
    lines.append("")

    fails = [i for i in issues if i.severity == "fail"]
    lines.append(f"**Verdict: {'FAIL' if fails else 'PASS'}** ({len(fails)} contradictions)")
    lines.append("")

    if not issues:
        lines.append("Timeline is internally consistent.")
        return "\n".join(lines)

    for i in issues:
        src = f"  _(source: {'; '.join(s for s in i.sources if s)})_" if any(i.sources) else ""
        lines.append(f"- **{i.kind}** — {i.message}{src}")

    lines.append("")
    lines.append("Fix the timeline sheet and the prose together. Do not revise "
                 "prose until this reports PASS.")
    return "\n".join(lines)


def check_timeline_file(path: Path) -> tuple[Timeline, List[TimelineIssue]]:
    tl = parse_timeline(path.read_text(encoding="utf-8"))
    return tl, validate(tl)


TIMELINE_NAMES = ("TIMELINE.md", "TIMELINE.txt", "artifacts/TIMELINE.md")


def find_timeline(root: Path) -> Optional[Path]:
    """Locate a project's TIMELINE file at one of the conventional paths."""
    for name in TIMELINE_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None
