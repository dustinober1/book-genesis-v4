from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.adopt import adopt_manuscript  # noqa: E402


class AdoptManuscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Path(tempfile.mkdtemp(prefix="book-genesis-adopt-src-"))
        self.target = Path(tempfile.mkdtemp(prefix="book-genesis-adopt-target-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.source, ignore_errors=True)
        shutil.rmtree(self.target, ignore_errors=True)

    def test_adopts_markdown_chapter(self) -> None:
        (self.source / "chapter-01.md").write_text("# Ch1\n\ntext\n", encoding="utf-8")
        report = adopt_manuscript(self.source, self.target)
        self.assertEqual(1, len(report.adopted))
        self.assertEqual(0, len(report.rejected))
        dest = self.target / "manuscript" / "chapters" / "chapter-01.md"
        self.assertTrue(dest.exists())
        self.assertEqual(report.adopted[0].source_sha256, report.adopted[0].destination_sha256)

    def test_rejects_unsupported_extension(self) -> None:
        (self.source / "notes.docx").write_bytes(b"binary")
        report = adopt_manuscript(self.source, self.target)
        self.assertEqual(0, len(report.adopted))
        self.assertEqual(1, len(report.rejected))
        self.assertIn("unsupported", report.rejected[0])

    def test_rejects_empty_file(self) -> None:
        (self.source / "chapter-01.md").write_text("", encoding="utf-8")
        report = adopt_manuscript(self.source, self.target)
        self.assertEqual(0, len(report.adopted))
        self.assertIn("empty", report.rejected[0])

    def test_rejects_symlink(self) -> None:
        target_file = self.source / "real.md"
        target_file.write_text("real content\n", encoding="utf-8")
        link = self.source / "chapter-01.md"
        try:
            link.symlink_to(target_file)
        except OSError:
            self.skipTest("symlinks not supported in this environment")
        report = adopt_manuscript(self.source, self.target)
        rejected_names = [r for r in report.rejected if "chapter-01.md" in r]
        self.assertEqual(1, len(rejected_names))

    def test_archives_rather_than_overwrites_existing_destination(self) -> None:
        dest_dir = self.target / "manuscript" / "chapters"
        dest_dir.mkdir(parents=True)
        (dest_dir / "chapter-01.md").write_text("old content\n", encoding="utf-8")

        (self.source / "chapter-01.md").write_text("new content\n", encoding="utf-8")
        report = adopt_manuscript(self.source, self.target)

        self.assertEqual(1, len(report.adopted))
        self.assertTrue(report.adopted[0].archived_previous)
        archived_path = self.target / report.adopted[0].archived_previous
        self.assertTrue(archived_path.exists())
        self.assertEqual("old content\n", archived_path.read_text(encoding="utf-8"))
        self.assertEqual(
            "new content\n",
            (dest_dir / "chapter-01.md").read_text(encoding="utf-8"),
        )

    def test_missing_source_directory_rejected(self) -> None:
        report = adopt_manuscript(self.source / "does-not-exist", self.target)
        self.assertEqual(0, len(report.adopted))
        self.assertEqual(1, len(report.rejected))


if __name__ == "__main__":
    unittest.main()
