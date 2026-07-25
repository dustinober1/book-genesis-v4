"""Burrows' Delta stylometric fingerprinting: does this manuscript measure
as the same "author" as a previous one?

The headline question this exists to answer: is a new manuscript closer, in
its function-word fingerprint, to the user's own writing (see
runner/corpus.py) than to a PREVIOUS manuscript this same pipeline wrote?
If every book this system produces converges toward one invisible house
voice, that is the single most damaging finding this whole project set out
to catch -- and nothing else in this package measures it.

That said, this is the least trustworthy module in runner/, and it says so
on every report it produces. Burrows' Delta needs a real reference set to
mean anything: a null simulation at n=2 references (target and both
references drawn from the SAME distribution) split winners 1004/996 across
2000 trials with a median margin of 1.2% -- it always confidently names a
winner, and that winner is a coin flip. Delta is also confounded by genre,
tense, POV, and dialogue ratio, which dominate function-word frequency far
more than authorial voice does -- a personal-writing corpus of present-tense
essays compared against two past-tense novels will always look "closer" to
whichever novel happens to share more incidental structure, regardless of
who wrote it.

Two guards follow from that:

1. No winner is named below MIN_REFERENCES_FOR_RANKING references. Below
   that floor this module reports raw, un-ranked deltas and says so
   explicitly -- it does not pretend the comparison means less than it does
   by staying silent, and it does not pretend it means more by naming a
   winner it cannot support.
2. Every report carries CONFOUND_NOTE, unconditionally. This is a hypothesis
   generator, not a verdict -- treat "closer to X than Y" as a prompt to
   read both, never as settled fact.

Profiles are cached as JSON in a small library directory (default
``~/.claude/book-genesis/fingerprints/``, override via
``BOOK_GENESIS_FINGERPRINT_DIR`` -- see paths.py's convention of resolving
roots via functions, not module constants, so tests can override cleanly)
so a user's prior books accumulate as reference points over time; the
comparison is only as good as that library eventually gets, which is why it
refuses to overclaim before the library has enough in it.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import statistics
from typing import Dict, List, Optional

from runner.discover import WORD

MIN_REFERENCES_FOR_RANKING = 6
DEFAULT_MFW_COUNT = 100

CONFOUND_NOTE = (
    "Burrows' Delta measures function-word frequency, which is confounded by "
    "genre, tense, POV, and dialogue ratio at least as much as by authorial "
    "voice. Treat any result here as a hypothesis to go read both texts "
    "against, never as a verdict."
)

_FINGERPRINT_DIR_ENV = "BOOK_GENESIS_FINGERPRINT_DIR"
_SLUG = re.compile(r"[^a-z0-9]+")


def default_library_dir() -> Path:
    override = os.environ.get(_FINGERPRINT_DIR_ENV)
    if override:
        return Path(override)
    return Path.home() / ".claude" / "book-genesis" / "fingerprints"


def _slugify(name: str) -> str:
    return _SLUG.sub("-", name.strip().lower()).strip("-") or "profile"


def _tokens(text: str) -> List[str]:
    return [w.lower() for w in WORD.findall(text)]


@dataclass
class FingerprintProfile:
    name: str
    total_words: int
    frequencies: Dict[str, float] = field(default_factory=dict)  # word -> per-1000-word rate


def build_profile(name: str, text: str) -> FingerprintProfile:
    tokens = _tokens(text)
    total = len(tokens)
    if total == 0:
        return FingerprintProfile(name=name, total_words=0, frequencies={})
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    freqs = {w: (c / total) * 1000.0 for w, c in counts.items()}
    return FingerprintProfile(name=name, total_words=total, frequencies=freqs)


def save_profile(profile: FingerprintProfile, *, library_dir: Optional[Path] = None) -> Path:
    library_dir = library_dir or default_library_dir()
    library_dir.mkdir(parents=True, exist_ok=True)
    path = library_dir / f"{_slugify(profile.name)}.json"
    path.write_text(json.dumps({
        "name": profile.name,
        "total_words": profile.total_words,
        "frequencies": profile.frequencies,
    }, indent=2), encoding="utf-8")
    return path


def load_profile(path: Path) -> FingerprintProfile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return FingerprintProfile(
        name=data["name"], total_words=data["total_words"], frequencies=data["frequencies"])


def load_library(library_dir: Optional[Path] = None) -> List[FingerprintProfile]:
    library_dir = library_dir or default_library_dir()
    if not library_dir.is_dir():
        return []
    return [load_profile(p) for p in sorted(library_dir.glob("*.json"))]


def _most_frequent_words(profiles: List[FingerprintProfile], *, count: int) -> List[str]:
    totals: Dict[str, float] = {}
    for p in profiles:
        for w, f in p.frequencies.items():
            totals[w] = totals.get(w, 0.0) + f
    return sorted(totals, key=lambda w: -totals[w])[:count]


@dataclass
class DeltaResult:
    reference: str
    delta: float  # NaN when too few references share variance to compute one


@dataclass
class FingerprintReport:
    target: str = ""
    n_references: int = 0
    deltas: List[DeltaResult] = field(default_factory=list)  # sorted, smallest first
    winner: Optional[str] = None  # only set when n_references >= MIN_REFERENCES_FOR_RANKING
    confound_note: str = CONFOUND_NOTE
    skipped: str = ""


def compare(
    target: FingerprintProfile,
    references: List[FingerprintProfile],
    *,
    mfw_count: int = DEFAULT_MFW_COUNT,
) -> FingerprintReport:
    if not references:
        return FingerprintReport(
            target=target.name,
            skipped="No reference profiles in the library yet -- nothing to compare against.")

    words = _most_frequent_words([target] + references, count=mfw_count)

    means: Dict[str, float] = {}
    stdevs: Dict[str, float] = {}
    usable_words: List[str] = []
    for w in words:
        values = [r.frequencies.get(w, 0.0) for r in references]
        sd = statistics.pstdev(values) if len(values) > 1 else 0.0
        if sd <= 0:
            continue  # zero-variance feature: would divide by zero, drop it
        means[w] = statistics.fmean(values)
        stdevs[w] = sd
        usable_words.append(w)

    def _zscores(p: FingerprintProfile) -> Dict[str, float]:
        return {w: (p.frequencies.get(w, 0.0) - means[w]) / stdevs[w] for w in usable_words}

    target_z = _zscores(target)
    deltas: List[DeltaResult] = []
    for r in references:
        if not usable_words:
            deltas.append(DeltaResult(reference=r.name, delta=float("nan")))
            continue
        ref_z = _zscores(r)
        d = sum(abs(target_z[w] - ref_z[w]) for w in usable_words) / len(usable_words)
        deltas.append(DeltaResult(reference=r.name, delta=d))

    deltas.sort(key=lambda d: (d.delta != d.delta, d.delta))  # NaN sorts last, not first

    report = FingerprintReport(target=target.name, n_references=len(references), deltas=deltas)
    if len(references) >= MIN_REFERENCES_FOR_RANKING and deltas and deltas[0].delta == deltas[0].delta:
        report.winner = deltas[0].reference
    return report


def render_report(report: FingerprintReport) -> str:
    lines = ["# Stylometric Fingerprint", ""]
    if report.skipped:
        lines.append(f"Skipped: {report.skipped}")
        return "\n".join(lines)

    lines.append(f"- Target: {report.target}")
    lines.append(f"- References in library: {report.n_references}")
    lines.append("")
    lines.append(f"> {report.confound_note}")
    lines.append("")

    if report.n_references < MIN_REFERENCES_FOR_RANKING:
        lines.append(
            f"**Fewer than {MIN_REFERENCES_FOR_RANKING} references in the library "
            "-- no winner named.** Raw deltas below (smallest = statistically "
            "nearest, but not a reliable ranking at this sample size):")
    else:
        lines.append(f"**Closest match: {report.winner}**")
    lines.append("")

    lines.append("| Reference | Delta (lower = closer) |")
    lines.append("|---|---|")
    for d in report.deltas:
        val = "n/a" if d.delta != d.delta else f"{d.delta:.3f}"
        lines.append(f"| {d.reference} | {val} |")
    lines.append("")

    return "\n".join(lines)
