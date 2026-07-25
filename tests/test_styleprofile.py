"""Tests for runner/styleprofile.py -- per-project lint threshold overrides."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.lint import Thresholds  # noqa: E402
from runner.styleprofile import (  # noqa: E402
    coerce_overrides,
    load_raw_overrides,
    render_style_profile,
    resolve_thresholds,
)


class StyleProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-styleprofile-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_missing_file_returns_no_overrides(self) -> None:
        self.assertEqual({}, load_raw_overrides(self.tempdir / "nope.yaml"))

    def test_load_raw_overrides_reads_lint_block(self) -> None:
        path = self.tempdir / "style-profile.yaml"
        path.write_text('lint:\n  em_dash_per_1k: "3.2"\n', encoding="utf-8")
        self.assertEqual({"em_dash_per_1k": "3.2"}, load_raw_overrides(path))

    def test_coerce_overrides_converts_known_float_field(self) -> None:
        coerced, warnings = coerce_overrides({"em_dash_per_1k": "3.2"})
        self.assertEqual({"em_dash_per_1k": 3.2}, coerced)
        self.assertEqual([], warnings)

    def test_coerce_overrides_converts_known_int_field(self) -> None:
        coerced, warnings = coerce_overrides({"min_chapter_words": "150"})
        self.assertEqual({"min_chapter_words": 150}, coerced)
        self.assertEqual([], warnings)

    def test_coerce_overrides_flags_unknown_key(self) -> None:
        coerced, warnings = coerce_overrides({"not_a_real_threshold": "1.0"})
        self.assertEqual({}, coerced)
        self.assertEqual(1, len(warnings))
        self.assertIn("not_a_real_threshold", warnings[0])

    def test_coerce_overrides_flags_unparseable_value(self) -> None:
        coerced, warnings = coerce_overrides({"em_dash_per_1k": "not-a-number"})
        self.assertEqual({}, coerced)
        self.assertEqual(1, len(warnings))
        self.assertIn("em_dash_per_1k", warnings[0])

    def test_coerce_overrides_reports_each_bad_key_independently(self) -> None:
        # One typo must not swallow a good override elsewhere in the file.
        coerced, warnings = coerce_overrides({
            "em_dash_per_1k": "3.2",
            "bogus_field": "1.0",
        })
        self.assertEqual({"em_dash_per_1k": 3.2}, coerced)
        self.assertEqual(1, len(warnings))

    def test_resolve_thresholds_no_file_returns_genre_default(self) -> None:
        thresholds, warnings = resolve_thresholds(
            profile="literary", style_profile_path=self.tempdir / "absent.yaml")
        self.assertEqual(Thresholds.for_profile("literary"), thresholds)
        self.assertEqual([], warnings)

    def test_resolve_thresholds_applies_override_on_top_of_profile(self) -> None:
        path = self.tempdir / "style-profile.yaml"
        path.write_text('lint:\n  em_dash_per_1k: "1.5"\n', encoding="utf-8")
        thresholds, warnings = resolve_thresholds(
            profile="commercial", style_profile_path=path)
        base = Thresholds.for_profile("commercial")
        self.assertEqual(1.5, thresholds.em_dash_per_1k)
        # Every other field stays at the genre default -- an override is
        # additive, not a full threshold replacement.
        self.assertEqual(base.phrase_per_10k, thresholds.phrase_per_10k)
        self.assertEqual([], warnings)

    def test_resolve_thresholds_surfaces_warnings_without_raising(self) -> None:
        path = self.tempdir / "style-profile.yaml"
        path.write_text('lint:\n  typo_field: "1.0"\n', encoding="utf-8")
        thresholds, warnings = resolve_thresholds(
            profile="", style_profile_path=path)
        self.assertEqual(Thresholds(), thresholds)  # bad override dropped, not applied
        self.assertEqual(1, len(warnings))

    def test_with_overrides_preserves_frozen_semantics(self) -> None:
        base = Thresholds.for_profile("literary")
        overridden = base.with_overrides({"em_dash_per_1k": 9.9})
        self.assertEqual(3.0, base.em_dash_per_1k)  # base is untouched
        self.assertEqual(9.9, overridden.em_dash_per_1k)
        self.assertEqual(base.phrase_per_10k, overridden.phrase_per_10k)

    def test_with_overrides_unknown_field_raises(self) -> None:
        with self.assertRaises(TypeError):
            Thresholds().with_overrides({"not_a_field": 1.0})

    def test_render_style_profile_round_trips_through_load(self) -> None:
        rendered = render_style_profile({"em_dash_per_1k": 2.5, "min_chapter_words": 300})
        path = self.tempdir / "style-profile.yaml"
        path.write_text(rendered, encoding="utf-8")
        raw = load_raw_overrides(path)
        self.assertEqual({"em_dash_per_1k": "2.5", "min_chapter_words": "300"}, raw)


if __name__ == "__main__":
    unittest.main()
