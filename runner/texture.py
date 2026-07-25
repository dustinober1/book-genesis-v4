"""The texture bank: sourced, verifiable sensory detail, and whether it made
it into the manuscript.

Generic detail is the AI tell readers name most often -- the unnamed coffee
shop, weather that's just "cold", a street with no name. book-researcher
already has WebSearch/WebFetch for market research; this module is the
counterpart for WORLD research: verified street names, period-correct
objects, occupational jargon, prices, weather on real dates -- each entry
carrying a source, because researched-then-hallucinated specifics are worse
than no specifics at all.

Authoring format is the same flat record syntax runner/timeline.py
established, for the same reason -- deterministic, dependency-free, easy to
hand-edit:

    # research/texture-bank.md
    texture  id=burnside-thai   term="the Thai place on Burnside"  kind=place  src="https://..."
    texture  id=ration-book     term="the blue ration book"        kind=object src="https://..."

This module answers two questions a research phase cannot verify by eye on
a real manuscript: which entries actually made it into the prose (coverage),
and which entries have no source at all (the exact place a hallucinated
"fact" would hide). Both are "warn" severity -- like macro.py, nothing here
is calibrated against a real corpus, and the gate check that wraps this
module belongs in gates.ADVISORY_CHECKS.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Tuple

RECORD = re.compile(r"^\s*(\w+)\s+(.*)$")
PAIR = re.compile(r'(\w+)\s*=\s*("(?:[^"\\]|\\.)*"|\S+)')

# Documented in the module docstring's example and agents/book-researcher.md.
# Not enforced as a hard error -- an unrecognized kind is a warn-level
# finding, not a parse failure, since new kinds are a reasonable thing for a
# project to invent.
KNOWN_KINDS: Tuple[str, ...] = ("place", "object", "jargon", "price", "weather")

TEXTURE_BANK_NAME = "research/texture-bank.md"


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"')
    return raw


@dataclass
class TextureEntry:
    id: str
    term: str
    kind: str = ""
    src: str = ""
    note: str = ""
    line: int = 0


@dataclass
class CoverageResult:
    entry: TextureEntry
    chapters_used: List[str] = field(default_factory=list)
    count: int = 0


@dataclass
class Finding:
    check: str
    severity: str  # "fail" for parse errors, "warn" for everything else
    measured: str
    threshold: str
    detail: str = ""
    citations: List[str] = field(default_factory=list)


@dataclass
class TextureReport:
    entries: List[TextureEntry] = field(default_factory=list)
    coverage: List[CoverageResult] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    skipped: str = ""

    @property
    def failed(self) -> bool:
        return any(f.severity == "fail" for f in self.findings)


def parse_texture_bank(text: str) -> Tuple[List[TextureEntry], List[str]]:
    """Parse texture-bank.md. Never raises -- unparsable lines are collected
    as errors, same contract as runner/timeline.py's parse_timeline.
    """
    entries: List[TextureEntry] = []
    errors: List[str] = []
    seen_ids: Dict[str, int] = {}

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = RECORD.match(line)
        if not m:
            errors.append(f"line {lineno}: unparsable record: {line!r}")
            continue
        record_kind, rest = m.group(1), m.group(2)
        if record_kind != "texture":
            errors.append(f"line {lineno}: unknown record type {record_kind!r} (expected 'texture')")
            continue
        fields = {k: _unquote(v) for k, v in PAIR.findall(rest)}
        entry_id = fields.get("id", "")
        term = fields.get("term", "")
        if not entry_id:
            errors.append(f"line {lineno}: texture record missing id=")
            continue
        if not term:
            errors.append(f"line {lineno}: texture record {entry_id!r} missing term=")
            continue
        if entry_id in seen_ids:
            errors.append(
                f"line {lineno}: duplicate texture id {entry_id!r} "
                f"(first seen at line {seen_ids[entry_id]})")
            continue
        seen_ids[entry_id] = lineno
        entries.append(TextureEntry(
            id=entry_id, term=term, kind=fields.get("kind", ""),
            src=fields.get("src", ""), note=fields.get("note", ""), line=lineno,
        ))

    return entries, errors


def check_coverage(
    entries: List[TextureEntry], chapter_texts: Dict[str, str],
) -> List[CoverageResult]:
    """Which chapters actually use each texture-bank entry, and how often.

    Substring match on the entry's exact `term` text, case-insensitive --
    the point is to verify the researched phrase made it into the prose
    largely as written, not to fuzzy-match around it.
    """
    results = []
    for entry in entries:
        pattern = re.compile(re.escape(entry.term), re.IGNORECASE)
        chapters_used = []
        count = 0
        for name in sorted(chapter_texts):
            n = len(pattern.findall(chapter_texts[name]))
            if n:
                chapters_used.append(name)
                count += n
        results.append(CoverageResult(entry=entry, chapters_used=chapters_used, count=count))
    return results


def texture_manuscript(
    bank_path: Path, chapter_dir: Path,
) -> TextureReport:
    if not bank_path.is_file():
        return TextureReport(skipped=f"No texture bank at {bank_path}")

    text = bank_path.read_text(encoding="utf-8")
    entries, parse_errors = parse_texture_bank(text)

    findings: List[Finding] = []
    for err in parse_errors:
        findings.append(Finding("parse", "fail", err, "parses cleanly"))

    if not entries:
        return TextureReport(entries=[], coverage=[], findings=findings)

    chapter_files = sorted(p for p in chapter_dir.glob("*.md") if p.is_file()) \
        if chapter_dir.is_dir() else []
    chapter_texts = {p.name: p.read_text(encoding="utf-8") for p in chapter_files}
    coverage = check_coverage(entries, chapter_texts)

    missing_src = [c.entry for c in coverage if not c.entry.src]
    if missing_src:
        findings.append(Finding(
            "missing_src", "warn",
            f"{len(missing_src)}/{len(entries)} entries have no src=",
            "every entry has a src",
            "Web-researched detail with no source is exactly where a "
            "hallucinated specific hides. Add src= or drop the entry.",
            [f"{e.id}: \"{e.term}\"" for e in missing_src][:10],
        ))

    if chapter_texts:
        unused = [c.entry for c in coverage if c.count == 0]
        if unused:
            findings.append(Finding(
                "unused_texture", "warn",
                f"{len(unused)}/{len(entries)} entries never appear in the manuscript",
                "every entry used at least once",
                "Researched detail that never makes it into the prose was "
                "wasted research -- or the manuscript is drifting from the "
                "world it was researched for.",
                [f"{e.id}: \"{e.term}\"" for e in unused][:10],
            ))

    unknown_kind = [e for e in entries if e.kind and e.kind not in KNOWN_KINDS]
    if unknown_kind:
        findings.append(Finding(
            "unknown_kind", "warn",
            f"{len(unknown_kind)} entries use a kind= outside "
            f"{{{', '.join(KNOWN_KINDS)}}}",
            f"kind in {{{', '.join(KNOWN_KINDS)}}}",
            "Not an error -- a project may reasonably need a new kind -- "
            "but check it wasn't a typo.",
            [f"{e.id}: kind={e.kind!r}" for e in unknown_kind][:10],
        ))

    return TextureReport(entries=entries, coverage=coverage, findings=findings)


def render_texture_report(report: TextureReport) -> str:
    lines = ["# Texture Bank Coverage", ""]
    if report.skipped:
        lines.append(f"Skipped: {report.skipped}")
        return "\n".join(lines)

    lines.append(f"- Entries: {len(report.entries)}")
    lines.append("")

    fails = [f for f in report.findings if f.severity == "fail"]
    warns = [f for f in report.findings if f.severity == "warn"]
    lines.append(f"**Verdict: {'FAIL' if fails else 'PASS'}** "
                 f"({len(fails)} fail, {len(warns)} warn)")
    lines.append("")

    if report.coverage:
        lines.append("| Entry | Term | Kind | Used in | Count |")
        lines.append("|---|---|---|---|---|")
        for c in report.coverage:
            used = ", ".join(c.chapters_used) if c.chapters_used else "(none)"
            lines.append(
                f"| {c.entry.id} | {c.entry.term} | {c.entry.kind or '-'} | {used} | {c.count} |")
        lines.append("")

    if not report.findings:
        lines.append("No deterministic pattern findings.")
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
