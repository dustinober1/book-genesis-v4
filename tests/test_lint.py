"""Tests for the deterministic manuscript checks.

Cases are drawn from a real editorial report so the suite proves the tooling
catches what a human editor caught.
"""

from pathlib import Path
import shutil
import sys
import tempfile
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
    dialogue_by_speaker,
    dialogue_ratio,
    entity_variants,
    flesch_kincaid_grade,
    line_defects,
    modern_register_hits,
    presence_matrix,
    repeated_ngrams,
    speaker_stats,
)


def _findings(report, check):
    return [f for f in report.findings if f.check == check]


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


if __name__ == "__main__":
    unittest.main()
