"""The 2% human pass: a small, mechanically-selected set of lines per
chapter for a person to hand-rewrite, with the result protected from every
later automated pass.

Every check in this package measures whether prose reads as machine-written.
None of them can make it read as human-written -- the most reliable lever
for that is a real person's own words landing in the text, even a
little. This module makes that cheap: pick a handful of high-leverage
lines per chapter (the ones a reader's eye actually catches -- the opening,
the closing, a simile, a line of dialogue), let a human rewrite them in one
file, then splice the rewrites back in wrapped in
``<!-- hp:start -->...<!-- hp:end -->`` markers so no later agent pass
(editor, disruptor) overwrites them. Those markers are ordinary HTML
comments as far as compilation and lint are concerned (see
discover.strip_comments) and a positional index as far as this module is
concerned (see discover.protected_spans).

Selection is deliberately mechanical, not semantic -- there is no attempt
here to identify "the emotional anchor" by meaning, because nothing in this
stdlib-only package can. The categories below are lexical/structural
proxies chosen because a line editor's eye tends to land on them: the
chapter's first and last sentence, its longest sentence, a sentence
containing a simile, the first line of dialogue, and a sentence that reads
as a maxim (reusing lint.py's MAXIM_MARKERS/CONCRETE_MARKERS heuristic).
Fewer than ten is expected and correct when a chapter doesn't have all of
these -- there is no attempt to pad to a target count.

``plan`` -> ``apply`` is a two-step, re-runnable workflow:

1. ``plan`` writes ``work/human-pass.md``: each candidate line, plus the
   chapter's sha256 and this line's byte offsets AT PLAN TIME.
2. A human hand-edits the REWRITE block for as many entries as they want
   (leaving a block unchanged skips it).
3. ``apply`` re-verifies each chapter's sha256 has not changed since
   ``plan`` (refusing that chapter's edits if it has -- offsets computed
   against an old version of the file are not safe to splice into a new
   one), splices the accepted rewrites in at their recorded offsets
   (highest offset first, so an earlier splice never shifts a later one),
   archives the pre-edit chapter (never silently overwrites), and
   sha256-verifies its own write.

Re-running ``plan`` after an ``apply`` must not re-select a human's own
rewritten lines as new candidates -- see ``_prepare_working_text``, which
blanks out existing ``hp:`` markers (along with every other comment) before
candidate selection, the same preserve-layout trick runner/proof.py uses so
that text stays inert to sentence-boundary detection without shifting any
offset.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Tuple

from runner.discover import SENTENCE_SPLIT, WORD, protected_spans, strip_comments
from runner.lint import CONCRETE_MARKERS, MAXIM_MARKERS
from runner.ledger import CHAPTER_FILE, find_simile_vehicles

HP_START = "<!-- hp:start -->"
HP_END = "<!-- hp:end -->"

_HEADING = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
_QUOTE_CHARS = set("\"'“”‘’")
_FILL = "x"

_RECORD = re.compile(r"^\s*(\w+)\s+(.*)$")
_PAIR = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\S+)')


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"')
    return raw


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

@dataclass
class LineEntry:
    kind: str
    text: str
    start: int
    end: int


def _blank_span(text: str, start: int, end: int) -> str:
    return text[:start] + re.sub(r"[^\n]", _FILL, text[start:end]) + text[end:]


def _prepare_working_text(raw: str) -> str:
    """Same length as `raw`. Comments, the chapter's heading line, and the
    CONTENT of any already-applied human-pass span are all blanked out (not
    deleted), so sentence-boundary offsets computed against this text are
    valid offsets into `raw`, but none of those three can become part of a
    freshly selected candidate.

    Blanking the hp: marker tags is not enough on its own -- strip_comments
    already does that (they're ordinary HTML comments) -- but the CONTENT a
    human already rewrote is real prose now, not a comment, and re-running
    `plan` after an `apply` must not re-select a human's own line as a new
    candidate, or fragment it into a neighboring sentence once its
    surrounding markers vanish from the split.
    """
    text = strip_comments(raw, preserve_layout=True, fill=_FILL)
    m = _HEADING.search(text)
    if m:
        text = _blank_span(text, m.start(), m.end())
    for start, end in protected_spans(raw):
        text = _blank_span(text, start, end)
    return text


def _trim_span(text: str, start: int, end: int) -> Tuple[int, int]:
    """Move (start, end) inward past whitespace and blanked-filler
    characters, so a span never opens on the tail of a blanked comment or
    closes on trailing whitespace.
    """
    while start < end and (text[start].isspace() or text[start] == _FILL):
        start += 1
    while end > start and (text[end - 1].isspace() or text[end - 1] == _FILL):
        end -= 1
    return start, end


def _sentence_spans(working_text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    pos = 0
    for m in SENTENCE_SPLIT.finditer(working_text):
        start, end = _trim_span(working_text, pos, m.start())
        if end > start:
            spans.append((start, end))
        pos = m.end()
    start, end = _trim_span(working_text, pos, len(working_text))
    if end > start:
        spans.append((start, end))
    return spans


def _looks_like_dialogue(sentence: str) -> bool:
    s = sentence.strip()
    return bool(s) and (s[0] in _QUOTE_CHARS or s[-1] in _QUOTE_CHARS)


def select_lines(raw: str, *, max_lines: int = 10) -> List[LineEntry]:
    working = _prepare_working_text(raw)
    spans = _sentence_spans(working)
    if not spans:
        return []

    candidates: Dict[Tuple[int, int], str] = {}  # span -> kind, first match wins

    def _claim(span: Tuple[int, int], kind: str) -> None:
        candidates.setdefault(span, kind)

    _claim(spans[0], "opening")
    _claim(spans[-1], "closing")

    longest = max(spans, key=lambda s: s[1] - s[0])
    _claim(longest, "longest")

    for span in spans:
        text = raw[span[0]:span[1]]
        if find_simile_vehicles(text):
            _claim(span, "simile")
            break

    for span in spans:
        text = raw[span[0]:span[1]]
        if _looks_like_dialogue(text):
            _claim(span, "dialogue_opener")
            break

    for span in spans:
        text = raw[span[0]:span[1]]
        if MAXIM_MARKERS.search(text) and not CONCRETE_MARKERS.search(text):
            _claim(span, "maxim")
            break

    entries = [
        LineEntry(kind=kind, text=raw[start:end], start=start, end=end)
        for (start, end), kind in candidates.items()
    ]
    entries.sort(key=lambda e: e.start)
    return entries[:max_lines]


# --------------------------------------------------------------------------
# Plan file
# --------------------------------------------------------------------------

@dataclass
class ChapterPlan:
    chapter: str
    sha256: str
    entries: List[LineEntry] = field(default_factory=list)


@dataclass
class HumanPassPlan:
    chapters: List[ChapterPlan] = field(default_factory=list)


def build_plan(chapter_dir: Path, *, max_lines_per_chapter: int = 10) -> HumanPassPlan:
    files = sorted(
        p for p in chapter_dir.glob("chapter-*.md")
        if p.is_file() and CHAPTER_FILE.match(p.name)
    )
    plan = HumanPassPlan()
    for path in files:
        raw = path.read_text(encoding="utf-8")
        entries = select_lines(raw, max_lines=max_lines_per_chapter)
        if entries:
            plan.chapters.append(ChapterPlan(
                chapter=path.name, sha256=_sha256_text(raw), entries=entries))
    return plan


def render_plan(plan: HumanPassPlan) -> str:
    lines = [
        "# Human Pass Worksheet", "",
        "Hand-rewrite any REWRITE block below. Leave a block exactly equal to",
        "its ORIGINAL to skip that line -- nothing outside a fenced block is",
        "read back. Do not edit the `entry ...` header lines; they are how",
        "`apply` matches an edit to the right file and position, and each one",
        "carries the chapter's checksum at plan time -- if the chapter changes",
        "before you run `apply`, that chapter's edits are refused rather than",
        "spliced in against stale offsets.", "",
        "Run when ready:", "",
        "    python3 runner/cli.py human-pass apply <project>", "",
    ]
    if not plan.chapters:
        lines.append("No finalized chapters with selectable lines yet.")
        return "\n".join(lines)

    for cp in plan.chapters:
        for i, e in enumerate(cp.entries, start=1):
            lines.append(
                f'entry  chapter={cp.chapter}  index={i}  kind={e.kind}  '
                f'start={e.start}  end={e.end}  sha256="{cp.sha256}"')
            lines.append("ORIGINAL:")
            lines.append("```")
            lines.append(e.text)
            lines.append("```")
            lines.append("REWRITE:")
            lines.append("```")
            lines.append(e.text)
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


@dataclass
class ParsedEntry:
    chapter: str
    index: int
    kind: str
    start: int
    end: int
    sha256: str
    original: str
    rewrite: str


def parse_plan(text: str) -> Tuple[List[ParsedEntry], List[str]]:
    """Never raises. Returns (entries, errors) -- a malformed block is
    reported and skipped, matching every other flat-record parser in this
    package (see runner/timeline.py, runner/texture.py).
    """
    entries: List[ParsedEntry] = []
    errors: List[str] = []

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _RECORD.match(line)
        if not m or m.group(1) != "entry":
            i += 1
            continue
        header_line_no = i + 1
        fields = {k: _unquote(v) for k, v in _PAIR.findall(m.group(2))}
        i += 1

        def _read_fence(idx: int, label: str) -> Tuple[Optional[str], int]:
            if idx >= len(lines) or lines[idx].strip() != f"{label}:":
                errors.append(f"line {header_line_no}: expected {label}: block after entry header")
                return None, idx
            idx += 1
            if idx >= len(lines) or lines[idx].strip() != "```":
                errors.append(f"line {header_line_no}: expected fenced {label} block")
                return None, idx
            idx += 1
            body_lines = []
            while idx < len(lines) and lines[idx].strip() != "```":
                body_lines.append(lines[idx])
                idx += 1
            if idx >= len(lines):
                errors.append(f"line {header_line_no}: unterminated {label} fence")
                return None, idx
            idx += 1
            return "\n".join(body_lines), idx

        original, i = _read_fence(i, "ORIGINAL")
        rewrite, i = _read_fence(i, "REWRITE")
        if original is None or rewrite is None:
            continue

        required = ("chapter", "index", "kind", "start", "end", "sha256")
        missing = [f for f in required if f not in fields]
        if missing:
            errors.append(f"line {header_line_no}: entry missing {', '.join(missing)}")
            continue
        try:
            entries.append(ParsedEntry(
                chapter=fields["chapter"], index=int(fields["index"]),
                kind=fields["kind"], start=int(fields["start"]), end=int(fields["end"]),
                sha256=fields["sha256"], original=original, rewrite=rewrite,
            ))
        except ValueError:
            errors.append(f"line {header_line_no}: entry has non-integer index/start/end")

    return entries, errors


# --------------------------------------------------------------------------
# Apply
# --------------------------------------------------------------------------

@dataclass
class ApplyResult:
    updated_chapters: List[str] = field(default_factory=list)
    skipped_entries: int = 0
    applied_entries: int = 0
    rejected_chapters: List[str] = field(default_factory=list)  # (chapter: reason)
    parse_errors: List[str] = field(default_factory=list)
    archived: Dict[str, str] = field(default_factory=dict)  # chapter -> archive path


def _archive_chapter(chapter_dir: Path, path: Path) -> str:
    """Move the pre-edit chapter aside -- never silently overwrite --
    mirroring adopt.py's `.archive/<date>/files/` convention.
    """
    today = date.today().isoformat()
    archive_dir = chapter_dir / ".archive" / today / "files"
    n = 0
    candidate = archive_dir / path.name
    while candidate.exists():
        n += 1
        candidate = archive_dir / f"{path.stem}-{n}{path.suffix}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(path), str(candidate))
    return str(candidate.relative_to(chapter_dir))


def apply_plan(chapter_dir: Path, plan_text: str) -> ApplyResult:
    result = ApplyResult()
    entries, parse_errors = parse_plan(plan_text)
    result.parse_errors = parse_errors

    by_chapter: Dict[str, List[ParsedEntry]] = {}
    for e in entries:
        by_chapter.setdefault(e.chapter, []).append(e)

    for chapter, chapter_entries in sorted(by_chapter.items()):
        if not CHAPTER_FILE.match(chapter):
            result.rejected_chapters.append(f"{chapter}: not a canonical chapter filename")
            continue
        path = chapter_dir / chapter
        if not path.is_file():
            result.rejected_chapters.append(f"{chapter}: file not found")
            continue

        raw = path.read_text(encoding="utf-8")
        current_sha = _sha256_text(raw)
        plan_sha = chapter_entries[0].sha256
        if any(e.sha256 != plan_sha for e in chapter_entries):
            result.rejected_chapters.append(
                f"{chapter}: entries disagree on sha256 -- worksheet was edited by hand incorrectly")
            continue
        if current_sha != plan_sha:
            result.rejected_chapters.append(
                f"{chapter}: chapter changed since plan was built "
                f"(plan sha256={plan_sha[:12]}..., current={current_sha[:12]}...) "
                "-- offsets are not safe to splice into a changed file; re-run "
                "`human-pass plan` and redo any edits you want to keep")
            continue

        changed = [e for e in chapter_entries if e.rewrite != e.original]
        result.skipped_entries += len(chapter_entries) - len(changed)
        if not changed:
            continue

        # Highest offset first, so an earlier splice never shifts a later one.
        new_raw = raw
        for e in sorted(changed, key=lambda e: -e.start):
            if raw[e.start:e.end] != e.original:
                result.rejected_chapters.append(
                    f"{chapter}: entry {e.index} ({e.kind}) no longer matches the "
                    "chapter at its recorded offset -- refusing to splice")
                new_raw = None
                break
            new_raw = (
                new_raw[:e.start] + HP_START + e.rewrite + HP_END + new_raw[e.end:])
        if new_raw is None:
            continue

        archived = _archive_chapter(chapter_dir, path)
        path.write_text(new_raw, encoding="utf-8")
        written = path.read_text(encoding="utf-8")
        if written != new_raw:
            # Restore from the archive rather than leave a corrupt write.
            shutil.copy2(str(chapter_dir / archived), str(path))
            result.rejected_chapters.append(
                f"{chapter}: write verification failed -- restored the pre-edit version")
            continue

        result.updated_chapters.append(chapter)
        result.applied_entries += len(changed)
        result.archived[chapter] = archived

    return result


def render_apply_result(result: ApplyResult) -> str:
    lines = ["# Human Pass — Apply Result", ""]
    lines.append(f"- Chapters updated: {len(result.updated_chapters)}")
    lines.append(f"- Lines applied: {result.applied_entries}")
    lines.append(f"- Lines left unchanged (skipped): {result.skipped_entries}")
    lines.append("")

    if result.parse_errors:
        lines.append("## Worksheet parse errors")
        lines.append("")
        for err in result.parse_errors:
            lines.append(f"- {err}")
        lines.append("")

    if result.updated_chapters:
        lines.append("## Updated")
        lines.append("")
        for ch in result.updated_chapters:
            lines.append(f"- {ch} (pre-edit archived at {result.archived.get(ch, '?')})")
        lines.append("")

    if result.rejected_chapters:
        lines.append("## Rejected (no changes written)")
        lines.append("")
        for reason in result.rejected_chapters:
            lines.append(f"- {reason}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------

def status_manuscript(chapter_dir: Path) -> Dict[str, int]:
    """Per-chapter count of already-protected (human-pass-applied) spans."""
    from runner.discover import protected_spans  # local import: keep this module's top small

    files = sorted(
        p for p in chapter_dir.glob("chapter-*.md")
        if p.is_file() and CHAPTER_FILE.match(p.name)
    )
    return {
        p.name: len(protected_spans(p.read_text(encoding="utf-8")))
        for p in files
    }
