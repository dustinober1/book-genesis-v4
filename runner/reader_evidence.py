"""Real (human) beta-reader evidence, kept separate from simulated evaluation.

``/beta-reader`` (skills/beta-reader) simulates four fictional readers. That
is a craft diagnostic, not proof anyone real will finish the book. Novel
Forge draws a hard line between the two and tracks actual human responses
with their own provenance and confidence rules; this module is that line
for Book Genesis.

Real reader responses live in ``feedback/beta-readers/`` and are never
merged into ``evaluations/`` (which is simulated-reader output) or allowed
to silently raise a Genesis Score. They answer a narrower question: did
real humans, in practice, keep reading and feel something -- and how much
should you trust that signal given how many of them there were.

CSV columns: ``reader_id,chapter,rating,comment,delayed``
- ``reader_id``: an opaque identifier the writer assigns (no real names).
- ``chapter``: chapter number the response is about.
- ``rating``: 1-5.
- ``comment``: free text (may be blank).
- ``delayed``: ``1`` if this is a delayed/next-day recall response
  (evidence of the Tomorrow Test), else ``0``/blank.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class Response:
    reader_id: str
    chapter: int
    rating: int
    comment: str
    delayed: bool


@dataclass
class ChapterEvidence:
    chapter: int
    responses: List[Response] = field(default_factory=list)

    @property
    def reader_count(self) -> int:
        return len({r.reader_id for r in self.responses})

    @property
    def average_rating(self) -> float:
        if not self.responses:
            return 0.0
        return sum(r.rating for r in self.responses) / len(self.responses)

    @property
    def has_positive(self) -> bool:
        return any(r.rating >= 4 for r in self.responses)

    @property
    def has_critical(self) -> bool:
        return any(r.rating <= 2 for r in self.responses)


@dataclass
class EvidenceReport:
    experiment_id: str
    chapters: Dict[int, ChapterEvidence]
    rejected_rows: List[str]
    duplicate_rows: List[str]

    @property
    def total_responses(self) -> int:
        return sum(len(c.responses) for c in self.chapters.values())

    @property
    def chapters_covered(self) -> int:
        return len(self.chapters)

    @property
    def confidence(self) -> str:
        # Deterministic tiers -- never invent a confidence higher than what
        # the sample size and chapter diversity actually support.
        n, spread = self.total_responses, self.chapters_covered
        if n >= 6 and spread >= 3:
            has_diverse_signal = any(c.has_positive for c in self.chapters.values()) and \
                any(c.has_critical for c in self.chapters.values())
            if has_diverse_signal:
                return "strong"
            return "moderate"
        if n >= 3 and spread >= 2:
            return "moderate"
        return "weak"


def import_reader_evidence(target: Path, csv_path: Path, *, experiment_id: str = "RE-001") -> EvidenceReport:
    chapters: Dict[int, ChapterEvidence] = {}
    rejected: List[str] = []
    duplicates: List[str] = []
    seen: set = set()

    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # header is row 1
            reader_id = (row.get("reader_id") or "").strip()
            chapter_raw = (row.get("chapter") or "").strip()
            rating_raw = (row.get("rating") or "").strip()
            comment = (row.get("comment") or "").strip()
            delayed_raw = (row.get("delayed") or "").strip()

            if not reader_id or not chapter_raw or not rating_raw:
                rejected.append(f"row {i}: missing reader_id, chapter, or rating")
                continue
            try:
                chapter = int(chapter_raw)
                rating = int(rating_raw)
            except ValueError:
                rejected.append(f"row {i}: chapter/rating must be integers, got {chapter_raw!r}/{rating_raw!r}")
                continue
            if not (1 <= rating <= 5):
                rejected.append(f"row {i}: rating {rating} out of 1-5 range")
                continue

            key = (reader_id, chapter)
            if key in seen:
                duplicates.append(f"row {i}: duplicate response from {reader_id!r} for chapter {chapter} (kept first)")
                continue
            seen.add(key)

            response = Response(
                reader_id=reader_id, chapter=chapter, rating=rating,
                comment=comment, delayed=delayed_raw in {"1", "true", "yes"},
            )
            chapters.setdefault(chapter, ChapterEvidence(chapter=chapter)).responses.append(response)

    return EvidenceReport(
        experiment_id=experiment_id, chapters=chapters,
        rejected_rows=rejected, duplicate_rows=duplicates,
    )


def render_evidence_report(report: EvidenceReport) -> str:
    lines = [f"# Reader Evidence — {report.experiment_id}", ""]
    lines.append(f"**Confidence: {report.confidence.upper()}** "
                 f"({report.total_responses} responses across {report.chapters_covered} chapters)")
    lines.append("")
    lines.append(
        "This is real human reader evidence, not simulated. It is separate from "
        "`/beta-reader` output and must not be merged into `evaluations/` or used "
        "to justify a Genesis Score increase on its own -- it answers a narrower "
        "question (did real people keep reading and feel something), and its "
        "confidence tier says how much weight that answer deserves."
    )
    lines.append("")

    if report.rejected_rows:
        lines.append("## Rejected Rows")
        for item in report.rejected_rows:
            lines.append(f"- {item}")
        lines.append("")

    if report.duplicate_rows:
        lines.append("## Duplicate Rows (first response kept)")
        for item in report.duplicate_rows:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("## Per-Chapter Summary")
    lines.append("")
    lines.append("| Chapter | Readers | Avg Rating | Positive | Critical | Delayed responses |")
    lines.append("|---|---|---|---|---|---|")
    for chapter in sorted(report.chapters):
        ce = report.chapters[chapter]
        delayed_count = sum(1 for r in ce.responses if r.delayed)
        lines.append(
            f"| {chapter} | {ce.reader_count} | {ce.average_rating:.1f} | "
            f"{'yes' if ce.has_positive else 'no'} | {'yes' if ce.has_critical else 'no'} | {delayed_count} |"
        )
    lines.append("")

    lines.append("## Comments")
    lines.append("")
    for chapter in sorted(report.chapters):
        ce = report.chapters[chapter]
        commented = [r for r in ce.responses if r.comment]
        if not commented:
            continue
        lines.append(f"### Chapter {chapter}")
        for r in commented:
            tag = " (delayed)" if r.delayed else ""
            lines.append(f"- [{r.reader_id}, {r.rating}/5{tag}] {r.comment}")
        lines.append("")

    return "\n".join(lines)
