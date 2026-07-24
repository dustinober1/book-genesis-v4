from pathlib import Path
import shutil
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.proof import (  # type: ignore  # noqa: E402
    ProofStyle,
    detect_style,
    proof_manuscript,
    render_proof_report,
)


class ProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-proof-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write(self, name: str, text: str) -> None:
        (self.tempdir / name).write_text(text, encoding="utf-8")

    def test_clean_manuscript_passes(self) -> None:
        self._write("chapter-01.md", (
            "# Chapter 1\n\n"
            "“You are certain,” she said, “that this is the door.”\n\n"
            "He nodded once and stepped through.\n"
        ))
        report = proof_manuscript(self.tempdir)
        self.assertFalse(report.failed)

    def test_doubled_word_detected(self) -> None:
        self._write("chapter-01.md", "# Chapter 1\n\nShe she went home and closed the door.\n")
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)
        self.assertTrue(any(i.check == "doubled_words" for i in report.issues))

    def test_doubled_space_warns_not_fails(self) -> None:
        self._write("chapter-01.md", "# Chapter 1\n\nShe walked  slowly to the door.\n")
        report = proof_manuscript(self.tempdir)
        doubled = [i for i in report.issues if i.check == "doubled_spaces"]
        self.assertTrue(doubled)
        self.assertEqual("warn", doubled[0].severity)

    def test_unbalanced_quotes_in_single_paragraph_fails(self) -> None:
        self._write("chapter-01.md", '# Chapter 1\n\n"This never closes, she said.\n')
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)
        self.assertTrue(any(i.check == "unbalanced_quotes" for i in report.issues))

    def test_multi_paragraph_quotation_convention_not_flagged(self) -> None:
        # A speech spanning multiple paragraphs opens each paragraph with a
        # quote mark and only closes it on the last one. That is correct
        # convention, not a defect.
        self._write("chapter-01.md", (
            "# Chapter 1\n\n"
            '"This is the first part of a long speech, unbroken by a close.\n\n'
            '"And this is the second part, which finally closes here."\n'
        ))
        report = proof_manuscript(self.tempdir)
        unbalanced = [i for i in report.issues if i.check == "unbalanced_quotes"]
        self.assertEqual([], unbalanced)

    def test_apostrophe_in_contraction_not_flagged(self) -> None:
        self._write("chapter-01.md", (
            "# Chapter 1\n\n"
            "“I don't think that's true,” she said, closing the door behind her.\n"
        ))
        report = proof_manuscript(self.tempdir)
        mixing = [i for i in report.issues if i.check == "quote_style_mixing"]
        self.assertEqual([], mixing)

    def test_unbalanced_parens_detected(self) -> None:
        self._write("chapter-01.md", "# Chapter 1\n\nShe opened the door (it creaked and went inside.\n")
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)
        self.assertTrue(any(i.check == "unbalanced_delims" for i in report.issues))

    def test_chapter_numbering_gap_detected(self) -> None:
        self._write("chapter-01.md", "# Chapter 1\n\nBody text here that is long enough.\n")
        self._write("chapter-03.md", "# Chapter 3\n\nBody text here that is long enough.\n")
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)
        self.assertTrue(any(i.check == "chapter_numbering" for i in report.issues))

    def test_chapter_numbering_filename_heading_mismatch_detected(self) -> None:
        self._write("chapter-07.md", "# Chapter 6\n\nBody text here that is long enough.\n")
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)
        mismatch = [i for i in report.issues if i.check == "chapter_numbering"]
        self.assertTrue(any("says" in i.message or "implies" in i.message for i in mismatch))

    def test_mojibake_detected(self) -> None:
        self._write("chapter-01.md", "# Chapter 1\n\nShe said â€œhelloâ€\x9d and walked away.\n")
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)
        self.assertTrue(any(i.check == "mojibake" for i in report.issues))

    def test_detect_style_curly_vs_straight(self) -> None:
        curly = detect_style({"a": "“Hello,” she said. “Yes.”"})
        self.assertEqual("curly", curly.quotes)
        straight = detect_style({"a": '"Hello," she said. "Yes."'})
        self.assertEqual("straight", straight.quotes)

    def test_empty_directory_fails(self) -> None:
        report = proof_manuscript(self.tempdir)
        self.assertTrue(report.failed)

    def test_report_renders_without_error(self) -> None:
        self._write("chapter-01.md", "# Chapter 1\n\nShe she went home.\n")
        report = proof_manuscript(self.tempdir)
        text = render_proof_report(report)
        self.assertIn("Manuscript Proof", text)


if __name__ == "__main__":
    unittest.main()
