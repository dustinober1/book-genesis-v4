"""Tests for runner/texture.py -- sourced world-texture coverage checks."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.texture import (  # noqa: E402
    check_coverage,
    parse_texture_bank,
    render_texture_report,
    texture_manuscript,
)


def _findings(report, check):
    return [f for f in report.findings if f.check == check]


class ParseTextureBankTests(unittest.TestCase):
    def test_parses_a_clean_entry(self) -> None:
        entries, errors = parse_texture_bank(
            'texture  id=burnside-thai  term="the Thai place on Burnside"  '
            'kind=place  src="https://example.com"\n'
        )
        self.assertEqual([], errors)
        self.assertEqual(1, len(entries))
        self.assertEqual("burnside-thai", entries[0].id)
        self.assertEqual("the Thai place on Burnside", entries[0].term)
        self.assertEqual("place", entries[0].kind)
        self.assertEqual("https://example.com", entries[0].src)

    def test_missing_src_is_not_a_parse_error(self) -> None:
        entries, errors = parse_texture_bank('texture  id=x  term="a phrase"\n')
        self.assertEqual([], errors)
        self.assertEqual("", entries[0].src)

    def test_comments_and_blank_lines_ignored(self) -> None:
        text = '# a comment\n\n\ntexture  id=x  term="phrase"\n'
        entries, errors = parse_texture_bank(text)
        self.assertEqual(1, len(entries))
        self.assertEqual([], errors)

    def test_unparsable_line_reported_not_raised(self) -> None:
        entries, errors = parse_texture_bank("this is not a record at all\n")
        self.assertEqual([], entries)
        self.assertEqual(1, len(errors))

    def test_unknown_record_type_reported(self) -> None:
        entries, errors = parse_texture_bank('event  id=x  term="phrase"\n')
        self.assertEqual([], entries)
        self.assertTrue(any("unknown record type" in e for e in errors))

    def test_missing_id_reported(self) -> None:
        entries, errors = parse_texture_bank('texture  term="phrase"\n')
        self.assertEqual([], entries)
        self.assertTrue(any("missing id=" in e for e in errors))

    def test_missing_term_reported(self) -> None:
        entries, errors = parse_texture_bank("texture  id=x\n")
        self.assertEqual([], entries)
        self.assertTrue(any("missing term=" in e for e in errors))

    def test_duplicate_id_reported(self) -> None:
        text = 'texture  id=x  term="a"\ntexture  id=x  term="b"\n'
        entries, errors = parse_texture_bank(text)
        self.assertEqual(1, len(entries))
        self.assertTrue(any("duplicate texture id" in e for e in errors))


class CheckCoverageTests(unittest.TestCase):
    def test_finds_term_in_chapter(self) -> None:
        entries, _ = parse_texture_bank('texture  id=x  term="Burnside"\n')
        results = check_coverage(entries, {"ch01.md": "She walked past Burnside twice."})
        self.assertEqual(["ch01.md"], results[0].chapters_used)
        self.assertEqual(1, results[0].count)

    def test_unused_term_has_zero_count(self) -> None:
        entries, _ = parse_texture_bank('texture  id=x  term="Burnside"\n')
        results = check_coverage(entries, {"ch01.md": "Nothing relevant here at all."})
        self.assertEqual([], results[0].chapters_used)
        self.assertEqual(0, results[0].count)

    def test_matching_is_case_insensitive(self) -> None:
        entries, _ = parse_texture_bank('texture  id=x  term="burnside"\n')
        results = check_coverage(entries, {"ch01.md": "She walked past Burnside."})
        self.assertEqual(1, results[0].count)


class TextureManuscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="bg-texture-"))
        self.chapters = self.tempdir / "chapters"
        self.chapters.mkdir()
        self.bank = self.tempdir / "texture-bank.md"

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_chapter(self, name: str, body: str) -> None:
        (self.chapters / name).write_text(body, encoding="utf-8")

    def test_missing_bank_file_is_skipped(self) -> None:
        report = texture_manuscript(self.tempdir / "nope.md", self.chapters)
        self.assertTrue(report.skipped)
        self.assertEqual([], report.findings)

    def test_parse_error_is_fail_severity(self) -> None:
        self.bank.write_text("garbage\n", encoding="utf-8")
        report = texture_manuscript(self.bank, self.chapters)
        found = _findings(report, "parse")
        self.assertTrue(found)
        self.assertEqual("fail", found[0].severity)
        self.assertTrue(report.failed)

    def test_missing_src_flagged(self) -> None:
        self.bank.write_text('texture  id=x  term="Burnside"\n', encoding="utf-8")
        self._write_chapter("ch01.md", "She walked past Burnside.")
        report = texture_manuscript(self.bank, self.chapters)
        found = _findings(report, "missing_src")
        self.assertTrue(found)
        self.assertEqual("warn", found[0].severity)

    def test_present_src_not_flagged(self) -> None:
        self.bank.write_text(
            'texture  id=x  term="Burnside"  src="https://example.com"\n', encoding="utf-8")
        self._write_chapter("ch01.md", "She walked past Burnside.")
        report = texture_manuscript(self.bank, self.chapters)
        self.assertEqual([], _findings(report, "missing_src"))

    def test_unused_entry_flagged(self) -> None:
        self.bank.write_text(
            'texture  id=x  term="Burnside"  src="https://example.com"\n', encoding="utf-8")
        self._write_chapter("ch01.md", "Nothing relevant appears in this chapter.")
        report = texture_manuscript(self.bank, self.chapters)
        found = _findings(report, "unused_texture")
        self.assertTrue(found)
        self.assertIn("x", found[0].citations[0])

    def test_used_entry_not_flagged_as_unused(self) -> None:
        self.bank.write_text(
            'texture  id=x  term="Burnside"  src="https://example.com"\n', encoding="utf-8")
        self._write_chapter("ch01.md", "She walked past Burnside.")
        report = texture_manuscript(self.bank, self.chapters)
        self.assertEqual([], _findings(report, "unused_texture"))

    def test_unknown_kind_flagged(self) -> None:
        self.bank.write_text(
            'texture  id=x  term="Burnside"  kind=vibe  src="https://example.com"\n',
            encoding="utf-8")
        self._write_chapter("ch01.md", "She walked past Burnside.")
        report = texture_manuscript(self.bank, self.chapters)
        self.assertTrue(_findings(report, "unknown_kind"))

    def test_known_kind_not_flagged(self) -> None:
        self.bank.write_text(
            'texture  id=x  term="Burnside"  kind=place  src="https://example.com"\n',
            encoding="utf-8")
        self._write_chapter("ch01.md", "She walked past Burnside.")
        report = texture_manuscript(self.bank, self.chapters)
        self.assertEqual([], _findings(report, "unknown_kind"))

    def test_clean_bank_renders_pass(self) -> None:
        self.bank.write_text(
            'texture  id=x  term="Burnside"  kind=place  src="https://example.com"\n',
            encoding="utf-8")
        self._write_chapter("ch01.md", "She walked past Burnside.")
        report = texture_manuscript(self.bank, self.chapters)
        text = render_texture_report(report)
        self.assertIn("PASS", text)
        self.assertFalse(report.failed)

    def test_missing_chapters_dir_still_reports_missing_src(self) -> None:
        # Coverage needs chapters; missing_src does not -- a research-phase
        # texture bank can exist before any chapter has been written.
        self.bank.write_text('texture  id=x  term="Burnside"\n', encoding="utf-8")
        report = texture_manuscript(self.bank, self.tempdir / "no-chapters-yet")
        self.assertTrue(_findings(report, "missing_src"))
        self.assertEqual([], _findings(report, "unused_texture"))


if __name__ == "__main__":
    unittest.main()
