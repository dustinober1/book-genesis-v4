"""Tests for runner/fingerprint.py -- Burrows' Delta stylometric comparison.

This module is explicitly the least trustworthy one in runner/ (see its
module docstring) -- these tests exist mainly to prove the two guards that
make it honest actually hold: no crash on degenerate input, and no winner
named below the reference-count floor.
"""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.fingerprint import (  # noqa: E402
    MIN_REFERENCES_FOR_RANKING,
    build_profile,
    compare,
    load_library,
    load_profile,
    render_report,
    save_profile,
)

PROSE_A = "She walked to the door and opened it slowly, feeling the cold air outside. "
PROSE_B = "He ran across the yard because the dog was barking loudly at something. "
PROSE_C = "They sat by the fire and talked about nothing in particular for hours. "
PROSE_D = "A storm was coming and everyone could feel it in the heavy summer air. "
PROSE_E = "The market was busy that morning with vendors calling out their prices. "
PROSE_F = "Nobody spoke for a long time after the news arrived at the small house. "


class BuildProfileTests(unittest.TestCase):
    def test_computes_relative_frequencies(self) -> None:
        profile = build_profile("test", PROSE_A * 10)
        self.assertGreater(profile.total_words, 0)
        self.assertIn("the", profile.frequencies)

    def test_empty_text_produces_empty_profile(self) -> None:
        profile = build_profile("empty", "")
        self.assertEqual(0, profile.total_words)
        self.assertEqual({}, profile.frequencies)


class SaveLoadLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-fingerprint-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_save_and_load_round_trip(self) -> None:
        profile = build_profile("My Book", PROSE_A * 20)
        path = save_profile(profile, library_dir=self.tempdir)
        self.assertTrue(path.is_file())
        loaded = load_profile(path)
        self.assertEqual(profile.name, loaded.name)
        self.assertEqual(profile.total_words, loaded.total_words)
        self.assertEqual(profile.frequencies, loaded.frequencies)

    def test_load_library_empty_dir(self) -> None:
        self.assertEqual([], load_library(self.tempdir / "nope"))

    def test_load_library_returns_all_saved_profiles(self) -> None:
        save_profile(build_profile("Book A", PROSE_A * 20), library_dir=self.tempdir)
        save_profile(build_profile("Book B", PROSE_B * 20), library_dir=self.tempdir)
        library = load_library(self.tempdir)
        self.assertEqual(2, len(library))

    def test_name_with_special_characters_is_slugified_to_a_safe_filename(self) -> None:
        path = save_profile(build_profile("My Book: A Novel!", PROSE_A * 20), library_dir=self.tempdir)
        self.assertTrue(path.is_file())
        self.assertNotIn(":", path.name)
        self.assertNotIn("!", path.name)
        self.assertNotIn(" ", path.name)


class CompareTests(unittest.TestCase):
    def test_no_references_is_skipped(self) -> None:
        target = build_profile("target", PROSE_A * 20)
        report = compare(target, [])
        self.assertTrue(report.skipped)
        self.assertIsNone(report.winner)

    def test_single_reference_does_not_crash_on_zero_variance(self) -> None:
        # Regression: pstdev([single_value]) == 0.0 for every feature, which
        # used to divide by zero computing z-scores. Must report deltas as
        # "n/a", never raise.
        target = build_profile("target", PROSE_A * 20)
        ref = build_profile("ref", PROSE_B * 20)
        report = compare(target, [ref])
        self.assertEqual(1, len(report.deltas))
        self.assertNotEqual(report.deltas[0].delta, report.deltas[0].delta)  # NaN

    def test_identical_references_do_not_crash(self) -> None:
        target = build_profile("target", PROSE_A * 20)
        ref1 = build_profile("ref1", PROSE_B * 20)
        ref2 = build_profile("ref2", PROSE_B * 20)  # byte-identical prose to ref1
        report = compare(target, [ref1, ref2])
        self.assertEqual(2, len(report.deltas))

    def test_no_winner_named_below_reference_floor(self) -> None:
        target = build_profile("target", PROSE_A * 20)
        references = [
            build_profile(f"ref{i}", text * 20)
            for i, text in enumerate([PROSE_A, PROSE_B, PROSE_C])
        ]
        self.assertLess(len(references), MIN_REFERENCES_FOR_RANKING)
        report = compare(target, references)
        self.assertIsNone(report.winner)

    def test_winner_named_at_or_above_reference_floor(self) -> None:
        target = build_profile("target", PROSE_A * 30)
        texts = [PROSE_A, PROSE_B, PROSE_C, PROSE_D, PROSE_E, PROSE_F]
        references = [build_profile(f"ref{i}", t * 30) for i, t in enumerate(texts)]
        self.assertGreaterEqual(len(references), MIN_REFERENCES_FOR_RANKING)
        report = compare(target, references)
        self.assertIsNotNone(report.winner)

    def test_near_identical_reference_ranks_closest(self) -> None:
        target = build_profile("target", PROSE_A * 30)
        texts = [PROSE_A, PROSE_B, PROSE_C, PROSE_D, PROSE_E, PROSE_F]
        references = [build_profile(f"ref{i}", t * 30) for i, t in enumerate(texts)]
        report = compare(target, references)
        self.assertEqual("ref0", report.winner)  # ref0 is PROSE_A, same as target

    def test_confound_note_always_present(self) -> None:
        target = build_profile("target", PROSE_A * 20)
        ref = build_profile("ref", PROSE_B * 20)
        report = compare(target, [ref])
        self.assertTrue(report.confound_note)

    def test_render_report_never_names_winner_below_floor(self) -> None:
        target = build_profile("target", PROSE_A * 20)
        ref = build_profile("ref", PROSE_B * 20)
        text = render_report(compare(target, [ref]))
        self.assertIn("no winner named", text)

    def test_render_report_includes_confound_language(self) -> None:
        target = build_profile("target", PROSE_A * 20)
        ref = build_profile("ref", PROSE_B * 20)
        text = render_report(compare(target, [ref]))
        self.assertIn("confounded", text)

    def test_render_skipped_report(self) -> None:
        text = render_report(compare(build_profile("t", PROSE_A * 5), []))
        self.assertIn("Skipped:", text)


if __name__ == "__main__":
    unittest.main()
