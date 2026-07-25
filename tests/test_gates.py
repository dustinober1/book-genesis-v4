"""Tests for runner/gates.py's deterministic phase checks.

Focused on the language guard added to check_lint_check: mirrors the
existing guard on check_macro so a non-English manuscript gets an honest
"skip" from the lint gate instead of a "pass" a lexicon-based check could
never have earned.
"""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.gates import (  # noqa: E402
    check_dynamic_range,
    check_human_pass,
    check_lint_check,
    check_structure_variety,
)


class CheckLintCheckLanguageGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-gates-"))
        self.chapters = self.tempdir / "manuscript" / "chapters"
        self.chapters.mkdir(parents=True)
        (self.chapters / "ch01.md").write_text(
            "She set the bread on the table and counted the jars again. " * 40,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_state(self, language: str) -> None:
        (self.tempdir / "PROJECT_STATE.yaml").write_text(
            f"project:\n  language: {language}\n", encoding="utf-8",
        )

    def test_non_english_language_skips_with_reason(self) -> None:
        self._write_state("pt-BR")
        result = check_lint_check(self.tempdir, [])
        self.assertEqual("skip", result.status)
        self.assertIn("pt-br", result.summary.lower())

    def test_english_language_runs_normally(self) -> None:
        self._write_state("en-US")
        result = check_lint_check(self.tempdir, [])
        self.assertIn(result.status, ("pass", "fail"))

    def test_blank_language_runs_normally(self) -> None:
        self._write_state("")
        result = check_lint_check(self.tempdir, [])
        self.assertIn(result.status, ("pass", "fail"))

    # No "missing PROJECT_STATE.yaml" case: state_get(target, "project.language")
    # raises FileNotFoundError with no state file, same as check_macro's
    # identical call at gates.py -- every gate check assumes a project that
    # has already been through `runner/cli.py init`, which always creates
    # PROJECT_STATE.yaml. Not a gap introduced here.


class CheckStructureVarietyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-gates-structure-"))
        self.chapters = self.tempdir / "manuscript" / "chapters"
        self.chapters.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_chapter(self, n: int, structure: str) -> None:
        (self.chapters / f"chapter-{n}.md").write_text(
            f"# Chapter {n}\n\nSome prose for chapter {n}.\n", encoding="utf-8")
        (self.chapters / f"chapter-{n}-report.md").write_text(
            f'meta chapter={n} structure={structure} hook=image anchor="the door"\n',
            encoding="utf-8",
        )

    def test_no_chapters_skips(self) -> None:
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("skip", result.status)

    def test_single_chapter_skips_not_enough_data(self) -> None:
        self._write_chapter(1, "linear")
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("skip", result.status)

    def test_consecutive_repeat_fails(self) -> None:
        self._write_chapter(1, "linear")
        self._write_chapter(2, "linear")
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("fail", result.status)
        self.assertIn("chapter-1.md", result.detail)
        self.assertIn("chapter-2.md", result.detail)

    def test_alternating_two_structures_passes_below_six_chapters(self) -> None:
        # Share-ceiling check only activates at 6+ tracked chapters.
        self._write_chapter(1, "linear")
        self._write_chapter(2, "spiral")
        self._write_chapter(3, "linear")
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("pass", result.status)

    def test_diverse_structures_across_six_chapters_passes(self) -> None:
        for i, s in enumerate(
            ["linear", "spiral", "fragmented", "flashback", "linear", "spiral"], start=1,
        ):
            self._write_chapter(i, s)
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("pass", result.status)

    def test_single_structure_over_share_ceiling_fails(self) -> None:
        # "linear" is 3/6 = 50%, over the 40% ceiling, with no two adjacent
        # chapters sharing a structure -- isolates the share-ceiling rule
        # from the consecutive-repeat rule.
        structures = ["linear", "spiral", "linear", "fragmented", "linear", "flashback"]
        for i, s in enumerate(structures, start=1):
            self._write_chapter(i, s)
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("fail", result.status)
        self.assertIn("40%", result.detail)

    def test_chapters_without_meta_records_skip(self) -> None:
        (self.chapters / "chapter-1.md").write_text("# Chapter 1\n\nProse.\n", encoding="utf-8")
        (self.chapters / "chapter-2.md").write_text("# Chapter 2\n\nProse.\n", encoding="utf-8")
        result = check_structure_variety(self.tempdir, [])
        self.assertEqual("skip", result.status)


class CheckHumanPassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-gates-humanpass-"))
        self.chapters = self.tempdir / "manuscript" / "chapters"
        self.chapters.mkdir(parents=True)
        (self.tempdir / "work").mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_state(self, skip_human_pass: str = "") -> None:
        (self.tempdir / "PROJECT_STATE.yaml").write_text(
            f"project:\n  skip_human_pass: {skip_human_pass}\n", encoding="utf-8",
        )

    def _write_chapter(self, n: int, body: str) -> None:
        (self.chapters / f"chapter-{n}.md").write_text(
            f"# Chapter {n}\n\n{body}\n", encoding="utf-8")

    def test_no_chapters_skips(self) -> None:
        self._write_state()
        result = check_human_pass(self.tempdir, [])
        self.assertEqual("skip", result.status)

    def test_skip_flag_passes_without_worksheet(self) -> None:
        self._write_chapter(1, "Some prose.")
        self._write_state(skip_human_pass="true")
        result = check_human_pass(self.tempdir, [])
        self.assertEqual("pass", result.status)

    def test_no_worksheet_fails(self) -> None:
        self._write_chapter(1, "Some prose.")
        self._write_state()
        result = check_human_pass(self.tempdir, [])
        self.assertEqual("fail", result.status)
        self.assertIn("no work/human-pass.md", result.summary)

    def test_worksheet_exists_but_no_applied_spans_fails(self) -> None:
        # This is the exact gap the fix closes: a worksheet the orchestrator
        # generated itself, with no human-applied protected span, used to
        # pass on existence alone.
        self._write_chapter(1, "Some prose with no protected span at all.")
        (self.tempdir / "work" / "human-pass.md").write_text("worksheet", encoding="utf-8")
        self._write_state()
        result = check_human_pass(self.tempdir, [])
        self.assertEqual("fail", result.status)
        self.assertIn("0 protected span", result.summary)

    def test_applied_span_meets_default_threshold(self) -> None:
        self._write_chapter(1, "Some prose with <!-- hp:start -->a rewritten line<!-- hp:end -->.")
        (self.tempdir / "work" / "human-pass.md").write_text("worksheet", encoding="utf-8")
        self._write_state()
        result = check_human_pass(self.tempdir, [])
        self.assertEqual("pass", result.status)
        self.assertIn("1 protected span", result.summary)

    def test_explicit_min_spans_arg_enforced(self) -> None:
        self._write_chapter(1, "Some prose with <!-- hp:start -->one rewrite<!-- hp:end -->.")
        (self.tempdir / "work" / "human-pass.md").write_text("worksheet", encoding="utf-8")
        self._write_state()
        result = check_human_pass(self.tempdir, ["2"])
        self.assertEqual("fail", result.status)
        self.assertIn("need >= 2", result.summary)


class CheckDynamicRangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-gates-dynrange-"))
        self.evals = self.tempdir / "evaluations"
        self.evals.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_eval(self, n: int, floor: float) -> None:
        (self.evals / f"eval-chapter-{n}.md").write_text(
            "## HEADLINE\n"
            f"**CVI-Launch:** 8.0 | **CVI-Legacy:** 7.5 | "
            f"**Genesis Floor:** {floor} | **Genesis Average:** {floor + 0.3}\n",
            encoding="utf-8",
        )

    def test_no_evaluations_dir_skips(self) -> None:
        shutil.rmtree(self.evals)
        result = check_dynamic_range(self.tempdir, [])
        self.assertEqual("skip", result.status)

    def test_below_minimum_chapter_count_skips(self) -> None:
        for i, s in enumerate([8.5, 9.0, 8.7], start=1):
            self._write_eval(i, s)
        result = check_dynamic_range(self.tempdir, [])
        self.assertEqual("skip", result.status)

    def test_uniform_scores_fail_low_variation(self) -> None:
        for i in range(1, 7):
            self._write_eval(i, 8.5)
        result = check_dynamic_range(self.tempdir, [])
        self.assertEqual("fail", result.status)
        self.assertIn("0.000", result.summary)

    def test_varied_scores_pass(self) -> None:
        for i, s in enumerate([8.5, 9.2, 8.6, 9.4, 8.5, 9.0], start=1):
            self._write_eval(i, s)
        result = check_dynamic_range(self.tempdir, [])
        self.assertEqual("pass", result.status)

    def test_explicit_threshold_arg_respected(self) -> None:
        # Scores [8.5, 8.6] alternating -> CV ~0.00585. A min_cv arg BELOW
        # that (easier to clear) passes; a min_cv ABOVE it (harder to
        # clear) fails -- args[0] is the floor the measured CV must clear.
        for i, s in enumerate([8.5, 8.6, 8.5, 8.6, 8.5, 8.6], start=1):
            self._write_eval(i, s)
        loose_threshold_passes = check_dynamic_range(self.tempdir, ["0.001"])
        self.assertEqual("pass", loose_threshold_passes.status)
        strict_threshold_fails = check_dynamic_range(self.tempdir, ["0.01"])
        self.assertEqual("fail", strict_threshold_fails.status)

    def test_missing_headline_line_is_silently_excluded(self) -> None:
        for i, s in enumerate([8.5, 9.2, 8.6, 9.4, 8.5], start=1):
            self._write_eval(i, s)
        (self.evals / "eval-chapter-6.md").write_text("no headline here", encoding="utf-8")
        # Only 5 chapters actually parsed -- below the minimum, so skip.
        result = check_dynamic_range(self.tempdir, [])
        self.assertEqual("skip", result.status)

    def test_is_registered_as_advisory(self) -> None:
        from runner.gates import ADVISORY_CHECKS
        self.assertIn("dynamic_range", ADVISORY_CHECKS)


if __name__ == "__main__":
    unittest.main()
