"""Tests for the deterministic manuscript checks.

Cases are drawn from a real editorial report so the suite proves the tooling
catches what a human editor caught.
"""

from pathlib import Path
import shutil
import sys
import tempfile
from typing import List
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.lint import (  # noqa: E402
    Thresholds,
    lint_manuscript,
    render_report,
)
from runner.timeline import (  # noqa: E402
    parse_timeline,
    render_issues,
    validate,
)
from runner.discover import (  # noqa: E402
    absence_gaps,
    adverb_density,
    dialogue_by_speaker,
    dialogue_ratio,
    dialogue_tag_counts,
    entity_variants,
    flesch_kincaid_grade,
    line_defects,
    modern_register_hits,
    presence_matrix,
    repeated_ngrams,
    sentence_opener_repeats,
    speaker_drift,
    speaker_stats,
    strip_comments,
    voice_collisions,
    window_echoes,
)


def _findings(report, check):
    return [f for f in report.findings if f.check == check]


def _words_with_dashes(word_count: int, dash_count: int) -> str:
    """Exactly `word_count` words with exactly `dash_count` standalone em
    dashes spaced evenly through them -- an em dash is not itself a word
    (WORD in lint.py/discover.py doesn't match `—`), so this gives a
    precise, reproducible density instead of an approximate one."""
    tokens: List[str] = []
    inserted = 0
    step = max(word_count // max(dash_count, 1), 1)
    for i in range(word_count):
        tokens.append("step")
        if inserted < dash_count and (i + 1) % step == 0:
            tokens.append("—")
            inserted += 1
    return " ".join(tokens) + "."


class LintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-lint-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write(self, name: str, body: str) -> None:
        (self.chapters / name).write_text(body, encoding="utf-8")

    def test_clean_prose_passes(self) -> None:
        body = " ".join(
            f"She set the bread on the table and counted the jars in row {i}."
            for i in range(80)
        )
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(report.failed, render_report(report))

    def test_em_dash_density_flagged(self) -> None:
        # Reference draft ran 1 em dash per 104 words. Reproduce that rate.
        sentence = "She counted the jars — the ones from the north room — again. "
        self._write("ch01.md", sentence * 60)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "em_dash_density")
        self.assertTrue(found, "expected em dash density failure")
        self.assertEqual("fail", found[0].severity)

    def test_writer_header_comment_not_counted_as_em_dash(self) -> None:
        # agents/book-writer.md mandates a `<!-- Word count: X | Target: Y |
        # Anchor: ... -->` header on every chapter. `<!--`/`-->` each contain
        # `--`, which analyze_chapter used to count as an em dash before
        # _strip_markdown learned to drop comments -- one header alone was
        # +2 phantom em dashes per chapter, and human-pass span markers
        # (`<!-- hp:start -->`) would add two more per span.
        body = (
            "<!-- Word count: 900 | Target: 900 | Anchor: the door -->\n\n"
            + "She set the bread on the table and counted the jars again. " * 40
        )
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(
            _findings(report, "em_dash_density"),
            "a metadata comment must not register as prose em dashes",
        )

    def test_phrase_repetition_flagged(self) -> None:
        body = ("I did not know exactly what he meant by that particular remark. "
                * 40)
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        flagged = {f.measured.split('"')[1] for f in _findings(report, "phrase_repetition")}
        self.assertIn("exactly", flagged)
        self.assertIn("particular", flagged)
        self.assertIn("I did not", flagged)

    def test_not_x_but_y_flagged(self) -> None:
        body = "It was not fear but habit that moved her hand to the latch. " * 40
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertTrue(_findings(report, "not_x_but_y"))

    def test_paragraph_opener_monotony_flagged(self) -> None:
        paras = ["I did not answer him that morning."] * 8 + [
            "The gate stood open until noon.",
            "Rain came through the roof seam.",
        ]
        self._write("ch01.md", "\n\n".join(paras))
        report = lint_manuscript(self.chapters)
        self.assertTrue(_findings(report, "opener_monotony"))

    def test_word_echo_flagged(self) -> None:
        body = " ".join(
            f"He shouldered the door. His shoulder ached from the strap. "
            f"Row {i} was still empty." for i in range(20)
        )
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        flagged = {f.measured.split('"')[1] for f in _findings(report, "word_echo")}
        self.assertIn("shoulder", flagged)

    def test_word_echo_excludes_character_names(self) -> None:
        # Repeating a character's name in close proximity is normal prose,
        # not a tic -- detect_names should keep it out of the echo scan.
        # detect_names deliberately excludes tokens that are sentence-initial
        # >=85% of the time (indistinguishable from a capitalized opener), so
        # the name must also appear mid-sentence to register as a name --
        # exactly how a real character's name reads across a chapter.
        body = " ".join(
            f"Mira found Devon by the window. Devon looked out at row {i}. "
            f"She watched Devon say nothing at all." for i in range(20)
        )
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        flagged = {f.measured.split('"')[1] for f in _findings(report, "word_echo")}
        self.assertNotIn("devon", flagged)

    def test_sentence_opener_repeat_flagged(self) -> None:
        para = (
            "She stood at the window. She watched the street below. "
            "She waited for the car to turn the corner. She did not move."
        )
        self._write("ch01.md", para)
        report = lint_manuscript(self.chapters)
        self.assertTrue(_findings(report, "sentence_opener_repeat"))

    def test_varied_sentence_openers_not_flagged(self) -> None:
        para = (
            "She stood at the window. Rain streaked the glass. "
            "Somewhere a dog barked twice. The street stayed empty."
        )
        self._write("ch01.md", para)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "sentence_opener_repeat"))

    def test_maxim_endings_flagged(self) -> None:
        for i in range(6):
            self._write(
                f"ch{i:02d}.md",
                "She carried the jar down the stair and set it by the door.\n\n"
                "That was the year I learned what memory costs a person.",
            )
        report = lint_manuscript(self.chapters)
        found = _findings(report, "maxim_endings")
        self.assertTrue(found, "expected maxim-ending failure")

    def test_concrete_ending_not_counted_as_maxim(self) -> None:
        # A closing image containing an abstract word is not a maxim.
        for i in range(6):
            self._write(
                f"ch{i:02d}.md",
                "She worked through the afternoon without speaking to anyone.\n\n"
                "She set the lamp on the step and left the gate open.",
            )
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "maxim_endings"))

    def test_uniform_chapter_length_warned(self) -> None:
        for i in range(6):
            self._write(f"ch{i:02d}.md", "word " * 500)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "length_uniformity")
        self.assertTrue(found)
        self.assertEqual("warn", found[0].severity)

    def test_varied_chapter_length_not_warned(self) -> None:
        for i, n in enumerate([300, 900, 1500, 600, 2100, 450]):
            self._write(f"ch{i:02d}.md", "word " * n)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "length_uniformity"))

    def test_empty_directory_fails(self) -> None:
        report = lint_manuscript(self.chapters)
        self.assertTrue(report.failed)

    def test_profile_relaxes_thresholds(self) -> None:
        self.assertGreater(
            Thresholds.for_profile("commercial").em_dash_per_1k,
            Thresholds.for_profile("literary").em_dash_per_1k,
        )

    def test_report_renders_without_error(self) -> None:
        self._write("ch01.md", "She set the bread down. " * 100)
        self.assertIn("Manuscript Lint", render_report(lint_manuscript(self.chapters)))

    def test_sentence_monotony_flagged(self) -> None:
        sentence = "She walked to the door and opened it slowly today."
        self._write("ch01.md", " ".join([sentence] * 12))
        report = lint_manuscript(self.chapters)
        found = _findings(report, "sentence_monotony")
        self.assertTrue(found, "expected sentence-length monotony warning")
        self.assertEqual("warn", found[0].severity)

    def test_varied_sentence_length_not_flagged(self) -> None:
        body = ("Go. " "She waited by the heavy oak door until the bell rang twice more. "
                 "Rain. " "He counted the coins on the table without looking up once.") * 6
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "sentence_monotony"))

    def test_phrase_escalation_flagged(self) -> None:
        for i in range(9):
            n = 1 if i < 3 else 8
            body = "She set the bread down and waited by the door. " * 20
            body += "It was exactly what she expected. " * n
            self._write(f"ch{i:02d}.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "phrase_escalation")
        self.assertTrue(found, "expected phrase escalation warning")
        self.assertIn("exactly", found[0].measured)

    def test_stable_phrase_rate_not_escalation_flagged(self) -> None:
        for i in range(9):
            body = "She set the bread down and waited by the door. " * 20
            body += "It was exactly what she expected. " * 2
            self._write(f"ch{i:02d}.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "phrase_escalation"))

    def test_voice_drift_flagged_across_manuscript_thirds(self) -> None:
        early_dialogue = (
            '"Do you think so? Really?" asked Mary. "No." said John. '
        )
        late_dialogue = '"Fine." said Mary. "Fine." said John. '
        # 9 chapters, thirds of 3: first-third chapters carry distinguishable
        # dialogue, last-third chapters carry converged dialogue.
        for i in range(9):
            dialogue = early_dialogue if i < 3 else late_dialogue
            body = "She set the bread down and waited by the door. " * 15 + dialogue * 3
            self._write(f"ch{i:02d}.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "voice_drift")
        self.assertTrue(found, "expected voice drift warning")
        self.assertIn("Mary / John", found[0].citations)

    def test_voice_drift_not_flagged_when_still_differentiated(self) -> None:
        for i in range(9):
            dialogue = '"Do you think so? Really?" asked Mary. "No." said John. '
            body = "She set the bread down and waited by the door. " * 15 + dialogue * 3
            self._write(f"ch{i:02d}.md", body)
        report = lint_manuscript(self.chapters)
        self.assertEqual([], _findings(report, "voice_drift"))

    def test_adverb_density_flagged(self) -> None:
        body = "She quickly quietly softly slowly carefully gently ran home. " * 30
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "adverb_density")
        self.assertTrue(found, "expected adverb density warning")

    def test_filter_word_density_flagged(self) -> None:
        body = (
            "She saw the door open. She heard the wind rise. She felt the cold. "
            "She noticed the lamp go out. She realized the house was empty. "
        ) * 15
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "filter_word_density")
        self.assertTrue(found, "expected filter word density warning")
        self.assertEqual("warn", found[0].severity)

    def test_filter_word_clean_prose_not_flagged(self) -> None:
        body = " ".join(
            f"She set the bread on the table and counted the jars in row {i}."
            for i in range(80)
        )
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertEqual([], _findings(report, "filter_word_density"))

    def test_filter_word_lowercase_common_word_not_false_positive(self) -> None:
        # A case-insensitive [A-Z] class would match "the felt", "and knew" --
        # any ordinary lowercase word before one of these common verbs. The
        # subject branch must require an actual capital letter.
        body = "the felt hat sat on the table and knew nothing of the plan. " * 20
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertEqual([], _findings(report, "filter_word_density"))

    def test_em_dash_density_local_flags_single_hot_chapter(self) -> None:
        # ch01: 1000 words, 20 em dashes -> 20/1k, well above both the
        # manuscript-wide (4.0/1k) and local (6.0/1k) thresholds on its own.
        hot = _words_with_dashes(1000, 20)
        # 10 clean chapters, 0 dashes, 1000 words each.
        clean = _words_with_dashes(1000, 0)
        self._write("ch01.md", hot)
        for i in range(2, 12):
            self._write(f"ch{i:02d}.md", clean)
        report = lint_manuscript(self.chapters)
        # Manuscript-wide average: 20 dashes / 11000 words = ~1.8/1k --
        # comfortably under the 4.0/1k manuscript-wide threshold, so the
        # whole-book average hides the one hot chapter.
        self.assertEqual([], _findings(report, "em_dash_density"))
        found = _findings(report, "em_dash_density_local")
        self.assertTrue(found, "expected a single-chapter em dash flag")
        self.assertIn("ch01.md", found[0].measured)

    def test_em_dash_density_local_not_flagged_when_evenly_distributed(self) -> None:
        # Every chapter at a uniform 5.0/1k: above the manuscript-wide
        # threshold (4.0/1k, so em_dash_density itself still fires) but
        # below the local multiplier's 6.0/1k ceiling, so no chapter is
        # flagged individually for running hotter than its siblings.
        even = _words_with_dashes(1000, 5)
        for i in range(1, 12):
            self._write(f"ch{i:02d}.md", even)
        report = lint_manuscript(self.chapters)
        self.assertEqual([], _findings(report, "em_dash_density_local"))

    def test_explanatory_extension_flagged(self) -> None:
        body = (
            "Her voice was flat, the kind of flat that meant she had already decided. "
        ) * 30
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "explanatory_extension")
        self.assertTrue(found, "expected explanatory extension failure")
        self.assertEqual("fail", found[0].severity)

    def test_explanatory_extension_clean_prose_not_flagged(self) -> None:
        body = " ".join(
            f"She set the bread on the table and counted the jars in row {i}."
            for i in range(80)
        )
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertEqual([], _findings(report, "explanatory_extension"))

    def test_ordinary_ly_words_not_flagged_as_adverbs(self) -> None:
        body = "The family lived a lonely, friendly, orderly life near the assembly. " * 30
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "adverb_density"))

    def test_dialogue_tag_variety_flagged(self) -> None:
        body = ('"Go now." exclaimed Mary. ' * 15) + ('"Wait." retorted John. ' * 15)
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "dialogue_tag_variety")
        self.assertTrue(found, "expected dialogue tag variety warning")

    def test_said_dominant_not_flagged(self) -> None:
        body = ('"Go now," said Mary. ' * 15) + ('"Wait," asked John. ' * 15)
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "dialogue_tag_variety"))

    def test_voice_collision_flagged(self) -> None:
        body = ('"I will go now." said Mary. ' * 8) + ('"I will go now." said John. ' * 8)
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        found = _findings(report, "voice_collision")
        self.assertTrue(found, "expected voice collision warning")
        self.assertIn("Mary", found[0].citations[0])

    def test_differentiated_voices_not_flagged(self) -> None:
        body = ('"Do you think so? Truly?" asked Mary. ' * 8) + \
               ('"No." said John. ' * 8)
        self._write("ch01.md", body)
        report = lint_manuscript(self.chapters)
        self.assertFalse(_findings(report, "voice_collision"))


