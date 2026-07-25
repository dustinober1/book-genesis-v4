"""Tests for runner/macro.py -- book-level template detection."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.macro import (  # noqa: E402
    MIN_CHAPTERS_FOR_MACRO,
    analyze_chapter_shape,
    macro_manuscript,
    render_macro_report,
)


def _findings(report, check):
    return [f for f in report.findings if f.check == check]


class MacroChapterShapeTests(unittest.TestCase):
    def test_dialogue_opening_detected(self) -> None:
        shape = analyze_chapter_shape("ch01.md", '# Ch 1\n\n"Get out," she said, and meant it.\n')
        self.assertEqual("dialogue", shape.open_mode)

    def test_question_opening_detected(self) -> None:
        shape = analyze_chapter_shape(
            "ch01.md", "# Ch 1\n\nWhy had nobody warned her about the stairs?\n")
        self.assertEqual("question", shape.open_mode)

    def test_fragment_opening_detected(self) -> None:
        shape = analyze_chapter_shape("ch01.md", "# Ch 1\n\nNo answer. Silence pressed in close.\n")
        self.assertEqual("fragment", shape.open_mode)

    def test_image_action_opening_detected(self) -> None:
        shape = analyze_chapter_shape(
            "ch01.md",
            "# Ch 1\n\nShe set the bread on the table and counted the jars twice.\n",
        )
        self.assertEqual("image-action", shape.open_mode)

    def test_maxim_closing_detected(self) -> None:
        shape = analyze_chapter_shape(
            "ch01.md",
            "# Ch 1\n\nShe set the bread down.\n\n"
            "In the end it was only grief that stayed, and grief teaches nothing but silence.\n",
        )
        self.assertEqual("maxim", shape.close_mode)

    def test_dialogue_closing_not_swallowed_by_preceding_sentence(self) -> None:
        # Regression: the sentence-split regex's separator character class
        # must not include an OPENING curly quote, or a dialogue sentence
        # that follows narration loses its leading quote mark and is
        # misclassified as "other" instead of "dialogue". This only shows
        # up when dialogue is NOT the chapter's very first sentence, which
        # is why test_dialogue_opening_detected (above) didn't catch it.
        shape = analyze_chapter_shape(
            "ch01.md",
            "# Ch 1\n\nShe walked in and shut the door behind her quietly.\n\n"
            "“Get out,” she said finally.\n",
        )
        self.assertEqual("dialogue", shape.close_mode)

    def test_concrete_ending_not_misread_as_maxim(self) -> None:
        shape = analyze_chapter_shape(
            "ch01.md",
            "# Ch 1\n\nShe stood.\n\nShe set the jar on the table and closed the door behind her.\n",
        )
        self.assertNotEqual("maxim", shape.close_mode)

    def test_scene_breaks_counted(self) -> None:
        shape = analyze_chapter_shape(
            "ch01.md",
            "# Ch 1\n\nA scene.\n\n---\n\nAnother scene.\n\n---\n\nA third.\n",
        )
        self.assertEqual(2, shape.scene_breaks)

    def test_comment_header_not_read_as_opening_sentence(self) -> None:
        # agents/book-writer.md mandates a <!-- Word count: ... --> header
        # on every real chapter -- it must never be classified as the
        # chapter's opening sentence.
        shape = analyze_chapter_shape(
            "ch01.md",
            "# Ch 1\n\n<!-- Word count: 900 | Target: 900 | Anchor: the door -->\n\n"
            '"Get out," she said.\n',
        )
        self.assertEqual("dialogue", shape.open_mode)

    def test_chapter_prefix_stripped_from_title(self) -> None:
        shape = analyze_chapter_shape("ch01.md", "# Chapter 1: The Ledger\n\nText here now.\n")
        self.assertEqual("Chapter 1: The Ledger", shape.title)


class MacroManuscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-macro-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write(self, name: str, body: str) -> None:
        (self.chapters / name).write_text(body, encoding="utf-8")

    def test_missing_directory_is_skipped(self) -> None:
        report = macro_manuscript(self.tempdir / "nope")
        self.assertTrue(report.skipped)
        self.assertEqual([], report.findings)

    def test_below_chapter_floor_is_skipped_not_flagged(self) -> None:
        # The demo fixture (4 chapters) must never be mistaken for a
        # template just because it's small -- see runner/filesystem.py's
        # _DEMO_CHAPTERS docstring on why the fixture must genuinely pass.
        for i in range(1, MIN_CHAPTERS_FOR_MACRO - 1):
            self._write(f"chapter-{i:02d}.md", f"# Chapter {i}: X\n\nShe stood at the door.\n")
        report = macro_manuscript(self.chapters)
        self.assertTrue(report.skipped)
        self.assertEqual([], report.findings)
        self.assertEqual([], report.chapters)

    def test_uniform_opening_mode_flagged_at_floor(self) -> None:
        for i in range(1, MIN_CHAPTERS_FOR_MACRO + 1):
            self._write(
                f"chapter-{i:02d}.md",
                f"# Chapter {i}: X\n\nShe set the bread on the table, chapter {i}.\n\n"
                "Rain kept falling on the roof outside.\n",
            )
        report = macro_manuscript(self.chapters)
        self.assertFalse(report.skipped)
        self.assertTrue(_findings(report, "opening_mode_share"))

    def test_varied_opening_modes_not_flagged(self) -> None:
        openings = [
            '"Get out," she said.',
            "Why had nobody warned her?",
            "No answer.",
            "She set the jar on the table and closed the door.",
            "Rain streaked the window glass in long grey lines today.",
            "The old truck rattled once and finally caught.",
        ]
        for i, opening in enumerate(openings, start=1):
            self._write(
                f"chapter-{i:02d}.md",
                f"# Chapter {i}: X\n\n{opening} A second sentence follows after that.\n",
            )
        report = macro_manuscript(self.chapters)
        self.assertFalse(_findings(report, "opening_mode_share"))

    def test_title_parallelism_flagged(self) -> None:
        for i in range(1, MIN_CHAPTERS_FOR_MACRO + 1):
            self._write(
                f"chapter-{i:02d}.md",
                f"# Chapter {i}: The Room {i}\n\nShe set the jar down and left quietly.\n",
            )
        report = macro_manuscript(self.chapters)
        self.assertTrue(_findings(report, "title_parallelism"))

    def test_varied_titles_not_flagged(self) -> None:
        titles = ["The Room", "Silence", "Devon Waits", "Late Arrival", "No Answer", "The End"]
        for i, title in enumerate(titles, start=1):
            self._write(
                f"chapter-{i:02d}.md",
                f"# Chapter {i}: {title}\n\nShe set the jar down and left quietly.\n",
            )
        report = macro_manuscript(self.chapters)
        self.assertFalse(_findings(report, "title_parallelism"))

    def test_scene_break_uniformity_flagged(self) -> None:
        for i in range(1, MIN_CHAPTERS_FOR_MACRO + 1):
            self._write(
                f"chapter-{i:02d}.md",
                f"# Chapter {i}: X\n\nOne scene, chapter {i}.\n\n---\n\nAnother scene follows.\n",
            )
        report = macro_manuscript(self.chapters)
        self.assertTrue(_findings(report, "scene_break_uniformity"))

    def test_no_findings_report_renders_clean(self) -> None:
        titles = ["The Room", "Silence", "Devon Waits", "Late Arrival", "No Answer", "The End"]
        openings = [
            '"Get out," she said.',
            "Why had nobody warned her?",
            "No answer.",
            "She set the jar on the table and closed the door.",
            "Rain streaked the window glass in long grey lines today.",
            "The old truck rattled once and finally caught.",
        ]
        for i, (title, opening) in enumerate(zip(titles, openings), start=1):
            self._write(
                f"chapter-{i:02d}.md",
                f"# Chapter {i}: {title}\n\n{opening} A second sentence follows after that.\n",
            )
        report = macro_manuscript(self.chapters)
        text = render_macro_report(report)
        self.assertIn("PASS", text)


if __name__ == "__main__":
    unittest.main()
