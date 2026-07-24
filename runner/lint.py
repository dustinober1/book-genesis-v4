"""Deterministic manuscript lint.

Every check here exists because a human editor caught it in a finished draft.
LLMs cannot reliably count 228 em dashes or notice that 85 paragraphs open with
"I did not" - that is what code is for. The agent-side prompts handle judgment;
this module handles arithmetic.

No external dependencies, matching the rest of runner/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Tuple

from runner.discover import (
    adverb_density,
    dialogue_by_speaker,
    dialogue_ratio,
    dialogue_tag_counts,
    entity_variants,
    flesch_kincaid_grade,
    line_defects,
    modern_register_hits,
    repeated_ngrams,
    speaker_stats,
    voice_collisions,
)

# --------------------------------------------------------------------------
# Watchlists
#
# Seeded from a real editorial report on a 23,800-word historical novella.
# Counts in the comments are what the editor found in that draft.
# --------------------------------------------------------------------------

# Phrases whose repetition reads as machine-assisted prose.
DEFAULT_PHRASE_WATCHLIST: Tuple[str, ...] = (
    "exactly",              # 44 in the reference draft
    "particular",           # 31
    "my own",               # 76
    "I did not",            # 85
    "I do not know",        # 15
    "I have come to believe",  # 8
    "this account",         # 26
    "I have thought",
    "I understood",
    "I decided",
    "the truest thing",
)

# Paragraph openers that, repeated, flatten voice into a single cadence.
DEFAULT_OPENER_WATCHLIST: Tuple[str, ...] = (
    "I did not",
    "I do not",
    "I want to",
    "I have",
    "It was",
    "There was",
)

# "not X but Y" - the binary-negation construction (base scan pattern #12).
NOT_X_BUT_Y = re.compile(r"\bnot\s+[^.,;]{1,40}?\s+but\s+", re.IGNORECASE)

# A closing line that resolves into a maxim rather than an image or action.
# Heuristic, deliberately conservative: abstract nouns with no concrete anchor.
MAXIM_MARKERS = re.compile(
    r"\b(truth|memory|faith|love|fear|grief|hope|time|history|meaning|"
    r"forgiveness|silence|mercy|courage|loss)\b",
    re.IGNORECASE,
)
CONCRETE_MARKERS = re.compile(
    r"\b(hand|hands|door|gate|stair|step|bread|flour|water|floor|table|"
    r"cloth|linen|jar|lamp|oil|dust|blood|wall|roof|knee|foot|feet|"
    r"stood|sat|walked|opened|closed|carried|poured|washed|set|put)\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
WORD = re.compile(r"\b[\w'-]+\b")


@dataclass
class Finding:
    check: str
    severity: str          # "fail" | "warn" | "info"
    measured: str
    threshold: str
    detail: str = ""
    citations: List[str] = field(default_factory=list)


@dataclass
class ChapterStats:
    name: str
    words: int
    sentences: int
    em_dashes: int
    avg_sentence_len: float
    sentence_len_cv: float
    ends_on_maxim: bool
    opener_counts: Dict[str, int]


@dataclass
class LintReport:
    total_words: int
    chapters: List[ChapterStats]
    findings: List[Finding]

    @property
    def failed(self) -> bool:
        return any(f.severity == "fail" for f in self.findings)


# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Thresholds:
    """Per-check limits. Density values are per 1000 words."""
    em_dash_per_1k: float = 4.0          # reference draft: 9.6 (1 per 104 words)
    phrase_per_10k: float = 8.0          # e.g. "exactly" 44 in 23.8k = 18.5
    not_x_but_y_per_10k: float = 6.0
    opener_share: float = 0.12           # max share of paragraphs one opener may hold
    maxim_ending_share: float = 0.67     # editor asked for >=1/3 non-maxim endings
    length_cv: float = 0.30              # chapter-length coefficient of variation floor
    min_chapter_words: int = 200

    # Discovered (not watchlisted) phrase repetition.
    ngram_min_count: int = 5
    ngram_per_10k: float = 4.0

    # Prose targets. These come from the genre profile tables and were
    # previously declared but never measured.
    fk_grade_min: float = 4.0
    fk_grade_max: float = 10.0
    sentence_len_min: float = 11.0
    sentence_len_max: float = 26.0
    dialogue_ratio_min: float = 0.15
    dialogue_ratio_max: float = 0.62

    # Sentence-length monotony: a chapter can hit the manuscript-wide mean
    # above while every sentence in it is the same length. CV floor, same
    # pattern as length_cv for chapters.
    sentence_cv_min: float = 0.35
    sentence_monotony_min_sentences: int = 8

    # Phrase escalation: front-third vs back-third density. Catches a tic
    # that's rare early and common late, which a manuscript-wide average
    # dilutes into invisibility.
    escalation_min_last_per_1k: float = 0.4
    escalation_ratio: float = 2.5

    # Adverb density. 105/10k words = 10.5/1k is the bestseller-DNA target
    # already documented in skills/book-editor/SKILL.md; this is the first
    # place it's actually measured instead of just asserted.
    adverb_per_1k: float = 10.5

    # Dialogue tag variety: "said"/"asked" should dominate attribution tags.
    min_tag_sample: int = 20
    said_tag_share_min: float = 0.6

    @staticmethod
    def for_profile(profile: str) -> "Thresholds":
        """Genre/length profiles. Literary prose tolerates fewer AI tells."""
        p = (profile or "").strip().lower()
        if p in {"literary", "literary fiction"}:
            return Thresholds(em_dash_per_1k=3.0, phrase_per_10k=6.0)
        if p in {"commercial", "commercial fiction"}:
            return Thresholds(
                em_dash_per_1k=6.0, phrase_per_10k=12.0,
                fk_grade_min=4.0, fk_grade_max=8.0,
                sentence_len_min=12.0, sentence_len_max=22.0,
                dialogue_ratio_min=0.30, dialogue_ratio_max=0.62)
        if p == "thriller":
            return Thresholds(
                em_dash_per_1k=6.0, phrase_per_10k=12.0,
                fk_grade_min=4.0, fk_grade_max=8.0,
                sentence_len_min=10.0, sentence_len_max=20.0,
                dialogue_ratio_min=0.30, dialogue_ratio_max=0.62)
        if p in {"historical", "historical fiction", "biblical", "biblical fiction"}:
            # Matches the historical-fiction genre pack's override table.
            return Thresholds(
                em_dash_per_1k=3.5, phrase_per_10k=7.0,
                fk_grade_min=7.0, fk_grade_max=9.0,
                sentence_len_min=16.0, sentence_len_max=24.0,
                dialogue_ratio_min=0.25, dialogue_ratio_max=0.40)
        return Thresholds()


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def _words(text: str) -> List[str]:
    return WORD.findall(text)


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def _strip_markdown(text: str) -> str:
    text = re.sub(r"^#.*$", "", text, flags=re.MULTILINE)   # headings
    text = re.sub(r"^\s*>.*$", "", text, flags=re.MULTILINE)  # blockquotes
    return text


def _ends_on_maxim(text: str) -> bool:
    """True when the final sentence abstracts instead of showing.

    Conservative: only fires when abstract markers are present AND no concrete
    anchor is. A closing image containing the word 'memory' is not a maxim.
    """
    sents = _sentences(text)
    if not sents:
        return False
    last = sents[-1]
    return bool(MAXIM_MARKERS.search(last)) and not CONCRETE_MARKERS.search(last)


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def analyze_chapter(name: str, raw: str, openers: Tuple[str, ...]) -> ChapterStats:
    text = _strip_markdown(raw)
    words = _words(text)
    sents = _sentences(text)
    paras = _paragraphs(text)

    opener_counts: Dict[str, int] = {}
    for para in paras:
        clean = re.sub(r"^[\"'“‘]+", "", para).strip()
        for opener in openers:
            if clean.lower().startswith(opener.lower()):
                opener_counts[opener] = opener_counts.get(opener, 0) + 1
                break

    sent_lens = [float(len(WORD.findall(s))) for s in sents]
    sent_lens = [n for n in sent_lens if n > 0]
    sent_mean = _mean(sent_lens)
    sent_cv = (_stdev(sent_lens) / sent_mean) if sent_mean else 0.0

    return ChapterStats(
        name=name,
        words=len(words),
        sentences=len(sents),
        em_dashes=text.count("—") + text.count("--"),
        avg_sentence_len=(len(words) / len(sents)) if sents else 0.0,
        sentence_len_cv=sent_cv,
        ends_on_maxim=_ends_on_maxim(text),
        opener_counts=opener_counts,
    )


def lint_manuscript(
    chapter_dir: Path,
    *,
    profile: str = "",
    phrases: Tuple[str, ...] = DEFAULT_PHRASE_WATCHLIST,
    openers: Tuple[str, ...] = DEFAULT_OPENER_WATCHLIST,
    thresholds: Thresholds | None = None,
) -> LintReport:
    th = thresholds or Thresholds.for_profile(profile)

    files = sorted(p for p in chapter_dir.glob("*.md") if p.is_file())
    if not files:
        return LintReport(0, [], [Finding(
            "manuscript", "fail", "0 chapters", ">=1 chapter",
            f"No .md chapter files found in {chapter_dir}",
        )])

    raw_by_file = {p.name: p.read_text(encoding="utf-8") for p in files}
    stats = [analyze_chapter(n, r, openers) for n, r in raw_by_file.items()]
    joined = _strip_markdown("\n\n".join(raw_by_file.values()))
    total_words = sum(s.words for s in stats)
    findings: List[Finding] = []

    if total_words == 0:
        return LintReport(0, stats, [Finding(
            "manuscript", "fail", "0 words", ">0", "Chapter files are empty")])

    per_1k = total_words / 1000.0
    per_10k = total_words / 10000.0

    # -- em dash density (finding 24) --------------------------------------
    em = sum(s.em_dashes for s in stats)
    em_density = em / per_1k
    if em_density > th.em_dash_per_1k:
        worst = sorted(stats, key=lambda s: -(s.em_dashes / max(s.words, 1)))[:3]
        findings.append(Finding(
            "em_dash_density", "fail",
            f"{em} total, {em_density:.1f}/1k words (1 per {total_words // max(em, 1)})",
            f"<={th.em_dash_per_1k:.1f}/1k",
            "Excessive em dashes are the most-cited machine-prose signal.",
            [f"{s.name}: {s.em_dashes}" for s in worst],
        ))

    # -- phrase repetition (finding 24) ------------------------------------
    for phrase in phrases:
        n = len(re.findall(r"\b" + re.escape(phrase) + r"\b", joined, re.IGNORECASE))
        if n == 0:
            continue
        density = n / per_10k
        if density > th.phrase_per_10k:
            findings.append(Finding(
                "phrase_repetition", "fail",
                f'"{phrase}" x{n} ({density:.1f}/10k words)',
                f"<={th.phrase_per_10k:.1f}/10k",
                "Repeated verbal tic. Cut at least half.",
            ))

    # -- "not X but Y" (finding 24) ----------------------------------------
    nxby = len(NOT_X_BUT_Y.findall(joined))
    if nxby / per_10k > th.not_x_but_y_per_10k:
        findings.append(Finding(
            "not_x_but_y", "fail",
            f"{nxby} instances ({nxby / per_10k:.1f}/10k)",
            f"<={th.not_x_but_y_per_10k:.1f}/10k",
            "Binary-negation construction. Keep only the strongest instances.",
        ))

    # -- paragraph opener monotony (finding 24) ----------------------------
    total_paras = sum(len(_paragraphs(_strip_markdown(r))) for r in raw_by_file.values())
    agg_openers: Dict[str, int] = {}
    for s in stats:
        for k, v in s.opener_counts.items():
            agg_openers[k] = agg_openers.get(k, 0) + v
    for opener, n in sorted(agg_openers.items(), key=lambda kv: -kv[1]):
        share = n / max(total_paras, 1)
        if share > th.opener_share:
            findings.append(Finding(
                "opener_monotony", "fail",
                f'"{opener}" opens {n}/{total_paras} paragraphs ({share:.0%})',
                f"<={th.opener_share:.0%}",
                "Vary paragraph openings.",
            ))

    # -- chapter endings (finding 24) --------------------------------------
    maxim = sum(1 for s in stats if s.ends_on_maxim)
    share = maxim / len(stats)
    if share > th.maxim_ending_share:
        findings.append(Finding(
            "maxim_endings", "fail",
            f"{maxim}/{len(stats)} chapters end on a maxim ({share:.0%})",
            f"<={th.maxim_ending_share:.0%}",
            "At least a third of chapters should end on image, action, or "
            "unresolved exchange.",
            [s.name for s in stats if s.ends_on_maxim][:5],
        ))

    # -- chapter length uniformity (finding 26) ----------------------------
    lengths = [float(s.words) for s in stats]
    if len(lengths) >= 3:
        cv = _stdev(lengths) / _mean(lengths) if _mean(lengths) else 0.0
        if cv < th.length_cv:
            findings.append(Finding(
                "length_uniformity", "warn",
                f"chapter-length CV {cv:.2f} (mean {_mean(lengths):.0f} words)",
                f">={th.length_cv:.2f}",
                "Chapters are near-identical in length, which signals a template. "
                "Let scene need set length.",
            ))

    # -- runt chapters -----------------------------------------------------
    for s in stats:
        if s.words < th.min_chapter_words:
            findings.append(Finding(
                "short_chapter", "warn", f"{s.name}: {s.words} words",
                f">={th.min_chapter_words}", "Possibly a stub or truncated file.",
            ))

    # -- sentence-length monotony (rhythm) ----------------------------------
    # A manuscript-wide mean sentence length can sit comfortably in-band while
    # one chapter's sentences are all nearly identical in length - flat
    # mechanical rhythm the mean can't see. Same CV pattern as chapter-length
    # uniformity above, applied per chapter instead of across chapters.
    monotone = [
        s for s in stats
        if s.sentences >= th.sentence_monotony_min_sentences
        and s.sentence_len_cv < th.sentence_cv_min
    ]
    if monotone:
        findings.append(Finding(
            "sentence_monotony", "warn",
            f"{len(monotone)} chapter(s) below CV {th.sentence_cv_min:.2f}",
            f">={th.sentence_cv_min:.2f}",
            "Sentences in these chapters are nearly identical in length - flat "
            "rhythm even if the manuscript-wide average sentence length is fine. "
            "Vary short/long on purpose.",
            [f"{s.name}: CV {s.sentence_len_cv:.2f} ({s.sentences} sentences)"
             for s in monotone[:6]],
        ))

    # -- discovered phrase repetition --------------------------------------
    # The watchlist above only finds tics someone predicted. This finds the
    # book's own, which is where the real damage usually is.
    stripped_by_file = {n: _strip_markdown(r) for n, r in raw_by_file.items()}
    ngram_hits = repeated_ngrams(
        stripped_by_file,
        min_count=th.ngram_min_count,
        min_per_10k=th.ngram_per_10k,
    )
    for hit in ngram_hits:
        if any(hit.phrase in f.measured.lower() for f in findings
               if f.check == "phrase_repetition"):
            continue  # already reported via the watchlist
        findings.append(Finding(
            "discovered_repetition", "warn",
            f'"{hit.phrase}" x{hit.count} ({hit.per_10k:.1f}/10k, {hit.chapters} chapters)',
            f"<={th.ngram_per_10k:.1f}/10k",
            "Recurring construction not on any watchlist. Verify it is deliberate.",
        ))

    # -- phrase escalation (front-third vs back-third density) -------------
    # "A phrase used twice in chapter 2 becomes eighty uses by chapter 14" -
    # a manuscript-wide average dilutes exactly this pattern into invisibility
    # because the early chapters drag the mean down. Compare thirds instead.
    if len(stats) >= 6:
        third = max(1, len(stats) // 3)
        first_names = [s.name for s in stats[:third]]
        last_names = [s.name for s in stats[-third:]]
        first_text = _strip_markdown("\n\n".join(raw_by_file[n] for n in first_names))
        last_text = _strip_markdown("\n\n".join(raw_by_file[n] for n in last_names))
        first_1k = max(len(WORD.findall(first_text)) / 1000.0, 0.001)
        last_1k = max(len(WORD.findall(last_text)) / 1000.0, 0.001)

        seen_escalation: set = set()
        for phrase in list(phrases) + [h.phrase for h in ngram_hits]:
            key = phrase.lower()
            if key in seen_escalation:
                continue
            seen_escalation.add(key)
            pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
            first_n = len(pattern.findall(first_text))
            last_n = len(pattern.findall(last_text))
            first_d = first_n / first_1k
            last_d = last_n / last_1k
            if last_d < th.escalation_min_last_per_1k:
                continue
            if first_d > 0 and last_d / first_d < th.escalation_ratio:
                continue
            if first_d == 0 and last_n < 2:
                continue
            findings.append(Finding(
                "phrase_escalation", "warn",
                f'"{phrase}": {first_d:.2f}/1k early -> {last_d:.2f}/1k late',
                f"<={th.escalation_ratio:.1f}x growth",
                "This tic compounds across the manuscript - rare early, common "
                "late. A whole-book average would have hidden it.",
            ))

    # -- readability and dialogue ratio ------------------------------------
    fk = flesch_kincaid_grade(joined)
    if not (th.fk_grade_min <= fk <= th.fk_grade_max):
        findings.append(Finding(
            "readability", "warn", f"Flesch-Kincaid grade {fk:.1f}",
            f"{th.fk_grade_min:.1f}-{th.fk_grade_max:.1f}",
            "Outside the profile's band. Too low reads as modern-commercial in a "
            "period setting; too high costs readers.",
        ))

    asl = _mean([s.avg_sentence_len for s in stats])
    if not (th.sentence_len_min <= asl <= th.sentence_len_max):
        findings.append(Finding(
            "sentence_length", "warn", f"mean {asl:.1f} words/sentence",
            f"{th.sentence_len_min:.0f}-{th.sentence_len_max:.0f}",
            "Outside the profile's band.",
        ))

    dr = dialogue_ratio(joined)
    if not (th.dialogue_ratio_min <= dr <= th.dialogue_ratio_max):
        findings.append(Finding(
            "dialogue_ratio", "warn", f"{dr:.0%} of words are in dialogue",
            f"{th.dialogue_ratio_min:.0%}-{th.dialogue_ratio_max:.0%}",
            "Outside the profile's band.",
        ))

    # -- adverb density ------------------------------------------------------
    adverb_n, adverb_total = adverb_density(joined)
    adverb_1k = (adverb_n / (adverb_total / 1000.0)) if adverb_total else 0.0
    if adverb_1k > th.adverb_per_1k:
        findings.append(Finding(
            "adverb_density", "warn",
            f"{adverb_n} '-ly' words, {adverb_1k:.1f}/1k words",
            f"<={th.adverb_per_1k:.1f}/1k",
            "Heuristic ('-ly' words minus a stopword list of non-adverbs like "
            "'family', 'only', 'likely'), so treat as a prompt to sample, not "
            "an exact count.",
        ))

    # -- dialogue tag variety -------------------------------------------------
    tag_counts = dialogue_tag_counts(joined)
    total_tags = sum(tag_counts.values())
    if total_tags >= th.min_tag_sample:
        plain_share = (tag_counts.get("said", 0) + tag_counts.get("asked", 0)) / total_tags
        if plain_share < th.said_tag_share_min:
            fancy = {k: v for k, v in tag_counts.items() if k not in ("said", "asked")}
            top_fancy = sorted(fancy.items(), key=lambda kv: -kv[1])[:6]
            findings.append(Finding(
                "dialogue_tag_variety", "warn",
                f'"said"/"asked" are {plain_share:.0%} of {total_tags} attribution tags',
                f">={th.said_tag_share_min:.0%}",
                "Bestseller dialogue defaults to \"said\"/\"asked\" - readers skip "
                "past them but stumble on synonym tags. Frequent \"exclaimed\", "
                "\"retorted\", etc. reads as amateur or AI-assisted.",
                [f'"{k}" x{v}' for k, v in top_fancy],
            ))

    # -- voice collisions -----------------------------------------------------
    # Automates the "cover the name" test: do two speaking characters' dialogue
    # signatures (line length, question rate, contraction rate) measure as
    # indistinguishable? A hit is a prompt to read the lines, not a verdict -
    # matching numbers are necessary but not sufficient for real differentiation.
    by_speaker, _ = dialogue_by_speaker(joined)
    speakers = speaker_stats(by_speaker)
    collisions = voice_collisions(speakers)
    if collisions:
        findings.append(Finding(
            "voice_collision", "warn",
            f"{len(collisions)} pair(s) statistically indistinguishable",
            "0 collisions",
            "Measurable dialogue signature (avg line length, question rate, "
            "contraction rate) matches closely enough that the cover-the-name "
            "test would likely fail. Differentiate speech patterns.",
            [f"{a} / {b}" for a, b in collisions],
        ))

    # -- modern register ---------------------------------------------------
    modern = modern_register_hits(joined)
    if modern:
        listed = ", ".join(f"{k} x{v}" for k, v in
                           sorted(modern.items(), key=lambda kv: -kv[1])[:8])
        findings.append(Finding(
            "modern_register", "warn", f"{len(modern)} terms: {listed}",
            "0 in a pre-modern setting",
            "Modern abstraction. Harmless in contemporary fiction; anachronistic "
            "otherwise unless the text frames it as translation.",
        ))

    # -- entity spelling variants ------------------------------------------
    for group in entity_variants(joined):
        spellings = ", ".join(f'"{k}" x{v}' for k, v in
                              sorted(group.variants.items(), key=lambda kv: -kv[1]))
        findings.append(Finding(
            "entity_variant", "warn", spellings, "one spelling per entity",
            "Same term spelled more than one way. Fix in the style sheet.",
        ))

    # -- mechanical line defects -------------------------------------------
    defects = line_defects(stripped_by_file)
    if defects:
        by_label: Dict[str, int] = {}
        for _, label, _ in defects:
            by_label[label] = by_label.get(label, 0) + 1
        findings.append(Finding(
            "line_defect", "warn",
            ", ".join(f"{k} x{v}" for k, v in sorted(by_label.items(), key=lambda kv: -kv[1])),
            "0",
            "Mechanical punctuation and spacing defects.",
            [f"{ch}: {ex[:90]}" for ch, _, ex in defects[:6]],
        ))

    return LintReport(total_words, stats, findings)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_report(report: LintReport) -> str:
    lines = ["# Manuscript Lint", ""]
    lines.append(f"- Total words: {report.total_words:,}")
    lines.append(f"- Chapters: {len(report.chapters)}")
    if report.chapters:
        avg = _mean([float(c.words) for c in report.chapters])
        lines.append(f"- Mean chapter length: {avg:,.0f} words")
    lines.append("")

    fails = [f for f in report.findings if f.severity == "fail"]
    warns = [f for f in report.findings if f.severity == "warn"]

    lines.append(f"**Verdict: {'FAIL' if fails else 'PASS'}** "
                 f"({len(fails)} fail, {len(warns)} warn)")
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