class TimelineTests(unittest.TestCase):
    def test_consistent_timeline_passes(self) -> None:
        text = """
        event id=yonah_death day=-3652 label="Yonah dies"
        event id=story_open  day=0     label="Chapter 1"
        age person=john_mark at=yonah_death years=9  src="Ch1"
        age person=john_mark at=story_open  years=19 src="Ch1"
        span from=yonah_death to=story_open stated=10y src="Ch1"
        """
        issues = validate(parse_timeline(text))
        self.assertEqual([], [i for i in issues if i.severity == "fail"], issues)

    def test_age_contradiction_caught(self) -> None:
        # Editorial finding 2: nine-to-nineteen implies ten years, but the
        # manuscript also calls the gap nine years.
        text = """
        event id=yonah_death day=-3287 label="Yonah dies"
        event id=story_open  day=0
        age person=john_mark at=yonah_death years=9  src="Ch1"
        age person=john_mark at=story_open  years=19 src="Ch1"
        """
        issues = validate(parse_timeline(text))
        kinds = [i.kind for i in issues]
        self.assertIn("age_contradiction", kinds)

    def test_stated_span_contradiction_caught(self) -> None:
        # Editorial finding 3: "three nights before" for a supper held last night.
        text = """
        event id=supper       day=120
        event id=crucifixion  day=121
        span from=supper to=crucifixion stated=3d src="Ch5"
        """
        issues = validate(parse_timeline(text))
        self.assertIn("span_contradiction", [i.kind for i in issues])

    def test_passion_week_day_precision(self) -> None:
        # A one-day error must fail even though it is small in absolute terms.
        text = """
        event id=resurrection day=123
        event id=emmaus       day=124
        span from=resurrection to=emmaus stated=0d src="Luke 24 same day"
        """
        issues = validate(parse_timeline(text))
        self.assertIn("span_contradiction", [i.kind for i in issues])

    def test_duplicate_occurrence_caught(self) -> None:
        # Editorial finding 4: Barnabas sells the same field twice.
        text = """
        event id=before_passover day=110
        event id=post_pentecost  day=175
        once id=barnabas_sells_field at=before_passover src="Ch1"
        once id=barnabas_sells_field at=post_pentecost  src="Ch9"
        """
        issues = validate(parse_timeline(text))
        self.assertIn("duplicate_occurrence", [i.kind for i in issues])

    def test_reversed_span_caught(self) -> None:
        text = """
        event id=a day=100
        event id=b day=50
        span from=a to=b stated=-50d src="Ch3"
        """
        issues = validate(parse_timeline(text))
        self.assertIn("reversed_span", [i.kind for i in issues])

    def test_unknown_event_reference_caught(self) -> None:
        text = """
        event id=a day=0
        age person=rhoda at=nonexistent years=12 src="Ch2"
        """
        issues = validate(parse_timeline(text))
        self.assertIn("unknown_event", [i.kind for i in issues])

    def test_duration_units(self) -> None:
        text = """
        event id=a day=0
        event id=b day=14
        span from=a to=b stated=2w src="Ch4"
        """
        issues = validate(parse_timeline(text))
        self.assertEqual([], [i for i in issues if i.severity == "fail"])

    def test_parse_error_reported(self) -> None:
        issues = validate(parse_timeline("event id=a\n"))
        self.assertIn("parse", [i.kind for i in issues])

    def test_render_issues_runs(self) -> None:
        tl = parse_timeline("event id=a day=0\n")
        self.assertIn("Chronology Check", render_issues(tl, validate(tl)))


