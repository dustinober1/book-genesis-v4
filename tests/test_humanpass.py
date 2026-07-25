"""Tests for runner/humanpass.py -- the 2% human pass and protected spans."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.discover import protected_spans  # noqa: E402
from runner.humanpass import (  # noqa: E402
    HP_END,
    HP_START,
    apply_plan,
    build_plan,
    render_apply_result,
    render_plan,
    select_lines,
    status_manuscript,
)

CHAPTER_RAW = (
    "# Chapter 1: The Ledger\n\n"
    "<!-- Word count: 300 | Target: 300 | Anchor: the door -->\n\n"
    "She set the bread on the table and counted the jars twice before speaking.\n\n"
    "“Get out,” she said, and meant every word of it completely.\n\n"
    "She moved like a soldier through the narrow hall without looking back once.\n\n"
    "In the end it was only grief that stayed, and grief teaches nothing but silence.\n"
)


def _kinds(entries):
    return {e.kind: e.text for e in entries}


def _edit_rewrite(worksheet: str, original: str, new_text: str) -> str:
    needle = f"{original}\n```\nREWRITE:\n```\n{original}"
    replacement = f"{original}\n```\nREWRITE:\n```\n{new_text}"
    assert needle in worksheet, "fixture text not found verbatim in worksheet"
    return worksheet.replace(needle, replacement)


class SelectLinesTests(unittest.TestCase):
    def test_selects_opening_closing_simile_and_dialogue(self) -> None:
        kinds = _kinds(select_lines(CHAPTER_RAW))
        self.assertIn("opening", kinds)
        self.assertIn("closing", kinds)
        self.assertIn("simile", kinds)
        self.assertIn("dialogue_opener", kinds)
        self.assertTrue(kinds["opening"].startswith("She set the bread"))
        self.assertTrue(kinds["closing"].startswith("In the end"))

    def test_heading_never_selected(self) -> None:
        entries = select_lines(CHAPTER_RAW)
        for e in entries:
            self.assertNotIn("Chapter 1", e.text)

    def test_comment_header_never_selected(self) -> None:
        entries = select_lines(CHAPTER_RAW)
        for e in entries:
            self.assertNotIn("Word count", e.text)

    def test_offsets_match_raw_text(self) -> None:
        for e in select_lines(CHAPTER_RAW):
            self.assertEqual(e.text, CHAPTER_RAW[e.start:e.end])

    def test_duplicate_span_keeps_first_label_only(self) -> None:
        # A one-sentence chapter is simultaneously its own opening, closing,
        # and longest sentence -- must appear once, not three times.
        entries = select_lines("# Ch 1\n\nShe stood at the door and did not move.\n")
        self.assertEqual(1, len(entries))
        self.assertEqual("opening", entries[0].kind)

    def test_empty_chapter_selects_nothing(self) -> None:
        self.assertEqual([], select_lines("# Ch 1\n\n"))

    def test_max_lines_caps_selection(self) -> None:
        entries = select_lines(CHAPTER_RAW, max_lines=1)
        self.assertEqual(1, len(entries))


class PlanRenderParseApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-humanpass-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write(self, name: str, body: str) -> None:
        (self.chapters / name).write_text(body, encoding="utf-8")

    def test_build_plan_skips_non_chapter_files(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        (self.chapters / "chapter-01-report.md").write_text("not a chapter", encoding="utf-8")
        (self.chapters / "chapter-01-pre-disruption.md").write_text("not a chapter", encoding="utf-8")
        plan = build_plan(self.chapters)
        self.assertEqual(["chapter-01.md"], [cp.chapter for cp in plan.chapters])

    def test_render_plan_empty_manuscript(self) -> None:
        text = render_plan(build_plan(self.chapters))
        self.assertIn("No finalized chapters", text)

    def test_unedited_worksheet_applies_nothing(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        result = apply_plan(self.chapters, worksheet)
        self.assertEqual([], result.updated_chapters)
        self.assertGreater(result.skipped_entries, 0)
        self.assertEqual(0, result.applied_entries)
        # And the file on disk is byte-identical -- nothing touched it.
        self.assertEqual(CHAPTER_RAW, (self.chapters / "chapter-01.md").read_text(encoding="utf-8"))

    def test_single_edit_applies_and_wraps_in_markers(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        result = apply_plan(self.chapters, edited)
        self.assertEqual(["chapter-01.md"], result.updated_chapters)
        self.assertEqual(1, result.applied_entries)

        new_text = (self.chapters / "chapter-01.md").read_text(encoding="utf-8")
        self.assertIn(f"{HP_START}Bread. Jars. Twice.{HP_END}", new_text)
        self.assertNotIn("She set the bread on the table", new_text)

    def test_applied_chapter_is_archived_not_overwritten(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        result = apply_plan(self.chapters, edited)
        archive_path = self.chapters / result.archived["chapter-01.md"]
        self.assertTrue(archive_path.is_file())
        self.assertEqual(CHAPTER_RAW, archive_path.read_text(encoding="utf-8"))

    def test_multiple_edits_in_one_chapter_all_applied(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        edited = _edit_rewrite(
            edited,
            "In the end it was only grief that stayed, and grief teaches nothing but silence.",
            "She never spoke of it again.",
        )
        result = apply_plan(self.chapters, edited)
        self.assertEqual(2, result.applied_entries)
        new_text = (self.chapters / "chapter-01.md").read_text(encoding="utf-8")
        self.assertIn("Bread. Jars. Twice.", new_text)
        self.assertIn("She never spoke of it again.", new_text)
        # Two independent protected spans, not one merged span.
        self.assertEqual(2, len(protected_spans(new_text)))

    def test_stale_sha_rejects_without_writing(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        # Chapter changes after the plan was built.
        self._write("chapter-01.md", CHAPTER_RAW + "\n\nOne more sentence entirely.\n")
        before = (self.chapters / "chapter-01.md").read_text(encoding="utf-8")
        result = apply_plan(self.chapters, edited)
        after = (self.chapters / "chapter-01.md").read_text(encoding="utf-8")
        self.assertEqual([], result.updated_chapters)
        self.assertTrue(result.rejected_chapters)
        self.assertEqual(before, after)

    def test_unparsable_worksheet_reports_errors_not_exception(self) -> None:
        result = apply_plan(self.chapters, "not a worksheet at all, just prose\n")
        self.assertEqual([], result.updated_chapters)
        self.assertEqual([], result.rejected_chapters)

    def test_missing_chapter_file_rejected(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        (self.chapters / "chapter-01.md").unlink()
        result = apply_plan(self.chapters, worksheet)
        self.assertTrue(any("chapter-01.md" in r for r in result.rejected_chapters))

    def test_replanning_after_apply_does_not_reselect_protected_content(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        apply_plan(self.chapters, edited)

        second_plan = build_plan(self.chapters)
        second_texts = [e.text for cp in second_plan.chapters for e in cp.entries]
        self.assertFalse(any("Bread. Jars. Twice." in t for t in second_texts))
        self.assertFalse(any(HP_START in t or HP_END in t for t in second_texts))

    def test_replanning_after_apply_still_selects_untouched_lines(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        apply_plan(self.chapters, edited)
        second_plan = build_plan(self.chapters)
        second_kinds = _kinds(second_plan.chapters[0].entries)
        self.assertIn("closing", second_kinds)

    def test_render_apply_result_lists_updated_and_rejected(self) -> None:
        self._write("chapter-01.md", CHAPTER_RAW)
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        text = render_apply_result(apply_plan(self.chapters, edited))
        self.assertIn("chapter-01.md", text)
        self.assertIn("Chapters updated: 1", text)


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-humanpass-status-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_status_reports_zero_before_any_pass(self) -> None:
        (self.chapters / "chapter-01.md").write_text(CHAPTER_RAW, encoding="utf-8")
        self.assertEqual({"chapter-01.md": 0}, status_manuscript(self.chapters))

    def test_status_counts_protected_spans_after_apply(self) -> None:
        (self.chapters / "chapter-01.md").write_text(CHAPTER_RAW, encoding="utf-8")
        worksheet = render_plan(build_plan(self.chapters))
        edited = _edit_rewrite(
            worksheet,
            "She set the bread on the table and counted the jars twice before speaking.",
            "Bread. Jars. Twice.",
        )
        apply_plan(self.chapters, edited)
        self.assertEqual({"chapter-01.md": 1}, status_manuscript(self.chapters))


if __name__ == "__main__":
    unittest.main()
