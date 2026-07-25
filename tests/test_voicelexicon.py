"""Tests for runner/voicelexicon.py -- never_say checks against dialogue."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.voicelexicon import check_lexicon, load_lexicon, render_report  # noqa: E402


class LoadLexiconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-lexicon-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual({}, load_lexicon(self.tempdir / "nope.yaml"))

    def test_parses_never_say_list_and_scalars(self) -> None:
        path = self.tempdir / "voice-lexicon.yaml"
        path.write_text(
            "mira:\n"
            "  never_say:\n"
            "    - literally\n"
            "    - y'all\n"
            "  contractions: high\n",
            encoding="utf-8",
        )
        lexicon = load_lexicon(path)
        self.assertEqual(["literally", "y'all"], lexicon["mira"]["never_say"])
        self.assertEqual("high", lexicon["mira"]["contractions"])


class CheckLexiconTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-lexicon-check-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()
        self.lexicon_path = self.tempdir / "voice-lexicon.yaml"

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_chapter(self, body: str) -> None:
        (self.chapters / "chapter-01.md").write_text(body, encoding="utf-8")

    def test_missing_lexicon_is_skipped(self) -> None:
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertTrue(report.skipped)
        self.assertEqual([], report.violations)

    def test_violation_detected(self) -> None:
        self.lexicon_path.write_text(
            "mira:\n  never_say:\n    - literally\n", encoding="utf-8")
        self._write_chapter(
            '"That is literally the worst thing," said Mira. "No." said Devon.')
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertEqual(1, len(report.violations))
        self.assertEqual("Mira", report.violations[0].character)
        self.assertEqual("literally", report.violations[0].phrase)

    def test_clean_dialogue_no_violation(self) -> None:
        self.lexicon_path.write_text(
            "mira:\n  never_say:\n    - literally\n", encoding="utf-8")
        self._write_chapter(
            '"That is the worst thing," said Mira. "No." said Devon. ' * 6)
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertEqual([], report.violations)

    def test_word_boundary_not_substring(self) -> None:
        # "literal" must not match inside "literally" or vice versa.
        self.lexicon_path.write_text(
            "mira:\n  never_say:\n    - literal\n", encoding="utf-8")
        self._write_chapter(
            '"That is figuratively true," said Mira. "No." said Devon. ' * 6)
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertEqual([], report.violations)

    def test_character_not_in_dialogue_is_silently_skipped(self) -> None:
        self.lexicon_path.write_text(
            "nobody:\n  never_say:\n    - literally\n", encoding="utf-8")
        self._write_chapter('"Hello." said Mira. "Hi." said Devon. ' * 6)
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertEqual([], report.violations)

    def test_character_matching_is_case_insensitive(self) -> None:
        self.lexicon_path.write_text(
            "MIRA:\n  never_say:\n    - literally\n", encoding="utf-8")
        self._write_chapter(
            '"That is literally the worst thing," said Mira. "No." said Devon.')
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertEqual(1, len(report.violations))

    def test_empty_lexicon_file_is_skipped(self) -> None:
        self.lexicon_path.write_text("", encoding="utf-8")
        report = check_lexicon(self.lexicon_path, self.chapters)
        self.assertTrue(report.skipped)

    def test_missing_chapters_dir_reports_skip_not_crash(self) -> None:
        self.lexicon_path.write_text(
            "mira:\n  never_say:\n    - literally\n", encoding="utf-8")
        report = check_lexicon(self.lexicon_path, self.tempdir / "no-chapters")
        self.assertTrue(report.skipped)

    def test_render_pass_and_fail(self) -> None:
        self.lexicon_path.write_text(
            "mira:\n  never_say:\n    - literally\n", encoding="utf-8")
        self._write_chapter('"Hello." said Mira. "Hi." said Devon. ' * 6)
        clean_text = render_report(check_lexicon(self.lexicon_path, self.chapters))
        self.assertIn("PASS", clean_text)

        self._write_chapter(
            '"That is literally the worst," said Mira. "No." said Devon. ' * 6)
        dirty_text = render_report(check_lexicon(self.lexicon_path, self.chapters))
        self.assertIn("FAIL", dirty_text)
        self.assertIn("literally", dirty_text)


if __name__ == "__main__":
    unittest.main()
