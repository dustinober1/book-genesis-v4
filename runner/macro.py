"""Book-level template detection.

lint.py measures sentences, paragraphs, and chapters in isolation. It has
no notion of the book as a whole -- so a manuscript where chapter 1 through
chapter 20 all open on an anomaly and all close on an unanswered question
passes every existing check cleanly, even though that uniformity is exactly
the kind of template a reader (and an editor) notices at the scale lint
cannot see.

This module looks at three book-level shapes instead: how chapters open and
close (dialogue / question / image-action / fragment / maxim), how often
scene breaks recur, and whether chapter titles share a structure. All of it
is measured, none of it is calibrated against a real corpus yet -- every
finding here is deliberately "warn" severity, and the gate check that wraps
this module is registered in gates.ADVISORY_CHECKS: visible in every report,
never blocking, until a personal baseline (runner/corpus.py) gives these
thresholds real evidence behind them.

Needs at least MIN_CHAPTERS_FOR_MACRO chapters to say anything -- at n=2 to
4, "every chapter opens the same way" is not a template, it is the whole
sample. The demo fixture (4 chapters) is deliberately below this floor.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List

from runner.discover import SENTENCE_SPLIT, WORD, strip_comments
from runner.lint import CONCRETE_MARKERS, MAXIM_MARKERS
from runner.proof import SCENE_BREAK_CANDIDATES

MIN_CHAPTERS_FOR_MACRO = 6

# Modes a chapter's opening or closing sentence is classified into. Order of
# the checks in _classify matters: dialogue and question are checked before
# fragment, so a one-word line of dialogue ("No.") or a two-word question
# ("Why now?") is not misclassified as merely short.
MODE_DIALOGUE = "dialogue"
MODE_QUESTION = "question"
MODE_MAXIM = "maxim"
MODE_FRAGMENT = "fragment"
MODE_IMAGE_ACTION = "image-action"
MODE_OTHER = "other"

_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_CHAPTER_PREFIX = re.compile(r"^Chapter\s+\d+\s*[:.\-]?\s*(.*)$", re.IGNORECASE)
_QUOTE_CHARS = set("\"'“”‘’")
_FRAGMENT_MAX_WORDS = 4


@dataclass
class ChapterShape:
    name: str
    title: str
    open_mode: str
    close_mode: str
    scene_breaks: int


@dataclass
class Finding:
    check: str
    severity: str  # always "warn" here -- see module docstring
    measured: str
    threshold: str
    detail: str = ""
    citations: List[str] = field(default_factory=list)


@dataclass
class MacroReport:
    chapters: List[ChapterShape]
    findings: List[Finding]
    skipped: str = ""  # non-empty when the manuscript is too small to analyze

    @property
    def failed(self) -> bool:
        return any(f.severity == "fail" for f in self.findings)


def _looks_like_dialogue(sentence: str) -> bool:
    s = sentence.strip()
    return bool(s) and (s[0] in _QUOTE_CHARS or s[-1] in _QUOTE_CHARS)


def _classify(sentence: str) -> str:
    s = sentence.strip()
    if not s:
        return MODE_OTHER
    if _looks_like_dialogue(s):
        return MODE_DIALOGUE
    if s.endswith("?"):
        return MODE_QUESTION
    if len(WORD.findall(s)) <= _FRAGMENT_MAX_WORDS:
        return MODE_FRAGMENT
    if MAXIM_MARKERS.search(s) and not CONCRETE_MARKERS.search(s):
        return MODE_MAXIM
    if CONCRETE_MARKERS.search(s):
        return MODE_IMAGE_ACTION
    return MODE_OTHER


def _title_lead_word(title: str) -> str:
    """The first content word of a chapter title, with any "Chapter N:"
    prefix stripped -- "Chapter 1: The Ledger" and "The Ledger" both
    resolve to "the", which is the word parallelism actually depends on.
    """
    if not title:
        return ""
    m = _CHAPTER_PREFIX.match(title.strip())
    remainder = (m.group(1) if m else title).strip()
    words = WORD.findall(remainder)
    return words[0].lower() if words else ""


def analyze_chapter_shape(name: str, raw: str) -> ChapterShape:
    # Comments first: the writer's `<!-- Word count: ... -->` header
    # (agents/book-writer.md) is every real chapter's first line, and
    # without stripping it, "opening mode" would classify the metadata
    # comment instead of the chapter's actual first sentence.
    text = strip_comments(raw)
    scene_breaks = len(SCENE_BREAK_CANDIDATES.findall(text))

    heading_match = _HEADING.search(text)
    title = heading_match.group(1).strip() if heading_match else ""
    body = _HEADING.sub("", text, count=1) if heading_match else text

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(body) if s.strip()]
    open_mode = _classify(sentences[0]) if sentences else MODE_OTHER
    close_mode = _classify(sentences[-1]) if sentences else MODE_OTHER
    return ChapterShape(
        name=name, title=title, open_mode=open_mode, close_mode=close_mode,
        scene_breaks=scene_breaks,
    )


def macro_manuscript(
    chapter_dir: Path,
    *,
    open_share_max: float = 0.5,
    close_share_max: float = 0.5,
    title_share_max: float = 0.5,
) -> MacroReport:
    files = sorted(p for p in chapter_dir.glob("*.md") if p.is_file())
    if not files:
        return MacroReport([], [], skipped=f"No .md chapter files found in {chapter_dir}")

    raw_by_file = {p.name: p.read_text(encoding="utf-8") for p in files}
    if len(raw_by_file) < MIN_CHAPTERS_FOR_MACRO:
        return MacroReport([], [], skipped=(
            f"Only {len(raw_by_file)} chapter(s); macro-structure patterns need "
            f"at least {MIN_CHAPTERS_FOR_MACRO} to mean anything -- at this size "
            "every chapter sharing an opening mode is the whole sample, not "
            "evidence of a template."
        ))

    shapes = [analyze_chapter_shape(n, r) for n, r in sorted(raw_by_file.items())]
    findings: List[Finding] = []

    def _mode_share_findings(check: str, get_mode, share_max: float, label: str) -> None:
        counts: Dict[str, int] = {}
        for s in shapes:
            counts[get_mode(s)] = counts.get(get_mode(s), 0) + 1
        for mode, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            share = n / len(shapes)
            if share > share_max:
                findings.append(Finding(
                    check, "warn",
                    f'{n}/{len(shapes)} chapters {label} in "{mode}" mode ({share:.0%})',
                    f"<={share_max:.0%}",
                    f"Vary how chapters {label} -- dialogue, question, "
                    "image-action, fragment, maxim.",
                    [s.name for s in shapes if get_mode(s) == mode][:6],
                ))

    _mode_share_findings("opening_mode_share", lambda s: s.open_mode, open_share_max, "open")
    _mode_share_findings("closing_mode_share", lambda s: s.close_mode, close_share_max, "close")

    # Scene-break uniformity: the same signal as lint's chapter-length
    # uniformity check (identical numbers across every chapter reads as a
    # template), applied to scene-break counts instead of word counts.
    break_counts = [s.scene_breaks for s in shapes]
    if len(set(break_counts)) == 1 and break_counts[0] > 0:
        findings.append(Finding(
            "scene_break_uniformity", "warn",
            f"every chapter has exactly {break_counts[0]} scene break(s)",
            "varied counts across chapters",
            "Identical scene-break counts in every chapter can signal a "
            "structural template as much as identical chapter lengths do.",
        ))

    # Chapter-title parallelism.
    titled = [(s.name, _title_lead_word(s.title)) for s in shapes]
    titled = [(name, word) for name, word in titled if word]
    if titled:
        lead_counts: Dict[str, int] = {}
        for _, word in titled:
            lead_counts[word] = lead_counts.get(word, 0) + 1
        for word, n in sorted(lead_counts.items(), key=lambda kv: -kv[1]):
            share = n / len(titled)
            if share > title_share_max and n >= 3:
                findings.append(Finding(
                    "title_parallelism", "warn",
                    f'{n}/{len(titled)} chapter titles open with '
                    f'"{word.title()}" ({share:.0%})',
                    f"<={title_share_max:.0%}",
                    "A repeated title structure across most chapters reads as "
                    "a template even when the prose inside varies.",
                    [name for name, w in titled if w == word][:6],
                ))

    return MacroReport(shapes, findings)


def render_macro_report(report: MacroReport) -> str:
    lines = ["# Manuscript Macro-Structure", ""]
    if report.skipped:
        lines.append(f"Skipped: {report.skipped}")
        return "\n".join(lines)

    lines.append(f"- Chapters analyzed: {len(report.chapters)}")
    lines.append("")

    fails = [f for f in report.findings if f.severity == "fail"]
    warns = [f for f in report.findings if f.severity == "warn"]
    lines.append(f"**Verdict: {'FAIL' if fails else 'PASS'}** "
                 f"({len(fails)} fail, {len(warns)} warn)")
    lines.append("")

    if not report.findings:
        lines.append("No macro-structure pattern findings.")
        return "\n".join(lines)

    lines.append("| Check | Severity | Measured | Threshold |")
    lines.append("|---|---|---|---|")
    for f in report.findings:
        lines.append(f"| {f.check} | {f.severity.upper()} | {f.measured} | {f.threshold} |")
    lines.append("")

    for f in report.findings:
        if not (f.detail or f.citations):
            continue
        lines.append(f"### {f.check} — {f.measured}")
        if f.detail:
            lines.append(f.detail)
        if f.citations:
            lines.append("")
            for c in f.citations:
                lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)
