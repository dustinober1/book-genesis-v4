from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.reader_evidence import import_reader_evidence, render_evidence_report  # noqa: E402


class ReaderEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-evidence-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _write_csv(self, rows: str) -> Path:
        path = self.tempdir / "evidence.csv"
        path.write_text("reader_id,chapter,rating,comment,delayed\n" + rows, encoding="utf-8")
        return path

    def test_weak_confidence_below_threshold(self) -> None:
        csv_path = self._write_csv("r1,1,5,great,0\n")
        report = import_reader_evidence(self.tempdir, csv_path)
        self.assertEqual("weak", report.confidence)
        self.assertEqual(1, report.total_responses)

    def test_moderate_confidence(self) -> None:
        csv_path = self._write_csv("r1,1,5,great,0\nr2,2,4,good,0\nr3,2,3,ok,0\n")
        report = import_reader_evidence(self.tempdir, csv_path)
        self.assertEqual("moderate", report.confidence)

    def test_strong_confidence_requires_diverse_signal(self) -> None:
        # 6 responses, 3 chapters, but all positive -- no critical signal -> moderate, not strong
        rows = "r1,1,5,a,0\nr2,1,4,b,0\nr3,2,5,c,0\nr4,2,4,d,0\nr5,3,5,e,0\nr6,3,4,f,0\n"
        csv_path = self._write_csv(rows)
        report = import_reader_evidence(self.tempdir, csv_path)
        self.assertEqual("moderate", report.confidence)

        rows_diverse = "r1,1,5,a,0\nr2,1,2,b,0\nr3,2,5,c,0\nr4,2,4,d,0\nr5,3,5,e,0\nr6,3,4,f,0\n"
        csv_path2 = self._write_csv(rows_diverse)
        report2 = import_reader_evidence(self.tempdir, csv_path2)
        self.assertEqual("strong", report2.confidence)

    def test_invalid_rows_rejected_not_crashed(self) -> None:
        csv_path = self._write_csv("r1,,5,missing chapter,0\nr2,1,9,bad rating,0\nr3,x,3,bad chapter,0\n")
        report = import_reader_evidence(self.tempdir, csv_path)
        self.assertEqual(3, len(report.rejected_rows))
        self.assertEqual(0, report.total_responses)

    def test_duplicate_reader_chapter_pair_flagged(self) -> None:
        csv_path = self._write_csv("r1,1,5,first,0\nr1,1,2,duplicate,0\n")
        report = import_reader_evidence(self.tempdir, csv_path)
        self.assertEqual(1, report.total_responses)
        self.assertEqual(1, len(report.duplicate_rows))

    def test_render_report_includes_disclaimer(self) -> None:
        csv_path = self._write_csv("r1,1,5,great,0\n")
        report = import_reader_evidence(self.tempdir, csv_path)
        text = render_evidence_report(report)
        self.assertIn("not simulated", text)
        self.assertIn("WEAK", text)


if __name__ == "__main__":
    unittest.main()
