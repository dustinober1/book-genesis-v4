"""Check attributed dialogue against each character's voice-lexicon.yaml.

voice-dna.md (agents/book-architect.md) already prescribes each character's
voice in prose -- vocabulary band, syntax fingerprint, "5 things this
character would never say". voice-lexicon.yaml is the same information in a
form code can check instead of only a person re-reading the prose:

    # voice-lexicon.yaml
    mira:
      never_say:
        - "literally"
        - "y'all"
      signature:
        - "for what it's worth"
      contractions: "high"
      fragments: "frequent"
    devon:
      never_say:
        - "please"
      signature:
        - "look"

Two levels only (character slug -> {scalar or list fields}), matching the
project's one hand-rolled YAML subset (see filesystem._load_simple_yaml_map
and its docstring on why there is no real YAML parser here). Character keys
are matched against discover.dialogue_by_speaker's speaker names
case-insensitively.

This module only checks `never_say` mechanically -- `signature`,
`contractions`, and `fragments` are read but not scored here; they are
qualitative craft notes for a human or the evaluator, not something a
substring match can verify without false positives (a "high contraction"
target has no single measurable pass/fail line the way a banned word does).

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List

from runner.discover import dialogue_by_speaker
from runner.filesystem import _load_simple_yaml_map  # the one YAML-ish parser in this repo

VOICE_LEXICON_NAME = "voice-lexicon.yaml"


@dataclass
class Violation:
    character: str
    phrase: str
    line: str


@dataclass
class VoiceLexiconReport:
    characters: List[str] = field(default_factory=list)
    violations: List[Violation] = field(default_factory=list)
    skipped: str = ""


def load_lexicon(path: Path) -> Dict[str, Dict[str, object]]:
    """{character_slug: {never_say: [...], signature: [...], ...}}.
    Never raises on a missing file -- returns {}, matching the "no bank yet"
    contract every other advisory check in this package follows.
    """
    if not path.is_file():
        return {}
    return _load_simple_yaml_map(path)


def check_lexicon(
    lexicon_path: Path, chapter_dir: Path,
) -> VoiceLexiconReport:
    lexicon = load_lexicon(lexicon_path)
    if not lexicon:
        return VoiceLexiconReport(skipped=f"No voice lexicon at {lexicon_path}")

    if not chapter_dir.is_dir():
        return VoiceLexiconReport(characters=sorted(lexicon), skipped="no chapters to check")

    files = sorted(p for p in chapter_dir.glob("*.md") if p.is_file())
    joined = "\n\n".join(p.read_text(encoding="utf-8") for p in files)
    by_speaker, _ = dialogue_by_speaker(joined)
    # Case-insensitive match between the lexicon's slugs and the speakers
    # dialogue_by_speaker actually attributed (character names, capitalized
    # as they appear in the prose).
    speaker_by_lower = {s.lower(): s for s in by_speaker}

    violations: List[Violation] = []
    for char_key, fields in lexicon.items():
        speaker = speaker_by_lower.get(char_key.lower())
        if not speaker:
            continue
        never_say = fields.get("never_say", [])
        if not isinstance(never_say, list) or not never_say:
            continue
        for line in by_speaker[speaker]:
            for phrase in never_say:
                if re.search(r"\b" + re.escape(str(phrase)) + r"\b", line, re.IGNORECASE):
                    violations.append(Violation(character=speaker, phrase=str(phrase), line=line))

    return VoiceLexiconReport(characters=sorted(lexicon), violations=violations)


def render_report(report: VoiceLexiconReport) -> str:
    lines = ["# Voice Lexicon Check", ""]
    if report.skipped:
        lines.append(f"Skipped: {report.skipped}")
        return "\n".join(lines)

    lines.append(f"- Characters in lexicon: {len(report.characters)}")
    lines.append(f"- Violations: {len(report.violations)}")
    lines.append("")
    lines.append(f"**Verdict: {'FAIL' if report.violations else 'PASS'}**")
    lines.append("")

    if report.violations:
        lines.append("| Character | Never-say phrase | Line |")
        lines.append("|---|---|---|")
        for v in report.violations:
            excerpt = v.line if len(v.line) <= 90 else v.line[:87] + "..."
            lines.append(f'| {v.character} | "{v.phrase}" | {excerpt} |')
        lines.append("")

    return "\n".join(lines)