class DiscoverTests(unittest.TestCase):
    """Unsupervised checks - the ones that find tics nobody listed."""

    def test_finds_unlisted_repeated_phrase(self) -> None:
        tic = "What Silas has written down is the version people repeat."
        chapters = {
            f"ch{i:02d}.md": f"She counted the jars in the {i} room.\n\n{tic}\n\n"
                             f"The gate held that night in year {i}."
            for i in range(1, 8)
        }
        hits = repeated_ngrams(chapters, min_count=5, min_per_10k=1.0)
        self.assertTrue(hits, "expected at least one discovered repeat")
        self.assertIn("silas has written down", hits[0].phrase)

    def test_maximal_span_not_sliding_windows(self) -> None:
        tic = "the version people repeat again and again without question"
        chapters = {f"ch{i}.md": f"Filler {i} words here.\n\n{tic}." for i in range(8)}
        hits = repeated_ngrams(chapters, min_count=5, min_per_10k=1.0)
        # One finding for the repeated span, not one per window offset.
        overlapping = [h for h in hits if "version people repeat" in h.phrase]
        self.assertEqual(1, len(overlapping), [h.phrase for h in hits])

    def test_single_chapter_repetition_not_flagged(self) -> None:
        # Deliberate in-scene repetition is craft, not a tic.
        chapters = {"ch01.md": "He knocked on the heavy door. " * 10}
        self.assertEqual([], repeated_ngrams(chapters, min_count=5, min_chapters=2))

    def test_hyphenation_variant_detected(self) -> None:
        text = ("She left it in the store-room. " * 5) + ("The storeroom was cold. " * 5)
        groups = entity_variants(text)
        merged = {frozenset(g.variants) for g in groups}
        self.assertIn(frozenset({"store-room", "storeroom"}), merged)

    def test_name_variant_detected(self) -> None:
        text = ("Miryam did not answer. " * 5) + ("Mariam did not answer. " * 5)
        variants = {v for g in entity_variants(text) for v in g.variants}
        self.assertTrue({"Miryam", "Mariam"} <= variants or
                        {"miryam", "mariam"} <= variants, variants)

    def test_function_words_not_treated_as_entities(self) -> None:
        text = "The door opened. That was all. The room was cold. That is what happened. " * 6
        flagged = {v.lower() for g in entity_variants(text) for v in g.variants}
        self.assertNotIn("the", flagged)
        self.assertNotIn("that", flagged)

    def test_readability_and_dialogue_ratio(self) -> None:
        text = '"Come in," she said. "The bread is ready and the table is set."'
        self.assertGreater(dialogue_ratio(text), 0.5)
        self.assertLess(dialogue_ratio("She walked to the door and waited."), 0.01)

    def test_flesch_kincaid_orders_by_complexity(self) -> None:
        # Absolute FK values can go negative on very simple text; what the
        # gate relies on is that harder prose scores higher.
        simple = flesch_kincaid_grade("The cat sat on the mat. He ran home.")
        complex_ = flesch_kincaid_grade(
            "The administrative determination, having been promulgated without "
            "adequate consideration of the jurisdictional complexities involved, "
            "necessitated substantial reconsideration by the assembled elders.")
        self.assertGreater(complex_, simple)
        self.assertGreater(complex_, 12.0)

    def test_modern_register_detected(self) -> None:
        hits = modern_register_hits("The elders discussed liability and formalized oversight.")
        self.assertIn("liability", hits)
        self.assertIn("oversight", hits)

    def test_line_defects_detected(self) -> None:
        # "doubled word" and "repeated whitespace" moved to runner/proof.py
        # (objective typographic defects); this list now covers stylistic
        # mechanical patterns only. See tests/test_proof.py for the moved
        # checks.
        found = line_defects({"ch01.md": "He waited, — and then left. She screamed!!"})
        labels = {label for _, label, _ in found}
        self.assertIn("comma immediately before a dash", labels)
        self.assertIn("repeated terminal punctuation", labels)

    def test_presence_gap_detected(self) -> None:
        order = [f"ch{i:02d}.md" for i in range(1, 9)]
        chapters = {c: ("Elazar spoke." if c in {order[0], order[7]} else "Nothing.")
                    for c in order}
        gaps = absence_gaps(presence_matrix(chapters, ["Elazar"]), order, min_gap=3)
        self.assertIn("Elazar", gaps)

    def test_speaker_stats_differentiate(self) -> None:
        text = ('"Do you think so?" asked Mary. ' * 6) + \
               ('"Go now." said Peter. ' * 6)
        stats = {s.speaker: s for s in speaker_stats(dialogue_by_speaker(text)[0])}
        self.assertIn("Mary", stats)
        self.assertIn("Peter", stats)
        self.assertGreater(stats["Mary"].question_rate, stats["Peter"].question_rate)

    def test_adverb_density_excludes_non_adverbs(self) -> None:
        n, total = adverb_density("The family lived a lonely, friendly life.")
        self.assertEqual(0, n)
        self.assertGreater(total, 0)

    def test_adverb_density_counts_true_adverbs(self) -> None:
        n, _ = adverb_density("She quickly and quietly closed the heavy door.")
        self.assertEqual(2, n)

    def test_dialogue_tag_counts_post_tag(self) -> None:
        counts = dialogue_tag_counts('"Go now," said Mary. "Wait," exclaimed John.')
        self.assertEqual(1, counts["said"])
        self.assertEqual(1, counts["exclaimed"])

    def test_dialogue_tag_counts_pre_tag(self) -> None:
        counts = dialogue_tag_counts('Mary said, "Go now." John exclaimed, "Wait."')
        self.assertEqual(1, counts["said"])
        self.assertEqual(1, counts["exclaimed"])

    def test_voice_collisions_detects_matching_signature(self) -> None:
        text = ('"I will go now." said Mary. ' * 8) + ('"I will go now." said John. ' * 8)
        stats = speaker_stats(dialogue_by_speaker(text)[0])
        pairs = voice_collisions(stats)
        self.assertEqual([("Mary", "John")], pairs)

    def test_voice_collisions_none_for_differentiated_speakers(self) -> None:
        text = ('"Do you think so? Truly?" asked Mary. ' * 8) + ('"No." said John. ' * 8)
        stats = speaker_stats(dialogue_by_speaker(text)[0])
        self.assertEqual([], voice_collisions(stats))

    def test_speaker_drift_detects_convergence(self) -> None:
        early = ('"Do you think so? Really?" asked Mary. ' * 6) + ('"No." said John. ' * 6)
        late = ('"Fine." said Mary. ' * 6) + ('"Fine." said John. ' * 6)
        early_by, _ = dialogue_by_speaker(early)
        late_by, _ = dialogue_by_speaker(late)
        converging, insufficient = speaker_drift(early_by, late_by)
        self.assertEqual([("Mary", "John")], converging)
        self.assertEqual([], insufficient)

    def test_speaker_drift_none_when_still_differentiated(self) -> None:
        early = ('"Do you think so? Really?" asked Mary. ' * 6) + ('"No." said John. ' * 6)
        late = ('"Are you certain? Truly?" asked Mary. ' * 6) + ('"Never." said John. ' * 6)
        early_by, _ = dialogue_by_speaker(early)
        late_by, _ = dialogue_by_speaker(late)
        converging, _ = speaker_drift(early_by, late_by)
        self.assertEqual([], converging)

    def test_speaker_drift_reports_insufficient_data_not_no_drift(self) -> None:
        # Mary has plenty of lines in both thirds; a secondary with too few
        # lines in the LAST third must be reported separately, not silently
        # counted as "no drift".
        early = ('"Do you think so? Really?" asked Mary. ' * 6) + ('"No." said Devon. ' * 6)
        late = '"Fine." said Mary. ' * 6  # Devon has zero lines in the last third
        early_by, _ = dialogue_by_speaker(early)
        late_by, _ = dialogue_by_speaker(late)
        converging, insufficient = speaker_drift(early_by, late_by)
        self.assertEqual([], converging)
        self.assertIn("Devon", insufficient)
        self.assertNotIn("Mary", insufficient)

    def test_strip_comments_removes_inline(self) -> None:
        text = "Before.\n\n<!-- Word count: 900 -->\n\nAfter.\n"
        self.assertEqual("Before.\n\n\n\nAfter.\n", strip_comments(text))

    def test_strip_comments_removes_multiline(self) -> None:
        text = "Before.\n\n<!-- hp:start -->\nMiddle.\n<!-- hp:end -->\n\nAfter.\n"
        cleaned = strip_comments(text)
        self.assertNotIn("<!--", cleaned)
        self.assertNotIn("-->", cleaned)
        self.assertIn("Middle.", cleaned)  # only the markers are comments; the
        # content they wrap is real prose and must survive

    def test_strip_comments_preserve_layout_keeps_offsets(self) -> None:
        text = "Before.\n<!-- note -->\nAfter.\n"
        cleaned = strip_comments(text, preserve_layout=True, fill="x")
        self.assertEqual(len(text), len(cleaned))
        self.assertEqual(text.count("\n"), cleaned.count("\n"))
        self.assertNotIn("<!--", cleaned)

    def test_strip_comments_no_comment_is_a_noop(self) -> None:
        text = "Plain prose with an em dash — right here.\n"
        self.assertEqual(text, strip_comments(text))

    def test_window_echoes_finds_close_repeat(self) -> None:
        text = "The shoulder ached. Ten words later the shoulder still ached badly."
        hits = window_echoes(text, window_words=50)
        words = {w for w, _gap in hits}
        self.assertIn("shoulder", words)

    def test_window_echoes_ignores_far_repeats(self) -> None:
        filler = " ".join(f"word{i}" for i in range(60))
        text = f"shoulder {filler} shoulder"
        hits = window_echoes(text, window_words=50)
        self.assertEqual([], hits)

    def test_window_echoes_respects_exclude_set(self) -> None:
        text = "Devon spoke. Devon listened. Devon left the room."
        hits = window_echoes(text, window_words=50, exclude={"devon"})
        self.assertEqual([], hits)

    def test_window_echoes_ignores_short_and_function_words(self) -> None:
        text = "the the the that that that this this this here here here"
        self.assertEqual([], window_echoes(text, window_words=50))

    def test_sentence_opener_repeats_finds_run(self) -> None:
        para = "She stood. She watched. She waited. She left."
        hits = sentence_opener_repeats(para, min_consecutive=3)
        self.assertEqual([("she", 4)], hits)

    def test_sentence_opener_repeats_below_minimum_not_flagged(self) -> None:
        para = "She stood. She watched. Rain fell outside."
        self.assertEqual([], sentence_opener_repeats(para, min_consecutive=3))

    def test_sentence_opener_repeats_does_not_cross_paragraphs(self) -> None:
        text = "She stood. She watched.\n\nShe waited. She left."
        # Two runs of 2 in separate paragraphs, never merged into a run of 4.
        self.assertEqual([], sentence_opener_repeats(text, min_consecutive=3))


if __name__ == "__main__":
    unittest.main()
