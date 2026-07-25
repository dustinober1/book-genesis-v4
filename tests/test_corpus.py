"""Tests for runner/corpus.py -- personal baseline calibration."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.corpus import (  # noqa: E402
    LOW_CORPUS_WORDS,
    MIN_CORPUS_WORDS,
    build_baseline_report,
    compute_stats,
    derive_overrides,
    render_baseline_report,
)
from runner.lint import Thresholds  # noqa: E402


def _words(n: int, template: str = "The morning was quiet and I walked outside, sentence {i}.") -> str:
    return " ".join(template.format(i=i) for i in range(n))


class ComputeStatsTests(unittest.TestCase):
    def test_measures_em_dash_density(self) -> None:
        text = ("She paused — waited — and left. " * 60)
        stats = compute_stats(text)
        self.assertGreater(stats.em_dash_per_1k, 0)

    def test_measures_dialogue_ratio(self) -> None:
        text = '"Get out," she said. ' * 30 + "The house was quiet after that. " * 30
        stats = compute_stats(text)
        self.assertGreater(stats.dialogue_ratio, 0)

    def test_zero_dialogue_gives_none_said_share(self) -> None:
        stats = compute_stats(_words(100))
        self.assertIsNone(stats.said_tag_share)

    def test_measures_filter_word_density(self) -> None:
        text = "She saw the door open. She heard the wind rise. She felt the cold. " * 20
        stats = compute_stats(text)
        self.assertGreater(stats.filter_word_per_1k, 0)

    def test_measures_not_x_but_y_density(self) -> None:
        # No comma between "not" and "but": NOT_X_BUT_Y excludes [.,;] inside
        # the span, same construction runner/lint.py's own tests use.
        text = "He was not angry but something colder and harder to name. " * 20
        stats = compute_stats(text)
        self.assertGreater(stats.not_x_but_y_per_10k, 0)

    def test_comments_excluded_from_word_count(self) -> None:
        plain = _words(50)
        with_comment = "<!-- Word count: 9000 | Target: 9000 -->\n\n" + plain
        self.assertEqual(compute_stats(plain).total_words, compute_stats(with_comment).total_words)


class DeriveOverridesTests(unittest.TestCase):
    def test_stricter_measured_rate_becomes_override(self) -> None:
        from runner.corpus import CorpusStats
        low = CorpusStats(
            total_words=5000, em_dash_per_1k=0.5, adverb_per_1k=2.0,
            filter_word_per_1k=0.5, not_x_but_y_per_10k=0.5,
            dialogue_ratio=0.2, fk_grade=6.0, said_tag_share=0.9)
        overrides, warnings = derive_overrides(low, profile="commercial")
        self.assertIn("em_dash_per_1k", overrides)
        self.assertIn("adverb_per_1k", overrides)
        self.assertIn("filter_word_per_1k", overrides)
        self.assertIn("not_x_but_y_per_10k", overrides)
        self.assertEqual([], warnings)
        base = Thresholds.for_profile("commercial")
        self.assertLess(overrides["em_dash_per_1k"], base.em_dash_per_1k)
        self.assertLess(overrides["filter_word_per_1k"], base.filter_word_per_1k)
        self.assertLess(overrides["not_x_but_y_per_10k"], base.not_x_but_y_per_10k)

    def test_looser_measured_rate_warns_and_is_not_applied(self) -> None:
        from runner.corpus import CorpusStats
        high = CorpusStats(
            total_words=5000, em_dash_per_1k=50.0, adverb_per_1k=50.0,
            filter_word_per_1k=50.0, not_x_but_y_per_10k=50.0,
            dialogue_ratio=0.2, fk_grade=6.0, said_tag_share=0.9)
        overrides, warnings = derive_overrides(high, profile="commercial")
        self.assertEqual({}, overrides)
        self.assertEqual(4, len(warnings))

    def test_allow_loosen_applies_looser_rate(self) -> None:
        from runner.corpus import CorpusStats
        high = CorpusStats(
            total_words=5000, em_dash_per_1k=50.0, adverb_per_1k=50.0,
            filter_word_per_1k=50.0, not_x_but_y_per_10k=50.0,
            dialogue_ratio=0.2, fk_grade=6.0, said_tag_share=0.9)
        overrides, warnings = derive_overrides(high, profile="commercial", allow_loosen=True)
        self.assertIn("em_dash_per_1k", overrides)
        self.assertEqual([], warnings)


class BaselineReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-corpus-"))
        self.corpus_dir = self.tempdir / "corpus"
        self.corpus_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write(self, name: str, body: str) -> None:
        (self.corpus_dir / name).write_text(body, encoding="utf-8")

    def test_missing_corpus_dir_is_skipped(self) -> None:
        report = build_baseline_report(self.tempdir / "nope")
        self.assertTrue(report.skipped)

    def test_below_minimum_words_is_skipped(self) -> None:
        self._write("a.md", _words(50))  # well under MIN_CORPUS_WORDS
        report = build_baseline_report(self.corpus_dir)
        self.assertTrue(report.skipped)
        self.assertIn(str(MIN_CORPUS_WORDS), report.skipped)

    def test_meets_minimum_but_below_low_threshold_warns(self) -> None:
        # Just over MIN_CORPUS_WORDS but under LOW_CORPUS_WORDS.
        self._write("a.md", _words(150))  # ~1500 words: above MIN, below LOW
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        self.assertFalse(report.skipped)
        self.assertTrue(any("only" in w for w in report.warnings))

    def test_dialogue_mismatch_warns(self) -> None:
        self._write("a.md", _words(600))  # ~6000 words, no dialogue at all
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        self.assertTrue(any("dialogue ratio" in w for w in report.warnings))

    def test_ingests_multiple_files(self) -> None:
        half = 300  # ~3000 words each, ~6000 total
        self._write("a.md", _words(half))
        self._write("b.txt", _words(half))
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        self.assertFalse(report.skipped)
        self.assertGreaterEqual(report.corpus.total_words, MIN_CORPUS_WORDS)

    def test_non_md_txt_files_ignored(self) -> None:
        self._write("a.md", _words(600))
        (self.corpus_dir / "notes.json").write_text('{"ignore": "me"}', encoding="utf-8")
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        self.assertFalse(report.skipped)

    def test_manuscript_comparison_populated_when_given(self) -> None:
        self._write("a.md", _words(600))
        chapters_dir = self.tempdir / "chapters"
        chapters_dir.mkdir()
        (chapters_dir / "chapter-01.md").write_text(
            '"Get out," she said. ' * 30, encoding="utf-8")
        report = build_baseline_report(self.corpus_dir, chapters_dir, profile="commercial")
        self.assertIsNotNone(report.manuscript)

    def test_manuscript_none_when_not_given(self) -> None:
        self._write("a.md", _words(600))
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        self.assertIsNone(report.manuscript)

    def test_render_skipped_report(self) -> None:
        report = build_baseline_report(self.tempdir / "nope")
        text = render_baseline_report(report)
        self.assertIn("Skipped:", text)

    def test_render_includes_manuscript_dash_when_absent(self) -> None:
        self._write("a.md", _words(600))
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        text = render_baseline_report(report)
        self.assertIn("—", text)  # manuscript column placeholder

    def test_render_never_claims_automatic_application(self) -> None:
        self._write("a.md", _words(600))
        report = build_baseline_report(self.corpus_dir, profile="commercial")
        text = render_baseline_report(report)
        if report.derived_overrides:
            self.assertIn("NOT applied automatically", text)


if __name__ == "__main__":
    unittest.main()
