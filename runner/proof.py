"""Deterministic proofing: typographic correctness, not prose style.

``lint.py`` asks "does this read as machine-written?" — stylistic, profile-
dependent, mostly warn-severity. This module asks "is this typographically
broken?" — objective, profile-independent, mostly fail-severity. Kept
separate deliberately: merging them would conflate "em-dash density is high
for literary fiction" with "chapter 9 has an unclosed quotation mark", and
this module must also run against *compiled* output later (front matter +
chapters together), not chapter sources only.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import unicodedata
from typing import Dict, List, Tuple

from runner.discover import strip_comments

CURLY_OPEN = "“"
CURLY_CLOSE = "”"
CURLY_APOS = "’"
STRAIGHT_QUOTE = '"'
STRAIGHT_APOS = "'"

MOJIBAKE_MARKERS = ("Ã¢â‚¬", "Ã©", "â€™", "â€œ", "â€\x9d", "�")

CHAPTER_NUMBER_IN_NAME = re.compile(r"(\d+)")
CHAPTER_HEADING = re.compile(r"^#{1,2}\s*Chapter\s+(\d+)\b", re.IGNORECASE | re.MULTILINE)
HEADING_LEVEL = re.compile(r"^(#{1,6})\s+\S", re.MULTILINE)
SCENE_BREAK_CANDIDATES = re.compile(r"^\s*([*#~\-]{3,}|[*#~\-]\s*[*#~\-]\s*[*#~\-])\s*$", re.MULTILINE)
DOUBLED_SPACE = re.compile(r"[ \t]{2,}")
ELLIPSIS_ASCII = re.compile(r"\.{3,}")
ELLIPSIS_UNICODE = "…"


@dataclass(frozen=True)
class ProofStyle:
    quotes: str = "auto"      # "curly" | "straight" | "auto"
    dashes: str = "auto"      # "em" | "spaced-en" | "auto"
    ellipsis: str = "auto"    # "unicode" | "ascii" | "auto"


@dataclass
class ProofIssue:
    check: str
    severity: str  # "fail" | "warn"
    chapter: str
    line: int
    excerpt: str
    message: str


@dataclass
class ProofReport:
    issues: List[ProofIssue] = field(default_factory=list)
    files: int = 0
    style: ProofStyle = field(default_factory=ProofStyle)

    @property
    def failed(self) -> bool:
        return any(i.severity == "fail" for i in self.issues)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _excerpt(text: str, start: int, end: int, pad: int = 30) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi].replace("\n", " ").strip()


def detect_style(chapter_texts: Dict[str, str]) -> ProofStyle:
    joined = "\n".join(chapter_texts.values())
    curly = joined.count(CURLY_OPEN) + joined.count(CURLY_CLOSE)
    straight = len(re.findall(r'(?<![\w])"', joined))
    quotes = "curly" if curly >= straight else ("straight" if straight > 0 else "auto")

    unicode_ellipsis = joined.count(ELLIPSIS_UNICODE)
    ascii_ellipsis = len(re.findall(r"(?<!\.)\.{3}(?!\.)", joined))
    ellipsis = "unicode" if unicode_ellipsis >= ascii_ellipsis else ("ascii" if ascii_ellipsis > 0 else "auto")

    return ProofStyle(quotes=quotes, ellipsis=ellipsis)


# --------------------------------------------------------------------------
# Individual detectors. Each returns a list of ProofIssue for one chapter.
# --------------------------------------------------------------------------

def _quote_style_mixing(name: str, text: str, style: ProofStyle) -> List[ProofIssue]:
    issues: List[ProofIssue] = []
    if style.quotes == "curly":
        for m in re.finditer(r'(?<!\w)"', text):
            issues.append(ProofIssue(
                "quote_style_mixing", "warn", name, _line_of(text, m.start()),
                _excerpt(text, m.start(), m.end()),
                "Straight double quote in a curly-quote manuscript.",
            ))
        # Straight apostrophe only flagged mid-word-boundary contexts like a
        # dialogue-opening apostrophe, never inside a contraction (don't).
        for m in re.finditer(r"(?<![\w])'(?=\w)", text):
            issues.append(ProofIssue(
                "quote_style_mixing", "warn", name, _line_of(text, m.start()),
                _excerpt(text, m.start(), m.end()),
                "Straight single quote/apostrophe in a curly-quote manuscript.",
            ))
    elif style.quotes == "straight":
        for ch, label in ((CURLY_OPEN, "curly open quote"), (CURLY_CLOSE, "curly close quote"),
                           (CURLY_APOS, "curly apostrophe")):
            for m in re.finditer(re.escape(ch), text):
                issues.append(ProofIssue(
                    "quote_style_mixing", "warn", name, _line_of(text, m.start()),
                    _excerpt(text, m.start(), m.end()),
                    f"{label} in a straight-quote manuscript.",
                ))
    return issues


def _unbalanced_quotes(name: str, text: str) -> List[ProofIssue]:
    """Flag genuinely unbalanced quotation marks.

    Whitelists the standard multi-paragraph quotation convention: a
    paragraph that opens with a quote mark and never closes it is correct
    when the *next* paragraph also opens with a quote mark (the closing
    mark is only used on the final paragraph of the speech).

    Curly and straight quotes are counted separately (curly marks are
    unambiguously open/close; straight marks are not, so parity — an even
    count — is the only reliable signal for those).
    """
    issues: List[ProofIssue] = []
    paragraphs = re.split(r"\n\s*\n", text)
    offsets = []
    pos = 0
    for p in paragraphs:
        offsets.append(pos)
        pos += len(p) + 2

    def opens(p: str) -> bool:
        stripped = p.lstrip()
        return stripped[:1] in (CURLY_OPEN, STRAIGHT_QUOTE)

    for i, para in enumerate(paragraphs):
        curly_opens = para.count(CURLY_OPEN)
        curly_closes = para.count(CURLY_CLOSE)
        straight_count = para.count(STRAIGHT_QUOTE)

        curly_balanced = curly_opens == curly_closes
        curly_deficit = curly_opens - curly_closes  # >0 means unclosed opens
        straight_balanced = straight_count % 2 == 0

        if curly_balanced and straight_balanced:
            continue

        # Allow exactly one unclosed curly open (or one unpaired straight
        # quote) when it is the start of a multi-paragraph quotation that
        # the next paragraph continues.
        deficit_is_one = (curly_deficit == 1 and straight_count == 0) or (
            not straight_balanced and curly_balanced
        )
        if deficit_is_one and opens(para):
            nxt = paragraphs[i + 1] if i + 1 < len(paragraphs) else ""
            if nxt and opens(nxt):
                continue

        if curly_opens or curly_closes:
            message = (
                f"{curly_opens} opening vs {curly_closes} closing curly quote "
                "marks in this paragraph."
            )
        else:
            message = (
                f"{straight_count} straight quote mark(s) in this paragraph — "
                "an odd count means one is unmatched."
            )
        issues.append(ProofIssue(
            "unbalanced_quotes", "fail", name, _line_of(text, offsets[i]),
            _excerpt(text, offsets[i], offsets[i] + min(60, len(para))),
            message,
        ))
    return issues


def _unbalanced_delims(name: str, text: str) -> List[ProofIssue]:
    issues: List[ProofIssue] = []
    for open_ch, close_ch, label in (("(", ")", "parentheses"),):
        depth = 0
        first_bad = None
        for i, ch in enumerate(text):
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth < 0 and first_bad is None:
                    first_bad = i
        if depth != 0:
            idx = first_bad if first_bad is not None else 0
            issues.append(ProofIssue(
                "unbalanced_delims", "fail", name, _line_of(text, idx),
                _excerpt(text, idx, idx + 1),
                f"Unbalanced {label} ({'more open' if depth > 0 else 'more close'} than close).",
            ))
    return issues


DOUBLED_WORD = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def _doubled_words(name: str, text: str) -> List[ProofIssue]:
    return [
        ProofIssue(
            "doubled_words", "fail", name, _line_of(text, m.start()),
            _excerpt(text, m.start(), m.end()), f'Repeated word: "{m.group(1)}".',
        )
        for m in DOUBLED_WORD.finditer(text)
    ]


def _doubled_spaces(name: str, text: str) -> List[ProofIssue]:
    return [
        ProofIssue(
            "doubled_spaces", "warn", name, _line_of(text, m.start()),
            _excerpt(text, m.start(), m.end()), "Repeated space/tab.",
        )
        for m in DOUBLED_SPACE.finditer(text)
    ]


def _dash_consistency(name: str, text: str) -> List[ProofIssue]:
    em = text.count("—")
    spaced_en = len(re.findall(r"\s–\s", text))
    double_hyphen = text.count("--")
    styles_used = sum(1 for c in (em, spaced_en, double_hyphen) if c > 0)
    if styles_used <= 1:
        return []
    return [ProofIssue(
        "dash_consistency", "warn", name, 1, "",
        f"Mixed dash styles in this chapter: em dash x{em}, spaced en dash x{spaced_en}, "
        f"double hyphen x{double_hyphen}. Pick one convention.",
    )]


def _ellipsis_consistency(name: str, text: str, style: ProofStyle) -> List[ProofIssue]:
    issues: List[ProofIssue] = []
    if style.ellipsis == "unicode":
        for m in re.finditer(r"(?<!\.)\.{3}(?!\.)", text):
            issues.append(ProofIssue(
                "ellipsis_consistency", "warn", name, _line_of(text, m.start()),
                _excerpt(text, m.start(), m.end()), "ASCII '...' in a unicode-ellipsis manuscript.",
            ))
    elif style.ellipsis == "ascii":
        for m in re.finditer(ELLIPSIS_UNICODE, text):
            issues.append(ProofIssue(
                "ellipsis_consistency", "warn", name, _line_of(text, m.start()),
                _excerpt(text, m.start(), m.end()), "Unicode '…' in an ASCII-ellipsis manuscript.",
            ))
    for m in re.finditer(r"\.{4,}", text):
        issues.append(ProofIssue(
            "ellipsis_consistency", "warn", name, _line_of(text, m.start()),
            _excerpt(text, m.start(), m.end()), "Four or more literal dots.",
        ))
    return issues


def _scene_break_consistency(all_texts: Dict[str, str]) -> List[ProofIssue]:
    markers: Dict[str, int] = {}
    for text in all_texts.values():
        for m in SCENE_BREAK_CANDIDATES.finditer(text):
            token = m.group(1).strip()
            markers[token] = markers.get(token, 0) + 1
    if len(markers) <= 1:
        return []
    listed = ", ".join(f'"{k}" x{v}' for k, v in sorted(markers.items(), key=lambda kv: -kv[1]))
    return [ProofIssue(
        "scene_break_consistency", "warn", "(manuscript)", 0, "",
        f"Multiple distinct scene-break markers in use: {listed}. Pick one.",
    )]


def _heading_levels(name: str, text: str) -> List[ProofIssue]:
    levels = {len(m.group(1)) for m in HEADING_LEVEL.finditer(text)}
    top_level_headings = [m for m in HEADING_LEVEL.finditer(text) if len(m.group(1)) == min(levels, default=1)]
    if len(top_level_headings) > 1:
        return [ProofIssue(
            "heading_levels", "warn", name, _line_of(text, top_level_headings[1].start()),
            _excerpt(text, top_level_headings[1].start(), top_level_headings[1].end()),
            "More than one top-level heading in a single chapter file.",
        )]
    return []


def _chapter_numbering(files: List[Path], chapter_texts: Dict[str, str]) -> List[ProofIssue]:
    issues: List[ProofIssue] = []
    numbers: List[Tuple[str, int]] = []
    for p in files:
        m = CHAPTER_NUMBER_IN_NAME.search(p.stem)
        if not m:
            issues.append(ProofIssue(
                "chapter_numbering", "fail", p.name, 0, p.stem,
                "Filename has no chapter number.",
            ))
            continue
        file_num = int(m.group(1))
        numbers.append((p.name, file_num))

        heading_match = CHAPTER_HEADING.search(chapter_texts.get(p.name, ""))
        if heading_match:
            heading_num = int(heading_match.group(1))
            if heading_num != file_num:
                issues.append(ProofIssue(
                    "chapter_numbering", "fail", p.name, _line_of(chapter_texts[p.name], heading_match.start()),
                    heading_match.group(0),
                    f"Filename implies chapter {file_num} but the heading says "
                    f"chapter {heading_num}.",
                ))

    for i in range(1, len(numbers)):
        prev_name, prev_num = numbers[i - 1]
        name, num = numbers[i]
        if num != prev_num + 1:
            issues.append(ProofIssue(
                "chapter_numbering", "fail", name, 0, "",
                f"Chapter numbering gap: {prev_name} is #{prev_num}, {name} is #{num}.",
            ))
    return issues


def _mojibake(name: str, text: str) -> List[ProofIssue]:
    issues: List[ProofIssue] = []
    for marker in MOJIBAKE_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            issues.append(ProofIssue(
                "mojibake", "fail", name, _line_of(text, idx),
                _excerpt(text, idx, idx + len(marker)),
                f"Possible mojibake/encoding corruption: {marker!r}.",
            ))
    for i, ch in enumerate(text):
        if unicodedata.category(ch) == "Cc" and ch not in ("\n", "\t", "\r"):
            issues.append(ProofIssue(
                "mojibake", "fail", name, _line_of(text, i),
                _excerpt(text, i, i + 1), f"Stray control character U+{ord(ch):04X}.",
            ))
    return issues


def _empty_sections(name: str, text: str) -> List[ProofIssue]:
    issues: List[ProofIssue] = []
    for m in re.finditer(r"^(#{1,6}\s+\S.*)$", text, re.MULTILINE):
        rest = text[m.end():]
        nxt = re.search(r"^#{1,6}\s+\S", rest, re.MULTILINE)
        body = rest[: nxt.start()] if nxt else rest
        if not body.strip():
            issues.append(ProofIssue(
                "empty_sections", "warn", name, _line_of(text, m.start()),
                m.group(1), "Heading with no body content before the next heading/EOF.",
            ))
    return issues


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def proof_manuscript(chapter_dir: Path, *, style: ProofStyle | None = None) -> ProofReport:
    files = sorted(p for p in chapter_dir.glob("*.md") if p.is_file())
    if not files:
        return ProofReport(
            issues=[ProofIssue("manuscript", "fail", "(none)", 0, "", "No .md chapter files found.")],
            files=0,
        )

    # Blank out editorial comments while keeping every byte offset and line
    # number intact, so reported line numbers still match the file on disk.
    # Without this, `<!--`/`-->` register as double-hyphen dashes and every
    # comment-bearing chapter reports a false "mixed dash styles".
    # `x` rather than a space: a blanked comment made of spaces would itself
    # trip the doubled-space check, and one made of `#` or `-` would look like
    # a scene break. A run of letters is inert against every detector below.
    texts = {
        p.name: strip_comments(
            p.read_text(encoding="utf-8"), preserve_layout=True, fill="x")
        for p in files
    }
    resolved_style = style or detect_style(texts)

    issues: List[ProofIssue] = []
    for p in files:
        text = texts[p.name]
        issues += _quote_style_mixing(p.name, text, resolved_style)
        issues += _unbalanced_quotes(p.name, text)
        issues += _unbalanced_delims(p.name, text)
        issues += _doubled_spaces(p.name, text)
        issues += _doubled_words(p.name, text)
        issues += _dash_consistency(p.name, text)
        issues += _ellipsis_consistency(p.name, text, resolved_style)
        issues += _heading_levels(p.name, text)
        issues += _mojibake(p.name, text)
        issues += _empty_sections(p.name, text)

    issues += _scene_break_consistency(texts)
    issues += _chapter_numbering(files, texts)

    return ProofReport(issues=issues, files=len(files), style=resolved_style)


def render_proof_report(report: ProofReport) -> str:
    lines = ["# Manuscript Proof", ""]
    lines.append(f"- Files checked: {report.files}")
    lines.append(f"- Detected style: quotes={report.style.quotes}, ellipsis={report.style.ellipsis}")
    lines.append("")

    fails = [i for i in report.issues if i.severity == "fail"]
    warns = [i for i in report.issues if i.severity == "warn"]
    lines.append(f"**Verdict: {'FAIL' if fails else 'PASS'}** ({len(fails)} fail, {len(warns)} warn)")
    lines.append("")

    if not report.issues:
        lines.append("No typographic defects found.")
        return "\n".join(lines)

    lines.append("| Check | Severity | Chapter | Line | Message |")
    lines.append("|---|---|---|---|---|")
    for i in report.issues:
        lines.append(f"| {i.check} | {i.severity.upper()} | {i.chapter} | {i.line} | {i.message} |")
    lines.append("")

    for i in report.issues:
        if not i.excerpt:
            continue
        lines.append(f"- **{i.check}** ({i.chapter}:{i.line}) — {i.excerpt}")

    return "\n".join(lines)
