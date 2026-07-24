"""Unsupervised manuscript analysis.

lint.py checks a fixed watchlist - it only finds tics someone predicted. This
module finds the ones nobody predicted, which is the harder and more useful half:

- repeated_ngrams:   over-represented phrases, discovered rather than listed
- entity_variants:   the same name or compound spelled more than one way
- presence_matrix:   which named characters appear in which chapters
- dialogue_by_speaker: quoted speech attributed and measured per speaker
- readability:       Flesch-Kincaid and dialogue ratio

All of these are mechanical. A model asked to do them by reading will make
arithmetic and recall errors that scale with manuscript length.

No external dependencies.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, Iterable, List, Sequence, Set, Tuple

WORD = re.compile(r"\b[\w'’-]+\b")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"'”’\s]+")

# Function words. An n-gram made only of these is grammar, not a verbal tic.
FUNCTION_WORDS: Set[str] = {
    "a", "an", "and", "as", "at", "be", "been", "but", "by", "did", "do", "for",
    "from", "had", "has", "have", "he", "her", "him", "his", "i", "if", "in",
    "is", "it", "its", "me", "my", "not", "of", "on", "or", "our", "out", "she",
    "so", "than", "that", "the", "their", "them", "then", "there", "they",
    "this", "to", "up", "was", "we", "were", "what", "when", "which", "who",
    "will", "with", "would", "you", "your", "am", "are", "no", "nor", "into",
    "over", "under", "again", "more", "most", "such", "only", "own", "same",
    "too", "very", "can", "could", "should", "now", "here", "how", "all",
}

# Modern register that reads as anachronistic in pre-modern settings.
# Seeded from an editorial report; extend per project in the period bible.
MODERN_REGISTER: Tuple[str, ...] = (
    "liability", "oversight", "governance", "apparatus", "configuration",
    "formalized", "formalised", "installments", "instalments", "protocol",
    "infrastructure", "logistics", "parameters", "framework", "leverage",
    "process", "boundaries", "closure", "trauma", "self-worth", "validate",
    "prioritize", "prioritise", "dynamic", "systemic", "optimize", "optimise",
)

# "-ly" words that are adjectives/nouns, not adverbs - excluded so adverb
# density doesn't fire on ordinary vocabulary. Not exhaustive; extend per
# project if a false positive shows up in a report.
ADVERB_EXCLUDE: Set[str] = {
    "family", "only", "early", "holy", "ally", "supply", "apply", "rely",
    "imply", "reply", "comply", "multiply", "monopoly", "anomaly", "assembly",
    "fly", "butterfly", "likely", "unlikely", "friendly", "unfriendly",
    "lonely", "lovely", "lively", "homely", "orderly", "disorderly", "costly",
    "deadly", "ghostly", "kindly", "unkindly", "leisurely", "lowly", "manly",
    "womanly", "monthly", "weekly", "yearly", "daily", "hourly", "elderly",
    "stately", "timely", "untimely", "goodly", "gadfly", "dragonfly",
    "belly", "bully", "silly", "jolly", "folly", "rally", "chilly", "ugly",
}
ADVERB_WORD = re.compile(r"\b(\w+ly)\b")

# Dialogue attribution verbs surveyed for "said"/"asked" dominance.
# Bestseller-DNA target: "said" as dominant tag - see skills/book-editor/SKILL.md.
DIALOGUE_TAG_VERBS: Tuple[str, ...] = (
    "said", "asked", "replied", "answered", "told", "whispered", "shouted",
    "murmured", "muttered", "exclaimed", "cried", "retorted", "snapped",
    "hissed", "growled", "drawled", "sighed", "breathed", "admitted",
    "continued", "added", "interrupted", "insisted", "protested", "demanded",
    "offered", "suggested", "warned", "agreed", "countered", "argued",
    "laughed", "chuckled", "grumbled", "stammered", "sneered",
)
_TAG_VERB_ALT = "|".join(DIALOGUE_TAG_VERBS)
# Post-tag: '"...," said Mary.' - verb right after the closing quote.
TAG_AFTER_QUOTE = re.compile(
    r'["”]\s*,?\s*(' + _TAG_VERB_ALT + r")\b", re.IGNORECASE)
# Pre-tag: 'Mary said, "..."' - verb right before the opening quote, name
# (or pronoun) immediately before the verb.
TAG_BEFORE_QUOTE = re.compile(
    r"\b\w+\s+(" + _TAG_VERB_ALT + r')[,:]?\s*["“]', re.IGNORECASE)

# Mechanical line defects - pure pattern, zero judgment.
# Purely-typographic defects (repeated whitespace, four-or-more dots,
# doubled words) live in runner/proof.py instead — proof answers "is this
# typographically broken" (objective, fail-severity), while lint (via this
# list) answers "does this read as machine-written" (stylistic, mostly
# warn). Keeping both here would double-report the same defect at two
# different severities.
LINE_DEFECTS: Tuple[Tuple[str, str], ...] = (
    (r",\s*[—–-]{1,2}\s", "comma immediately before a dash"),
    (r"\s[—–]\s*,", "dash immediately before a comma"),
    (r"[!?]{2,}", "repeated terminal punctuation"),
    (r"[“”\"][^“”\"]{0,3}[“”\"]", "empty or near-empty quotation"),
)

VOWEL_GROUP = re.compile(r"[aeiouy]+")


# --------------------------------------------------------------------------
# Repeated n-grams
# --------------------------------------------------------------------------

@dataclass
class NgramHit:
    phrase: str
    count: int
    per_10k: float
    chapters: int


def _tokens(text: str) -> List[str]:
    return [w.lower() for w in WORD.findall(text)]


def _is_contentful(gram: Sequence[str]) -> bool:
    """Reject n-grams that are pure grammar."""
    content = [w for w in gram if w not in FUNCTION_WORDS]
    if not content:
        return False
    # "of the house" is one content word carried by two function words - allow
    # it only when the phrase is short enough to be a real tic.
    return len(content) >= 1 and (len(content) / len(gram)) >= 0.34


def repeated_ngrams(
    chapter_texts: Dict[str, str],
    *,
    min_n: int = 3,
    min_count: int = 5,
    min_per_10k: float = 4.0,
    min_chapters: int = 2,
    top: int = 25,
    max_span: int = 40,
) -> List[NgramHit]:
    """Discover over-represented phrases without being told what to look for.

    Finds *maximal* repeats: a seed n-gram is extended left and right only while
    every one of its occurrences agrees on the next token. That yields the span
    that genuinely repeats, rather than a dozen overlapping windows of it.

    Requires recurrence across multiple chapters, which separates an authorial
    tic from a phrase repeated deliberately inside one scene.
    """
    chapters = list(chapter_texts.items())
    token_lists = [(name, _tokens(text)) for name, text in chapters]
    total_words = sum(len(t) for _, t in token_lists)
    if total_words == 0:
        return []
    per_10k_factor = total_words / 10000.0

    # Seed positions for every min_n-gram.
    positions: Dict[Tuple[str, ...], List[Tuple[int, int]]] = defaultdict(list)
    for ci, (_, toks) in enumerate(token_lists):
        for i in range(len(toks) - min_n + 1):
            gram = tuple(toks[i:i + min_n])
            if _is_contentful(gram):
                positions[gram].append((ci, i))

    def token_at(ci: int, idx: int) -> str | None:
        toks = token_lists[ci][1]
        return toks[idx] if 0 <= idx < len(toks) else None

    results: List[NgramHit] = []
    consumed: Set[Tuple[str, ...]] = set()

    for gram, occ in sorted(positions.items(), key=lambda kv: -len(kv[1])):
        if len(occ) < min_count or gram in consumed:
            continue
        if len({ci for ci, _ in occ} ) < min_chapters:
            continue

        start = list(occ)
        left, right = 0, 0

        # Extend right while every occurrence agrees.
        while min_n + left + right < max_span:
            nxt = {token_at(ci, i + min_n + right) for ci, i in start}
            if len(nxt) != 1 or None in nxt:
                break
            right += 1

        # Then left.
        while min_n + left + right < max_span:
            prv = {token_at(ci, i - left - 1) for ci, i in start}
            if len(prv) != 1 or None in prv:
                break
            left += 1

        ci0, i0 = start[0]
        span = tuple(token_lists[ci0][1][i0 - left:i0 + min_n + right])
        count = len(start)
        density = count / per_10k_factor
        if density < min_per_10k:
            continue

        # Mark every sub-window of this span so it is not reported again.
        for n in range(min_n, len(span) + 1):
            for i in range(len(span) - n + 1):
                consumed.add(span[i:i + n])

        results.append(NgramHit(
            " ".join(span), count, density, len({ci for ci, _ in start})))

    # Drop any span that is a substring of a longer reported span.
    results.sort(key=lambda h: -len(h.phrase))
    deduped: List[NgramHit] = []
    for h in results:
        if any(h.phrase in k.phrase for k in deduped):
            continue
        deduped.append(h)

    # Rank by damage, not raw frequency. A ten-word sentence repeated seven
    # times is a far worse finding than a three-word prepositional phrase
    # repeated sixty times - the latter is usually just English.
    deduped.sort(key=lambda h: -(h.count * len(h.phrase.split()) ** 2))
    return deduped[:top]


# --------------------------------------------------------------------------
# Entity variants
# --------------------------------------------------------------------------

@dataclass
class VariantGroup:
    canonical: str
    variants: Dict[str, int]


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _normalize_compound(word: str) -> str:
    return word.replace("-", "").replace("’", "'").lower()


def entity_variants(
    text: str,
    *,
    min_count: int = 3,
    max_distance: int = 3,
) -> List[VariantGroup]:
    """Find one entity spelled several ways.

    Catches both transliteration pairs (Miryam/Mary, Kefa/Peter cannot be caught
    by distance alone and must be declared in the style sheet) and the mechanical
    cases that distance does catch: storeroom/store-room, roof tax/roof-tax,
    Bar-Abbas/Barabbas.
    """
    # Capitalized tokens, excluding sentence-initial function words - "The" and
    # "That" are grammar, not entities.
    caps: Counter = Counter()
    for m in re.finditer(r"\b[A-Z][\w'’-]{2,}\b", text):
        tok = m.group(0)
        if tok.lower() in FUNCTION_WORDS:
            continue
        caps[tok] += 1
    caps = Counter({w: c for w, c in caps.items() if c >= min_count})

    # Spelling variants keyed on the separator-stripped form, so
    # storeroom / store-room / store room and Barabbas / Bar-Abbas collapse
    # to one key. Scanned in three passes because a single greedy regex
    # tokenizes "the store-room" into "the store" + "room" and the hyphenated
    # compound never assembles.
    forms: Dict[str, Counter] = defaultdict(Counter)

    def record(raw: str) -> None:
        if len(raw) < 5:
            return
        key = _normalize_compound(raw)
        if key in FUNCTION_WORDS:
            return
        forms[key][raw.lower()] += 1

    # 1. Hyphenated compounds (unambiguous).
    for m in re.finditer(r"\b[\w'’]+(?:-[\w'’]+)+\b", text):
        record(m.group(0))

    # 2. Single tokens.
    for m in re.finditer(r"\b[\w'’]+\b", text):
        record(m.group(0))

    # 3. Space-separated pairs, skipping any pair touching a function word so
    #    "the store" never becomes a key while "roof tax" does.
    tokens = [(m.group(0), m.start()) for m in re.finditer(r"\b[\w'’]+\b", text)]
    for (w1, _), (w2, _) in zip(tokens, tokens[1:]):
        if w1.lower() in FUNCTION_WORDS or w2.lower() in FUNCTION_WORDS:
            continue
        record(f"{w1} {w2}")

    groups: List[VariantGroup] = []

    for key, variants in forms.items():
        distinct = {v: c for v, c in variants.items() if c >= min_count}
        if len(distinct) > 1:
            canonical = max(distinct.items(), key=lambda kv: kv[1])[0]
            groups.append(VariantGroup(canonical, dict(distinct)))

    # Near-identical capitalized tokens.
    seen: Set[str] = set()
    words = sorted(caps, key=lambda w: -caps[w])
    for i, w1 in enumerate(words):
        if w1 in seen:
            continue
        cluster = {w1: caps[w1]}
        for w2 in words[i + 1:]:
            if w2 in seen or w2 == w1:
                continue
            if _normalize_compound(w1) == _normalize_compound(w2):
                continue  # already handled as a compound
            d = _levenshtein(w1.lower(), w2.lower())
            if 0 < d <= max_distance and abs(len(w1) - len(w2)) <= max_distance:
                cluster[w2] = caps[w2]
                seen.add(w2)
        if len(cluster) > 1:
            seen.add(w1)
            groups.append(VariantGroup(w1, cluster))

    return groups


# --------------------------------------------------------------------------
# Character presence
# --------------------------------------------------------------------------

def presence_matrix(
    chapter_texts: Dict[str, str],
    names: Iterable[str],
) -> Dict[str, Dict[str, int]]:
    """{name: {chapter: mentions}} for every supplied character name."""
    matrix: Dict[str, Dict[str, int]] = {}
    for name in names:
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        matrix[name] = {
            ch: len(pattern.findall(text)) for ch, text in chapter_texts.items()
        }
    return matrix


def absence_gaps(
    matrix: Dict[str, Dict[str, int]],
    chapter_order: Sequence[str],
    *,
    min_gap: int = 3,
) -> Dict[str, List[Tuple[str, str, int]]]:
    """Characters present early and late but missing through a long middle run."""
    gaps: Dict[str, List[Tuple[str, str, int]]] = {}
    for name, per_ch in matrix.items():
        present = [c for c in chapter_order if per_ch.get(c, 0) > 0]
        if len(present) < 2:
            continue
        first, last = chapter_order.index(present[0]), chapter_order.index(present[-1])
        run_start = None
        found: List[Tuple[str, str, int]] = []
        for idx in range(first, last + 1):
            ch = chapter_order[idx]
            if per_ch.get(ch, 0) == 0:
                run_start = idx if run_start is None else run_start
            else:
                if run_start is not None and idx - run_start >= min_gap:
                    found.append((chapter_order[run_start], chapter_order[idx - 1],
                                  idx - run_start))
                run_start = None
        if found:
            gaps[name] = found
    return gaps


# --------------------------------------------------------------------------
# Dialogue
# --------------------------------------------------------------------------

DIALOGUE = re.compile(r"[“\"]([^”\"]{2,})[”\"]")
ATTRIB_AFTER = re.compile(
    r"^[,\.\s]*(?:said|asked|replied|answered|told|whispered|shouted)\s+([A-Z][\w'’-]+)")
ATTRIB_BEFORE = re.compile(r"([A-Z][\w'’-]+)\s+(?:said|asked|replied|answered)[,:]?\s*$")


@dataclass
class SpeakerStats:
    speaker: str
    lines: int
    words: int
    avg_line_words: float
    question_rate: float
    contraction_rate: float
    qualifier_rate: float
    top_words: List[Tuple[str, int]] = field(default_factory=list)


QUALIFIERS = {"perhaps", "maybe", "possibly", "somewhat", "rather", "quite",
              "seems", "seemed", "suppose", "believe", "think", "might"}


def dialogue_by_speaker(text: str) -> Tuple[Dict[str, List[str]], int]:
    """Return ({speaker: [lines]}, total_dialogue_words). Unattributed -> '?'.

    A speech split across several quoted spans in one paragraph carries its
    attribution forward: '"I will not," said Mary. "The house is mine."' is
    two spans but one speaker. Without the carry, the second span lands in '?'
    and every speaker's average line length is skewed short, which makes
    distinct voices look statistically identical.
    """
    by_speaker: Dict[str, List[str]] = defaultdict(list)
    total_words = 0

    for para in re.split(r"\n\s*\n", text):
        current = "?"
        for m in DIALOGUE.finditer(para):
            line = m.group(1).strip()
            total_words += len(WORD.findall(line))
            after = para[m.end():m.end() + 60]
            before = para[max(0, m.start() - 60):m.start()]
            am = ATTRIB_AFTER.match(after)
            bm = ATTRIB_BEFORE.search(before)
            if am:
                current = am.group(1)
            elif bm:
                current = bm.group(1)
            # else: keep `current` - continuation of the same speech.
            by_speaker[current].append(line)

    return dict(by_speaker), total_words


def speaker_stats(by_speaker: Dict[str, List[str]], *, min_lines: int = 5) -> List[SpeakerStats]:
    out: List[SpeakerStats] = []
    for speaker, lines in by_speaker.items():
        if speaker == "?" or len(lines) < min_lines:
            continue
        words = [w.lower() for line in lines for w in WORD.findall(line)]
        if not words:
            continue
        questions = sum(1 for l in lines if l.rstrip().endswith("?"))
        contractions = sum(1 for w in words if "'" in w or "’" in w)
        quals = sum(1 for w in words if w in QUALIFIERS)
        content = Counter(w for w in words if w not in FUNCTION_WORDS)
        out.append(SpeakerStats(
            speaker=speaker,
            lines=len(lines),
            words=len(words),
            avg_line_words=len(words) / len(lines),
            question_rate=questions / len(lines),
            contraction_rate=contractions / len(words),
            qualifier_rate=quals / len(words),
            top_words=content.most_common(5),
        ))
    out.sort(key=lambda s: -s.lines)
    return out


def voice_collisions(
    stats: Sequence[SpeakerStats],
    *,
    line_word_gap: float = 1.5,
    question_gap: float = 0.10,
    contraction_gap: float = 0.02,
) -> List[Tuple[str, str]]:
    """Speaker pairs whose measurable dialogue signature is indistinguishable.

    Automates the "cover the name" test: if you covered the attribution, could
    you tell these two characters apart from the dialogue alone? A close match
    on average line length, question rate, and contraction rate says no -
    necessary but not sufficient for real differentiation. Treat a hit as a
    prompt to read the lines, not as a verdict.
    """
    collisions: List[Tuple[str, str]] = []
    for i, a in enumerate(stats):
        for b in stats[i + 1:]:
            if (abs(a.avg_line_words - b.avg_line_words) < line_word_gap
                    and abs(a.question_rate - b.question_rate) < question_gap
                    and abs(a.contraction_rate - b.contraction_rate) < contraction_gap):
                collisions.append((a.speaker, b.speaker))
    return collisions


# --------------------------------------------------------------------------
# Readability
# --------------------------------------------------------------------------

def _syllables(word: str) -> int:
    groups = VOWEL_GROUP.findall(word.lower())
    n = len(groups)
    if word.lower().endswith("e") and n > 1:
        n -= 1
    return max(n, 1)


def flesch_kincaid_grade(text: str) -> float:
    words = WORD.findall(text)
    sentences = [s for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if not words or not sentences:
        return 0.0
    syl = sum(_syllables(w) for w in words)
    return 0.39 * (len(words) / len(sentences)) + 11.8 * (syl / len(words)) - 15.59


def dialogue_ratio(text: str) -> float:
    total = len(WORD.findall(text))
    if total == 0:
        return 0.0
    spoken = sum(len(WORD.findall(m.group(1))) for m in DIALOGUE.finditer(text))
    return spoken / total


def adverb_density(text: str) -> Tuple[int, int]:
    """(adverb_count, total_words). Heuristic: '-ly' words minus a stopword
    list of '-ly' adjectives/nouns (family, only, likely...). Imprecise by
    nature - it will miss adverbs that don't end in -ly and occasionally
    over/under count - but it is the same cheap signal already used ad hoc
    elsewhere in this pipeline, now with a threshold instead of just a count.
    """
    words = WORD.findall(text)
    total = len(words)
    n = sum(
        1 for w in words
        if len(w) > 3 and w.lower().endswith("ly")
        and w.lower() not in ADVERB_EXCLUDE
    )
    return n, total


def dialogue_tag_counts(text: str) -> Counter:
    """Tally dialogue attribution verbs ('said', 'exclaimed', 'retorted'...).

    Used to check that 'said'/'asked' dominate, per the bestseller-DNA target.
    Frequent synonym tags are a common amateur/AI tell - readers skip past
    'said' but stumble on 'ejaculated' or 'opined'.
    """
    counts: Counter = Counter()
    for m in TAG_AFTER_QUOTE.finditer(text):
        counts[m.group(1).lower()] += 1
    for m in TAG_BEFORE_QUOTE.finditer(text):
        counts[m.group(1).lower()] += 1
    return counts


def modern_register_hits(text: str, extra: Iterable[str] = ()) -> Dict[str, int]:
    hits: Dict[str, int] = {}
    for term in tuple(MODERN_REGISTER) + tuple(extra):
        n = len(re.findall(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE))
        if n:
            hits[term] = n
    return hits


def line_defects(chapter_texts: Dict[str, str]) -> List[Tuple[str, str, str]]:
    """[(chapter, defect description, excerpt)] - mechanical only."""
    out: List[Tuple[str, str, str]] = []
    for name, text in chapter_texts.items():
        for pattern, label in LINE_DEFECTS:
            # Case-insensitive: the common doubled-word typo straddles a
            # sentence boundary ("... home. She she went ...").
            for m in re.finditer(pattern, text, re.IGNORECASE):
                start = max(0, m.start() - 30)
                excerpt = text[start:m.end() + 30].replace("\n", " ").strip()
                out.append((name, label, excerpt))
    return out


def load_chapters(chapter_dir: Path) -> Dict[str, str]:
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(chapter_dir.glob("*.md")) if p.is_file()
    }


def detect_names(text: str, *, min_count: int = 3, top: int = 15) -> List[str]:
    # min_count is deliberately low: a character appearing in only three
    # chapters is precisely the one an absence-gap check needs to see.
    """Guess the cast: frequent capitalized tokens that are not sentence-initial
    grammar and not the first word of a sentence more often than not."""
    counts: Counter = Counter()
    initial: Counter = Counter()
    for m in re.finditer(r"(^|[.!?][\"'”’\s]+|\n\s*)?\b([A-Z][\w'’-]{2,})\b", text):
        tok = m.group(2)
        if tok.lower() in FUNCTION_WORDS:
            continue
        counts[tok] += 1
        if m.group(1):
            initial[tok] += 1
    names = [
        w for w, c in counts.items()
        if c >= min_count and initial[w] / c < 0.85   # not merely sentence-openers
    ]
    names.sort(key=lambda w: -counts[w])
    return names[:top]


def render_structure_report(
    chapter_texts: Dict[str, str],
    names: Sequence[str] | None = None,
) -> str:
    """Presence matrix + per-speaker dialogue metrics for audit Passes 10-12."""
    order = list(chapter_texts.keys())
    joined = "\n\n".join(chapter_texts.values())
    cast = list(names) if names else detect_names(joined)

    lines = ["# Structure Report", "", f"Chapters: {len(order)}", ""]

    lines.append("## Character Presence (mentions per chapter)")
    lines.append("")
    matrix = presence_matrix(chapter_texts, cast)
    header = "| Character | " + " | ".join(c.replace(".md", "") for c in order) + " |"
    lines.append(header)
    lines.append("|---" * (len(order) + 1) + "|")
    for name in cast:
        row = matrix[name]
        cells = " | ".join(str(row.get(c, 0) or "·") for c in order)
        lines.append(f"| {name} | {cells} |")
    lines.append("")

    gaps = absence_gaps(matrix, order, min_gap=3)
    lines.append("## Absence Gaps (present early and late, missing through the middle)")
    lines.append("")
    if gaps:
        for name, runs in gaps.items():
            for start, end, size in runs:
                lines.append(
                    f"- **{name}** absent for {size} chapters "
                    f"({start.replace('.md','')} → {end.replace('.md','')})")
        lines.append("")
        lines.append("A character strong at the start and end but missing through "
                     "the middle makes the climax feel bolted on.")
    else:
        lines.append("None.")
    lines.append("")

    lines.append("## Dialogue by Speaker")
    lines.append("")
    stats = speaker_stats(dialogue_by_speaker(joined)[0])
    if not stats:
        lines.append("No attributed dialogue found. If the book has dialogue, the "
                     "attribution pattern is unusual - check manually.")
        return "\n".join(lines)

    lines.append("| Speaker | Lines | Avg words/line | Questions | Contractions | Qualifiers |")
    lines.append("|---|---|---|---|---|---|")
    for s in stats:
        lines.append(
            f"| {s.speaker} | {s.lines} | {s.avg_line_words:.1f} | "
            f"{s.question_rate:.0%} | {s.contraction_rate:.1%} | {s.qualifier_rate:.1%} |")
    lines.append("")

    # Flag speakers whose measurable signature is near-identical.
    collisions = voice_collisions(stats)
    lines.append("## Voice Collisions")
    lines.append("")
    if collisions:
        for a, b in collisions:
            lines.append(f"- {a} / {b} — statistically indistinguishable")
        lines.append("")
        lines.append("These are measurements, not a verdict: matching numbers mean "
                     "the *measurable* signature is identical, which is necessary "
                     "but not sufficient for real differentiation. Read the lines.")
    else:
        lines.append("No two speakers share a measurable signature.")
    return "\n".join(lines)
