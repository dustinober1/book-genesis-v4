"""Calibrate lint against the author's own writing, not a stranger's.

lint.py's Thresholds are seeded from one editorial report on one 23,800-word
historical novella (see lint.py's module docstring). Useful defaults, but
they encode that book's tics and that editor's calibration -- not this
author's. This module ingests a directory of the author's own prior writing
(journal entries, old drafts, published work -- anything genuinely theirs)
and produces two things:

- `work/baseline-report.md` -- the actual deliverable: a metric-by-metric
  comparison of how THIS manuscript's measured prose differs from how this
  author actually writes. A human reads this; nothing here is a gate.
- `style-profile.suggested.yaml` -- candidate lint threshold overrides
  derived from the corpus, in the format runner/styleprofile.py reads.
  Never written to the active `style-profile.yaml` directly and never
  applied invisibly -- the "suggested" name and a required rename/copy step
  are the review gate. See render_style_profile in runner/styleprofile.py.

Derived overrides are tightening-only by default: a threshold is only
suggested when it would make the genre default STRICTER (closer to zero
tolerance), never looser, unless the caller explicitly passes
allow_loosen=True. Calibrating on a corpus of unknown genre (an author's
essays, say) could otherwise loosen a novel's dialogue-ratio band without
anyone deciding that was wanted -- see the module's own warning path for
exactly that mismatch.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from runner.discover import (
    WORD,
    adverb_density,
    dialogue_ratio,
    dialogue_tag_counts,
    flesch_kincaid_grade,
    strip_comments,
)
from runner.lint import (
    FILTER_FOUND_SELF,
    FILTER_WORD,
    NOT_X_BUT_Y,
    Thresholds,
)

MIN_CORPUS_WORDS = 1_000
LOW_CORPUS_WORDS = 5_000

# Genre-mismatch warning bands: how far a corpus's own dialogue ratio or FK
# grade can sit outside the project's genre band before we warn that the
# corpus may not be representative of what this book needs. Essays (near-zero
# dialogue) calibrated against a dialogue-heavy thriller is exactly the
# mismatch this exists to catch.
DIALOGUE_MISMATCH_MARGIN = 0.20
FK_MISMATCH_MARGIN = 3.0

# Which Thresholds fields this module knows how to derive from a corpus, and
# a safety margin applied to the corpus's own measured rate before it
# becomes a candidate override -- a personal baseline of exactly the corpus's
# observed density would flag the corpus's own median usage half the time.
#
# Every field here is a single-value CEILING (lower = stricter) with a
# matching per-1k-or-10k CorpusStats field of the identical shape --
# fk_grade/dialogue_ratio are deliberately excluded even though
# compute_stats reports them, because those are two-sided BANDS
# (fk_grade_min/max, dialogue_ratio_min/max), and this function's
# "candidate < default -> apply" logic is ceiling-only: forcing one
# corpus's single measured value to become both a stricter min AND a
# stricter max would silently narrow the band around wherever the author's
# prose happens to sit, which is a design mismatch, not a calibration. The
# mismatch check for those two lives in build_baseline_report's warnings
# instead (DIALOGUE_MISMATCH_MARGIN / FK_MISMATCH_MARGIN below).
_MARGIN = 1.25
_DERIVABLE_FIELDS: Tuple[str, ...] = (
    "em_dash_per_1k", "adverb_per_1k", "filter_word_per_1k", "not_x_but_y_per_10k",
)


@dataclass
class CorpusStats:
    total_words: int
    em_dash_per_1k: float
    adverb_per_1k: float
    filter_word_per_1k: float
    not_x_but_y_per_10k: float
    dialogue_ratio: float
    fk_grade: float
    said_tag_share: Optional[float]  # None when too little dialogue to judge


def compute_stats(text: str) -> CorpusStats:
    stripped = strip_comments(text)
    words = WORD.findall(stripped)
    total = len(words)
    per_1k = max(total / 1000.0, 0.001)
    per_10k = max(total / 10000.0, 0.0001)

    em = stripped.count("—") + stripped.count("--")
    adverb_n, adverb_total = adverb_density(stripped)
    adverb_1k = (adverb_n / (adverb_total / 1000.0)) if adverb_total else 0.0
    filter_n = len(FILTER_WORD.findall(stripped)) + len(FILTER_FOUND_SELF.findall(stripped))
    nxby_n = len(NOT_X_BUT_Y.findall(stripped))

    tag_counts = dialogue_tag_counts(stripped)
    total_tags = sum(tag_counts.values())
    said_share = (
        (tag_counts.get("said", 0) + tag_counts.get("asked", 0)) / total_tags
        if total_tags else None
    )

    return CorpusStats(
        total_words=total,
        em_dash_per_1k=em / per_1k,
        adverb_per_1k=adverb_1k,
        filter_word_per_1k=filter_n / per_1k,
        not_x_but_y_per_10k=nxby_n / per_10k,
        dialogue_ratio=dialogue_ratio(stripped),
        fk_grade=flesch_kincaid_grade(stripped),
        said_tag_share=said_share,
    )


def load_corpus_text(corpus_dir: Path) -> str:
    files = sorted(
        p for p in corpus_dir.glob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}
    )
    return "\n\n".join(p.read_text(encoding="utf-8") for p in files)


@dataclass
class BaselineReport:
    corpus: Optional[CorpusStats] = None
    manuscript: Optional[CorpusStats] = None
    warnings: List[str] = field(default_factory=list)
    derived_overrides: Dict[str, float] = field(default_factory=dict)
    skipped: str = ""


def derive_overrides(
    corpus: CorpusStats, *, profile: str = "", allow_loosen: bool = False,
) -> Tuple[Dict[str, float], List[str]]:
    """Candidate Thresholds overrides from the corpus's own measured rates.

    Only the two fields in _DERIVABLE_FIELDS are touched -- they are the
    clearest "personal tic density" metrics available from a corpus with no
    guaranteed dialogue or genre-fit. A candidate is included only when it
    is STRICTER than the genre default (lower ceiling), unless
    allow_loosen=True; a looser candidate is reported as a warning instead
    of silently adopted, since a permissive corpus calibrating a stricter
    genre's gate looser is exactly the failure mode this function exists to
    avoid.
    """
    base = Thresholds.for_profile(profile)
    overrides: Dict[str, float] = {}
    warnings: List[str] = []

    for field_name in _DERIVABLE_FIELDS:
        measured = getattr(corpus, field_name)
        candidate = round(measured * _MARGIN, 2)
        default = getattr(base, field_name)
        if candidate < default:
            overrides[field_name] = candidate
        elif not allow_loosen:
            warnings.append(
                f"{field_name}: your corpus's own rate ({measured:.1f}/1k, "
                f"margin-adjusted {candidate:.1f}) is looser than the genre "
                f"default ({default:.1f}) -- not applied. Pass allow_loosen=True "
                "if you want it anyway."
            )
        else:
            overrides[field_name] = candidate

    return overrides, warnings


def build_baseline_report(
    corpus_dir: Path,
    manuscript_chapter_dir: Optional[Path] = None,
    *,
    profile: str = "",
    allow_loosen: bool = False,
) -> BaselineReport:
    if not corpus_dir.is_dir():
        return BaselineReport(skipped=f"No corpus directory at {corpus_dir}")

    text = load_corpus_text(corpus_dir)
    words = len(WORD.findall(strip_comments(text)))
    if words < MIN_CORPUS_WORDS:
        return BaselineReport(skipped=(
            f"Corpus is {words} words; need at least {MIN_CORPUS_WORDS} to "
            "calibrate anything meaningful from it."
        ))

    corpus_stats = compute_stats(text)
    report = BaselineReport(corpus=corpus_stats)

    if words < LOW_CORPUS_WORDS:
        report.warnings.append(
            f"Corpus is only {words} words (recommended: {LOW_CORPUS_WORDS}+) "
            "-- treat derived thresholds as a rough first pass, not a settled "
            "calibration."
        )

    base = Thresholds.for_profile(profile)
    if not (base.dialogue_ratio_min - DIALOGUE_MISMATCH_MARGIN
            <= corpus_stats.dialogue_ratio
            <= base.dialogue_ratio_max + DIALOGUE_MISMATCH_MARGIN):
        report.warnings.append(
            f"Corpus dialogue ratio ({corpus_stats.dialogue_ratio:.0%}) is far "
            f"from this project's genre band "
            f"({base.dialogue_ratio_min:.0%}-{base.dialogue_ratio_max:.0%}) -- "
            "the corpus may not be representative of what this book needs "
            "(e.g. essays calibrating a dialogue-heavy novel)."
        )
    if not (base.fk_grade_min - FK_MISMATCH_MARGIN
            <= corpus_stats.fk_grade
            <= base.fk_grade_max + FK_MISMATCH_MARGIN):
        report.warnings.append(
            f"Corpus Flesch-Kincaid grade ({corpus_stats.fk_grade:.1f}) is far "
            f"from this project's genre band "
            f"({base.fk_grade_min:.1f}-{base.fk_grade_max:.1f})."
        )

    overrides, derive_warnings = derive_overrides(
        corpus_stats, profile=profile, allow_loosen=allow_loosen)
    report.derived_overrides = overrides
    report.warnings.extend(derive_warnings)

    if manuscript_chapter_dir is not None and manuscript_chapter_dir.is_dir():
        manuscript_files = sorted(
            p for p in manuscript_chapter_dir.glob("*.md") if p.is_file())
        if manuscript_files:
            manuscript_text = "\n\n".join(
                p.read_text(encoding="utf-8") for p in manuscript_files)
            report.manuscript = compute_stats(manuscript_text)

    return report


def render_baseline_report(report: BaselineReport) -> str:
    lines = ["# Personal Baseline Report", ""]
    if report.skipped:
        lines.append(f"Skipped: {report.skipped}")
        return "\n".join(lines)

    c = report.corpus
    lines.append(f"- Corpus size: {c.total_words:,} words")
    lines.append("")

    def _row(label: str, corpus_val: str, manuscript_val: str) -> str:
        return f"| {label} | {corpus_val} | {manuscript_val} |"

    lines.append("| Metric | Your writing | This manuscript |")
    lines.append("|---|---|---|")
    m = report.manuscript
    lines.append(_row(
        "Em dashes / 1k words", f"{c.em_dash_per_1k:.1f}",
        f"{m.em_dash_per_1k:.1f}" if m else "—"))
    lines.append(_row(
        "Adverbs / 1k words", f"{c.adverb_per_1k:.1f}",
        f"{m.adverb_per_1k:.1f}" if m else "—"))
    lines.append(_row(
        "Filter words / 1k words", f"{c.filter_word_per_1k:.1f}",
        f"{m.filter_word_per_1k:.1f}" if m else "—"))
    lines.append(_row(
        "\"Not X but Y\" / 10k words", f"{c.not_x_but_y_per_10k:.1f}",
        f"{m.not_x_but_y_per_10k:.1f}" if m else "—"))
    lines.append(_row(
        "Dialogue ratio", f"{c.dialogue_ratio:.0%}",
        f"{m.dialogue_ratio:.0%}" if m else "—"))
    lines.append(_row(
        "Flesch-Kincaid grade", f"{c.fk_grade:.1f}",
        f"{m.fk_grade:.1f}" if m else "—"))
    said = f"{c.said_tag_share:.0%}" if c.said_tag_share is not None else "n/a"
    said_m = (
        f"{m.said_tag_share:.0%}" if m and m.said_tag_share is not None else "—")
    lines.append(_row("\"said\"/\"asked\" share of dialogue tags", said, said_m))
    lines.append("")

    if report.derived_overrides:
        lines.append("## Suggested threshold overrides")
        lines.append("")
        lines.append(
            "Written to `style-profile.suggested.yaml`, NOT applied automatically. "
            "Review, then copy/rename to `style-profile.yaml` to activate.")
        lines.append("")
        for key, value in sorted(report.derived_overrides.items()):
            lines.append(f"- `{key}`: {value}")
        lines.append("")

    if report.warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    return "\n".join(lines)
