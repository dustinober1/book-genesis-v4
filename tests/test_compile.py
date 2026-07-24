from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.compile import (  # type: ignore  # noqa: E402
    BookMeta,
    CompileError,
    book_meta_path,
    book_meta_template,
    build_epub,
    collect_chapters,
    compile_manuscript_md,
    load_book_meta,
    md_to_xhtml_body,
    scaffold_matter,
    validate_book_meta,
    validate_chapter_order,
    validate_epub,
)


def _write_chapter(chapters_dir: Path, name: str, heading: str, body: str = "A short paragraph of prose.") -> None:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / name).write_text(f"# {heading}\n\n{body}\n", encoding="utf-8")


class CompileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-compile-"))
        self.chapters_dir = self.tempdir / "manuscript" / "chapters"
        _write_chapter(self.chapters_dir, "chapter-01.md", "Chapter 1: Opening")
        _write_chapter(self.chapters_dir, "chapter-02.md", "Chapter 2: Middle")
        book_meta_path(self.tempdir).write_text(
            book_meta_template(title="Test Book", author="Test Author"), encoding="utf-8"
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_load_book_meta_roundtrip(self) -> None:
        meta = load_book_meta(self.tempdir)
        self.assertEqual("Test Book", meta.title)
        self.assertEqual("Test Author", meta.author)
        self.assertEqual("en", meta.language)

    def test_validate_book_meta_requires_title_and_author(self) -> None:
        problems = validate_book_meta(BookMeta())
        self.assertTrue(any("title" in p for p in problems))
        self.assertTrue(any("author" in p for p in problems))

    def test_book_meta_without_identifier_gets_stable_uuid_fallback(self) -> None:
        meta = BookMeta(title="T", author="A")
        first = meta.resolved_identifier()
        second = meta.resolved_identifier()
        self.assertTrue(first.startswith("urn:uuid:"))
        self.assertEqual(first, second)  # deterministic, not random

    def test_collect_chapters_orders_and_numbers(self) -> None:
        chapters = collect_chapters(self.tempdir)
        self.assertEqual(2, len(chapters))
        self.assertEqual(1, chapters[0].number)
        self.assertEqual(2, chapters[1].number)
        self.assertEqual("Chapter 1: Opening", chapters[0].title)

    def test_validate_chapter_order_detects_gap(self) -> None:
        _write_chapter(self.chapters_dir, "chapter-04.md", "Chapter 4: Late")
        chapters = collect_chapters(self.tempdir)
        problems = validate_chapter_order(chapters)
        self.assertTrue(any("gap" in p for p in problems))

    def test_validate_chapter_order_clean_set_has_no_problems(self) -> None:
        chapters = collect_chapters(self.tempdir)
        self.assertEqual([], validate_chapter_order(chapters))

    def test_markdown_subset_rejects_table(self) -> None:
        with self.assertRaises(CompileError):
            md_to_xhtml_body("| a | b |\n|---|---|\n| 1 | 2 |\n", source="test.md")

    def test_markdown_subset_rejects_list(self) -> None:
        with self.assertRaises(CompileError):
            md_to_xhtml_body("- first item\n- second item\n", source="test.md")

    def test_markdown_subset_rejects_image(self) -> None:
        with self.assertRaises(CompileError):
            md_to_xhtml_body("![alt text](cover.png)\n", source="test.md")

    def test_markdown_subset_renders_supported_constructs(self) -> None:
        html = md_to_xhtml_body(
            "# Title\n\nA paragraph with *em* and **strong** text.\n\n"
            "> A quoted line.\n\n---\n",
            source="test.md",
        )
        self.assertIn("<h1>Title</h1>", html)
        self.assertIn("<em>em</em>", html)
        self.assertIn("<strong>strong</strong>", html)
        self.assertIn("<blockquote>", html)
        self.assertIn("scene-break", html)

    def test_compile_manuscript_md_produces_single_file(self) -> None:
        meta = load_book_meta(self.tempdir)
        path = compile_manuscript_md(self.tempdir, meta)
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        self.assertIn("Test Book", text)
        self.assertIn("Chapter 1: Opening", text)
        self.assertIn("Chapter 2: Middle", text)

    def test_scaffold_matter_skips_on_rebuild_without_force(self) -> None:
        meta = load_book_meta(self.tempdir)
        first = scaffold_matter(self.tempdir, meta)
        self.assertTrue(first)
        second = scaffold_matter(self.tempdir, meta)  # not forced -> nothing new written
        self.assertEqual([], second)

    def test_build_epub_is_deterministic(self) -> None:
        meta = load_book_meta(self.tempdir)
        p1 = build_epub(self.tempdir, meta, out=self.tempdir / "e1.epub")
        p2 = build_epub(self.tempdir, meta, out=self.tempdir / "e2.epub")
        self.assertEqual(p1.read_bytes(), p2.read_bytes())

    def test_build_epub_structure_validates(self) -> None:
        meta = load_book_meta(self.tempdir)
        epub_path = build_epub(self.tempdir, meta)
        self.assertEqual([], validate_epub(epub_path))

    def test_build_epub_fails_without_title(self) -> None:
        with self.assertRaises(CompileError):
            build_epub(self.tempdir, BookMeta())

    def test_build_epub_mimetype_is_first_and_stored(self) -> None:
        import zipfile
        meta = load_book_meta(self.tempdir)
        epub_path = build_epub(self.tempdir, meta)
        with zipfile.ZipFile(epub_path) as zf:
            names = zf.namelist()
            self.assertEqual("mimetype", names[0])
            info = zf.getinfo("mimetype")
            self.assertEqual(zipfile.ZIP_STORED, info.compress_type)

    def test_epub_includes_scaffolded_front_matter(self) -> None:
        meta = load_book_meta(self.tempdir)
        scaffold_matter(self.tempdir, meta)
        # Fill copyright (not a stub) so it is included; dedication stays a
        # stub and must be skipped.
        (self.tempdir / "manuscript" / "front-matter" / "copyright.md").write_text(
            "# Copyright\n\nCopyright 2026 Test Author.\n", encoding="utf-8"
        )
        epub_path = build_epub(self.tempdir, meta)
        import zipfile
        with zipfile.ZipFile(epub_path) as zf:
            names = zf.namelist()
        self.assertTrue(any("front-copyright" in n for n in names))
        self.assertFalse(any("front-dedication" in n for n in names))


if __name__ == "__main__":
    unittest.main()
