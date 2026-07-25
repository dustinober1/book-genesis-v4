"""Tests for runner/ledger.py -- the retired-phrase prevention ledger."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.ledger import (  # noqa: E402
    build_ledger,
    chapter_opening_word,
    find_simile_vehicles,
    parse_meta_line,
    render_ledger,
)


class LedgerPrimitiveTests(unittest.TestCase):
    def test_parse_meta_line_extracts_pairs(self) -> None:
        text = (
            "# Writer Report: Chapter 7\n\n- Word count: 3100\n\n"
            'meta  chapter=7  structure=spiral  hook=image  '
            'anchor="the phone on the sill"\n'
        )
        meta = parse_meta_line(text)
        self.assertEqual({
            "chapter": "7", "structure": "spiral", "hook": "image",
            "anchor": "the phone on the sill",
        }, meta)

    def test_parse_meta_line_missing_returns_none(self) -> None:
        self.assertIsNone(parse_meta_line("# Writer Report\n\nNo meta line here.\n"))

    def test_find_simile_vehicles_matches_three_constructions(self) -> None:
        text = (
            "She moved like a soldier through the hall. "
            "It felt as if the walls were listening. "
            "He walked the way his father used to."
        )
        vehicles = find_simile_vehicles(text)
        self.assertEqual(3, len(vehicles))
        self.assertTrue(any(v.startswith("like a soldier") for v in vehicles))
        self.assertTrue(any(v.startswith("as if the walls") for v in vehicles))
        self.assertTrue(any(v.startswith("the way his father") for v in vehicles))

    def test_chapter_opening_word_skips_heading_and_comment(self) -> None:
        raw = (
            "# Chapter 1: The Ledger\n\n"
            "<!-- Word count: 900 | Target: 900 | Anchor: the door -->\n\n"
            "Mira set the lantern down.\n"
        )
        self.assertEqual("mira", chapter_opening_word(raw))


class LedgerManuscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-ledger-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_chapter(self, n: int, body: str, *, meta: str = "") -> None:
        (self.chapters / f"chapter-{n:02d}.md").write_text(
            f"# Chapter {n}: Test\n\n{body}\n", encoding="utf-8")
        if meta:
            (self.chapters / f"chapter-{n:02d}-report.md").write_text(
                f"# Writer Report: Chapter {n}\n\n{meta}\n", encoding="utf-8")

    def test_empty_directory_returns_empty_ledger(self) -> None:
        report = build_ledger(self.chapters)
        self.assertEqual([], report.chapters_scanned)

    def test_only_canonical_chapter_files_are_scanned(self) -> None:
        # chapter-N-report.md and chapter-N-pre-disruption.md live in the
        # same directory as chapter-N.md (see agents/book-writer.md and
        # agents/book-disruptor.md) and must never be read as manuscript
        # prose.
        self._write_chapter(1, "Mira stood at the door.")
        (self.chapters / "chapter-01-pre-disruption.md").write_text(
            "SHOULD NEVER APPEAR IN chapters_scanned", encoding="utf-8")
        report = build_ledger(self.chapters)
        self.assertEqual(["chapter-01.md"], report.chapters_scanned)

    def test_repeated_phrase_across_chapters_listed(self) -> None:
        self._write_chapter(1, "She stood like a soldier at the door and did not move at all.")
        self._write_chapter(2, "He too stood like a soldier at the door, waiting for something.")
        report = build_ledger(self.chapters)
        phrases = {p for p, _n in report.phrases}
        self.assertTrue(any("stood like a soldier" in p for p in phrases))

    def test_simile_vehicles_collected_across_chapters(self) -> None:
        self._write_chapter(1, "She moved like a soldier through the hall.")
        self._write_chapter(2, "He walked like a soldier out the door too.")
        report = build_ledger(self.chapters)
        self.assertTrue(report.similes)
        self.assertTrue(any("like a soldier" in v for v, _n in report.similes))

    def test_opening_words_grouped_by_word(self) -> None:
        self._write_chapter(1, "Mira set the lantern down carefully.")
        self._write_chapter(2, "Devon watched her from the doorway quietly.")
        report = build_ledger(self.chapters)
        words = dict(report.opening_words)
        self.assertEqual(["chapter-01.md"], words["mira"])
        self.assertEqual(["chapter-02.md"], words["devon"])

    def test_dialogue_tags_exclude_said_and_asked(self) -> None:
        body = '"Get out," she exclaimed. "Never," he retorted. "Why," she asked.'
        self._write_chapter(1, body)
        report = build_ledger(self.chapters)
        tags = {t for t, _n in report.dialogue_tags}
        self.assertNotIn("said", tags)
        self.assertNotIn("asked", tags)

    def test_structural_approach_and_hook_from_meta_line(self) -> None:
        self._write_chapter(
            1, "Mira stood at the door.",
            meta='meta  chapter=1  structure=chronological  hook=image  anchor="the door"',
        )
        self._write_chapter(
            2, "Devon watched her leave.",
            meta='meta  chapter=2  structure=spiral  hook=question  anchor="the letter"',
        )
        report = build_ledger(self.chapters)
        self.assertEqual(
            [("chapter-01.md", "chronological"), ("chapter-02.md", "spiral")],
            report.structural_approaches,
        )
        self.assertEqual(
            [("chapter-01.md", "image"), ("chapter-02.md", "question")],
            report.hooks,
        )
        self.assertEqual([], report.chapters_missing_meta)

    def test_chapter_without_report_tracked_as_missing_meta(self) -> None:
        self._write_chapter(1, "Mira stood at the door.")  # no meta= no report file
        report = build_ledger(self.chapters)
        self.assertEqual(["chapter-01.md"], report.chapters_missing_meta)
        self.assertEqual([], report.structural_approaches)

    def test_chapter_report_without_meta_line_tracked_as_missing(self) -> None:
        self._write_chapter(1, "Mira stood at the door.")
        (self.chapters / "chapter-01-report.md").write_text(
            "# Writer Report\n\nJust prose, no meta record.\n", encoding="utf-8")
        report = build_ledger(self.chapters)
        self.assertEqual(["chapter-01.md"], report.chapters_missing_meta)

    def test_render_ledger_lists_most_recent_structure_and_hook(self) -> None:
        self._write_chapter(
            1, "Mira stood at the door.",
            meta='meta  chapter=1  structure=chronological  hook=image',
        )
        self._write_chapter(
            2, "Devon watched her leave.",
            meta='meta  chapter=2  structure=spiral  hook=question',
        )
        text = render_ledger(build_ledger(self.chapters))
        self.assertIn("Most recent (chapter-02.md): **spiral**", text)
        self.assertIn("Most recent (chapter-02.md): **question**", text)

    def test_render_ledger_empty_manuscript(self) -> None:
        text = render_ledger(build_ledger(self.chapters))
        self.assertIn("No finalized chapters yet.", text)


if __name__ == "__main__":
    unittest.main()
