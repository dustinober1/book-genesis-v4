"""The retired-phrase ledger: repetition prevention, not just detection.

lint.py's discovered-repetition and phrase-escalation checks find a tic
AFTER the manuscript exists -- useful for the evaluator, too late for the
writer drafting chapter 14, who has no way to know chapter 3 already spent
"a lattice of grief" three times. This module scans every FINALIZED chapter
and produces a running ledger of what has already been used: phrases,
simile vehicles, dialogue tags, chapter-opening words, and (when available)
structural approaches and hook types. `ledger_manuscript` is meant to run
after each chapter clears its quality gate, with the resulting
`work/retired.md` fed into the next chapter's writer dispatch as a banned
list -- turning the pipeline's strongest repetition checks from a post-
mortem into prevention.

Structural approach and hook type come from a `meta` line the writer's
self-report is expected to emit (see agents/book-writer.md), in the same
flat key=value record syntax runner/timeline.py already established:

    meta  chapter=7  structure=spiral  hook=image  anchor="the phone on the sill"

This is deliberate: chapter-N-report.md is otherwise a model-authored
bulleted template, and every other parser in this package reads a
machine-written format -- parsing the writer's free-form prose would be the
one parser here whose input isn't under this package's control. A chapter
missing a meta line simply contributes nothing to the structural-approach
and hook sections; it is never a parse error, and it never blocks the rest
of the ledger from building.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from runner.discover import (
    WORD,
    dialogue_tag_counts,
    repeated_ngrams,
    strip_comments,
)

# Canonical chapter filename, matching agents/book-writer.md's "Write to:
# manuscript/chapters/chapter-[N].md". Deliberately excludes sibling files
# that live in the SAME directory -- chapter-N-report.md (the writer's own
# self-report) and chapter-N-pre-disruption.md (the disruptor's backup, per
# agents/book-disruptor.md) -- neither of which is manuscript prose.
CHAPTER_FILE = re.compile(r"^chapter-(\d+)\.md$", re.IGNORECASE)

_META_RECORD = re.compile(r"^\s*meta\s+(.*)$", re.MULTILINE)
_PAIR = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\S+)')

# "like a lattice", "as if the walls", "the way grief settles" -- trimmed at
# the first clause boundary so the vehicle stays a short, matchable phrase
# rather than swallowing the rest of the sentence.
_SIMILE = re.compile(
    r"\b(like (?:a|an|the)\s+[\w'-]+(?:\s+[\w'-]+){0,4}"
    r"|as if\s+[\w'-]+(?:\s+[\w'-]+){0,4}"
    r"|the way\s+[\w'-]+(?:\s+[\w'-]+){0,4})",
    re.IGNORECASE,
)

# "said" and "asked" are the house style's dominant tags (see lint.py's
# said_tag_share_min) and are never retired -- only the less common
# synonym tags are worth flagging as already spent.
_ALWAYS_AVAILABLE_TAGS = {"said", "asked"}


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"')
    return raw


def parse_meta_line(report_text: str) -> Optional[Dict[str, str]]:
    """The first `meta ...` record in a chapter-N-report.md, if any."""
    m = _META_RECORD.search(report_text)
    if not m:
        return None
    return {k: _unquote(v) for k, v in _PAIR.findall(m.group(1))}


def find_simile_vehicles(text: str) -> List[str]:
    """Normalized simile-opener phrases ("like a X", "as if X", "the way
    X") found in the text, one entry per occurrence -- not deduplicated,
    so the caller can count repeats.
    """
    hits = []
    for m in _SIMILE.finditer(text):
        snippet = re.sub(r"\s+", " ", m.group(1)).strip().lower()
        hits.append(snippet)
    return hits


def chapter_opening_word(raw: str) -> Optional[str]:
    """The first content word of a chapter, after stripping comments and
    the heading line -- what a fresh chapter must not simply repeat.
    """
    text = strip_comments(raw)
    text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)
    words = WORD.findall(text)
    return words[0].lower() if words else None


@dataclass
class LedgerReport:
    chapters_scanned: List[str] = field(default_factory=list)
    phrases: List[Tuple[str, int]] = field(default_factory=list)          # (phrase, count)
    similes: List[Tuple[str, int]] = field(default_factory=list)          # (vehicle, count)
    opening_words: List[Tuple[str, List[str]]] = field(default_factory=list)  # (word, chapters)
    dialogue_tags: List[Tuple[str, int]] = field(default_factory=list)    # (tag, count) excl. said/asked
    structural_approaches: List[Tuple[str, str]] = field(default_factory=list)  # (chapter, structure)
    hooks: List[Tuple[str, str]] = field(default_factory=list)            # (chapter, hook)
    chapters_missing_meta: List[str] = field(default_factory=list)


def build_ledger(
    chapter_dir: Path,
    *,
    report_dir: Optional[Path] = None,
    ngram_min_count: int = 2,
    ngram_min_per_10k: float = 1.0,
) -> LedgerReport:
    """Scan every finalized chapter and build the retired-resource ledger.

    Deliberately looser than lint's own thresholds (ngram_min_count=5,
    ngram_per_10k=4.0): lint exists to catch a tic that got out of hand,
    this exists to catch a phrase the *next* chapter might reach for again
    -- a single distinctive use is already worth listing, since the whole
    point is to prevent the second use, not react to it.
    """
    report_dir = report_dir or chapter_dir
    chapter_files = sorted(
        p for p in chapter_dir.glob("chapter-*.md")
        if p.is_file() and CHAPTER_FILE.match(p.name)
    )
    if not chapter_files:
        return LedgerReport()

    raw_by_file = {p.name: p.read_text(encoding="utf-8") for p in chapter_files}
    stripped_by_file = {n: strip_comments(r) for n, r in raw_by_file.items()}
    joined = "\n\n".join(stripped_by_file.values())

    report = LedgerReport(chapters_scanned=sorted(raw_by_file))

    # -- phrases (looser threshold than lint's discovered-repetition) ------
    ngram_hits = repeated_ngrams(
        stripped_by_file, min_count=ngram_min_count, min_per_10k=ngram_min_per_10k)
    report.phrases = [(h.phrase, h.count) for h in ngram_hits]

    # -- simile vehicles -----------------------------------------------------
    simile_counts: Dict[str, int] = {}
    for text in stripped_by_file.values():
        for vehicle in find_simile_vehicles(text):
            simile_counts[vehicle] = simile_counts.get(vehicle, 0) + 1
    report.similes = sorted(simile_counts.items(), key=lambda kv: -kv[1])

    # -- chapter-opening words -----------------------------------------------
    opening_chapters: Dict[str, List[str]] = {}
    for name, raw in raw_by_file.items():
        word = chapter_opening_word(raw)
        if word:
            opening_chapters.setdefault(word, []).append(name)
    report.opening_words = sorted(opening_chapters.items(), key=lambda kv: -len(kv[1]))

    # -- dialogue tags (excluding the always-available said/asked) ----------
    tag_counts = dialogue_tag_counts(joined)
    report.dialogue_tags = sorted(
        ((tag, n) for tag, n in tag_counts.items() if tag not in _ALWAYS_AVAILABLE_TAGS),
        key=lambda kv: -kv[1],
    )

    # -- structural approaches and hooks, from each chapter's self-report ---
    for name in sorted(raw_by_file):
        m = CHAPTER_FILE.match(name)
        report_path = report_dir / f"chapter-{m.group(1)}-report.md"
        if not report_path.is_file():
            report.chapters_missing_meta.append(name)
            continue
        meta = parse_meta_line(report_path.read_text(encoding="utf-8"))
        if not meta:
            report.chapters_missing_meta.append(name)
            continue
        if meta.get("structure"):
            report.structural_approaches.append((name, meta["structure"]))
        if meta.get("hook"):
            report.hooks.append((name, meta["hook"]))

    return report


def render_ledger(report: LedgerReport) -> str:
    lines = ["# Retired — Already Used", ""]
    lines.append(
        "Do not reuse anything listed below. This ledger exists so a later "
        "chapter never repeats what an earlier one already spent.")
    lines.append("")
    lines.append(f"- Chapters scanned: {len(report.chapters_scanned)}")
    lines.append("")

    if not report.chapters_scanned:
        lines.append("No finalized chapters yet.")
        return "\n".join(lines)

    if report.structural_approaches:
        last_chapter, last_structure = report.structural_approaches[-1]
        lines.append(f"## Structural approach (do not repeat the most recent)")
        lines.append("")
        lines.append(f"Most recent ({last_chapter}): **{last_structure}**")
        lines.append("")
        lines.append("All used so far: " + ", ".join(
            f"{ch}={s}" for ch, s in report.structural_approaches))
        lines.append("")

    if report.hooks:
        last_chapter, last_hook = report.hooks[-1]
        lines.append("## Hook type (do not repeat the most recent)")
        lines.append("")
        lines.append(f"Most recent ({last_chapter}): **{last_hook}**")
        lines.append("")

    if report.phrases:
        lines.append("## Phrases already used")
        lines.append("")
        for phrase, n in report.phrases:
            lines.append(f'- "{phrase}" (x{n})')
        lines.append("")

    if report.similes:
        lines.append("## Simile vehicles already used")
        lines.append("")
        for vehicle, n in report.similes:
            lines.append(f'- "{vehicle}" (x{n})')
        lines.append("")

    if report.opening_words:
        lines.append("## Chapter-opening words already used")
        lines.append("")
        for word, chapters in report.opening_words:
            lines.append(f'- "{word}" — {", ".join(chapters)}')
        lines.append("")

    if report.dialogue_tags:
        lines.append("## Dialogue tags already used (besides said/asked)")
        lines.append("")
        for tag, n in report.dialogue_tags:
            lines.append(f'- "{tag}" (x{n})')
        lines.append("")

    if report.chapters_missing_meta:
        lines.append(
            "## Chapters without a `meta` record in their self-report "
            "(structural approach / hook not tracked for these)")
        lines.append("")
        for name in report.chapters_missing_meta:
            lines.append(f"- {name}")
        lines.append("")

    return "\n".join(lines)
