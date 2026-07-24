"""Compile a manuscript into publishable output: a single manuscript.md
and a deterministic, self-validating EPUB3 file.

Pure stdlib, matching the rest of runner/. EPUB3 is built by hand with
``zipfile`` (the mimetype entry written first and STORED, per the OCF
spec) and validated by re-parsing every part it wrote — no external
EPUB-validation tool required, though ``pandoc`` can optionally produce
PDF/DOCX alongside it when present on the machine (never required, never
gating: its absence is reported as ``skip``, not ``fail``).

The Markdown-to-XHTML renderer only understands a narrow fiction subset:
ATX headings, paragraphs, *em*/**strong**, blockquotes, and a scene-break
rule. Anything outside that (tables, lists, images, links, footnotes, raw
HTML) is a compile error naming the file and line, not silently mangled
output. Non-fiction constructs (lists, tables, images, footnotes) are out
of scope for this module by design -- see the plan this shipped under.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from xml.etree import ElementTree
from xml.sax.saxutils import escape as _xml_escape
import zipfile
from typing import Dict, List, Optional, Sequence, Tuple

from runner.filesystem import _load_simple_yaml_map  # reuse the one YAML-ish parser in this repo

EPOCH = (1980, 1, 1, 0, 0, 0)
FRONT_MATTER_ORDER: Tuple[str, ...] = (
    "half-title", "title-page", "copyright", "dedication", "epigraph",
)
BACK_MATTER_ORDER: Tuple[str, ...] = (
    "acknowledgments", "about-the-author", "also-by",
)


# --------------------------------------------------------------------------
# Metadata
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BookMeta:
    title: str = ""
    subtitle: str = ""
    author: str = ""
    language: str = "en"
    identifier: str = ""
    publisher: str = ""
    rights: str = ""
    pubdate: str = ""
    description: str = ""
    series: str = ""
    series_index: str = ""
    bisac: Tuple[str, ...] = ()
    keywords: Tuple[str, ...] = ()

    def resolved_identifier(self) -> str:
        if self.identifier:
            return self.identifier
        seed = f"book-genesis:{self.title}:{self.author}"
        return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"


def book_meta_path(target: Path) -> Path:
    return target / "BOOK.yaml"


def book_meta_template(*, title: str = "", author: str = "") -> str:
    return (
        "book:\n"
        f'  title: "{title}"\n'
        '  subtitle: ""\n'
        f'  author: "{author}"\n'
        '  language: "en"\n'
        '  identifier: ""\n'
        '  publisher: ""\n'
        '  rights: ""\n'
        '  pubdate: ""\n'
        '  description: ""\n'
        '  series: ""\n'
        '  series_index: ""\n'
        "  bisac:\n"
        '    - ""\n'
        "  keywords:\n"
        '    - ""\n'
    )


def load_book_meta(target: Path) -> BookMeta:
    path = book_meta_path(target)
    if not path.exists():
        return BookMeta()
    entries = _load_simple_yaml_map(path)
    b = entries.get("book", {})

    def _s(key: str) -> str:
        return str(b.get(key, "") or "")

    def _list(key: str) -> Tuple[str, ...]:
        raw = b.get(key, [])
        if not isinstance(raw, list):
            return ()
        return tuple(v for v in raw if v)

    return BookMeta(
        title=_s("title"), subtitle=_s("subtitle"), author=_s("author"),
        language=_s("language") or "en", identifier=_s("identifier"),
        publisher=_s("publisher"), rights=_s("rights"), pubdate=_s("pubdate"),
        description=_s("description"), series=_s("series"), series_index=_s("series_index"),
        bisac=_list("bisac"), keywords=_list("keywords"),
    )


def validate_book_meta(meta: BookMeta) -> List[str]:
    problems: List[str] = []
    if not meta.title:
        problems.append("BOOK.yaml: title is required")
    if not meta.author:
        problems.append("BOOK.yaml: author is required")
    if not meta.language:
        problems.append("BOOK.yaml: language is required")
    return problems


# --------------------------------------------------------------------------
# Chapters
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ChapterDoc:
    path: Path
    order: int
    number: Optional[int]
    title: str
    body_md: str


CHAPTER_NUMBER = re.compile(r"(\d+)")
H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def collect_chapters(target: Path) -> List[ChapterDoc]:
    chapters_dir = target / "manuscript" / "chapters"
    files = sorted(p for p in chapters_dir.glob("*.md") if p.is_file()) if chapters_dir.is_dir() else []
    docs: List[ChapterDoc] = []
    for order, p in enumerate(files):
        text = p.read_text(encoding="utf-8")
        m = CHAPTER_NUMBER.search(p.stem)
        number = int(m.group(1)) if m else None
        h1 = H1.search(text)
        title = h1.group(1).strip() if h1 else p.stem
        docs.append(ChapterDoc(path=p, order=order, number=number, title=title, body_md=text))
    return docs


def validate_chapter_order(chapters: List[ChapterDoc]) -> List[str]:
    problems: List[str] = []
    if not chapters:
        problems.append("No chapter files found under manuscript/chapters/")
        return problems
    numbered = [c for c in chapters if c.number is not None]
    if len(numbered) != len(chapters):
        for c in chapters:
            if c.number is None:
                problems.append(f"{c.path.name}: filename has no chapter number")
    for i in range(1, len(numbered)):
        if numbered[i].number != numbered[i - 1].number + 1:  # type: ignore[operator]
            problems.append(
                f"Chapter numbering gap: {numbered[i-1].path.name} (#{numbered[i-1].number}) "
                f"-> {numbered[i].path.name} (#{numbered[i].number})"
            )
    return problems


# --------------------------------------------------------------------------
# Front/back matter
# --------------------------------------------------------------------------

_MATTER_TEMPLATES: Dict[str, str] = {
    "half-title": "# {title}\n",
    "title-page": "# {title}\n\n{subtitle_line}*{author}*\n",
    "copyright": (
        "# Copyright\n\n"
        "Copyright (c) {year} {author}. All rights reserved.\n\n"
        "{rights}\n"
    ),
    "dedication": "# Dedication\n\n*(fill in a dedication, or delete this file)*\n",
    "epigraph": "# Epigraph\n\n*(fill in an epigraph, or delete this file)*\n",
    "acknowledgments": "# Acknowledgments\n\n*(fill in acknowledgments, or delete this file)*\n",
    "about-the-author": "# About the Author\n\n*(fill in an author bio, or delete this file)*\n",
    "also-by": "# Also By {author}\n\n*(list other titles, or delete this file)*\n",
}


def matter_dir(target: Path, kind: str) -> Path:
    section = "front-matter" if kind in FRONT_MATTER_ORDER else "back-matter"
    return target / "manuscript" / section


def scaffold_matter(target: Path, meta: BookMeta, *, force: bool = False) -> List[Path]:
    written: List[Path] = []
    for kind in (*FRONT_MATTER_ORDER, *BACK_MATTER_ORDER):
        directory = matter_dir(target, kind)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{kind}.md"
        if path.exists() and not force:
            continue
        template = _MATTER_TEMPLATES[kind]
        text = template.format(
            title=meta.title or "Untitled",
            subtitle_line=f"*{meta.subtitle}*\n\n" if meta.subtitle else "",
            author=meta.author or "Unknown Author",
            year=(meta.pubdate[:4] if meta.pubdate else "____"),
            rights=meta.rights or "All rights reserved.",
        )
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def collect_matter(target: Path, kind: str) -> List[ChapterDoc]:
    order = (*FRONT_MATTER_ORDER, *BACK_MATTER_ORDER)
    path = matter_dir(target, kind) / f"{kind}.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "*(fill in" in text or "*(list other titles" in text:
        return []  # unfilled template stub: skip, do not compile placeholder text
    h1 = H1.search(text)
    title = h1.group(1).strip() if h1 else kind.replace("-", " ").title()
    return [ChapterDoc(path=path, order=order.index(kind), number=None, title=title, body_md=text)]


# --------------------------------------------------------------------------
# Narrow Markdown -> XHTML
# --------------------------------------------------------------------------

class CompileError(Exception):
    def __init__(self, source: str, line: int, message: str):
        super().__init__(f"{source}:{line}: {message}")
        self.source = source
        self.line = line
        self.message = message


_SCENE_BREAK = re.compile(r"^\s*([*#~\-]\s*){3,}$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
_FORBIDDEN = (
    (re.compile(r"!\["), "image syntax is not supported by the fiction compiler"),
    (re.compile(r"(?<!!)\[[^\]]*\]\([^)]*\)"), "link syntax is not supported by the fiction compiler"),
    (re.compile(r"\[\^[^\]]+\]"), "footnote syntax is not supported by the fiction compiler"),
    (re.compile(r"^\s*\|.*\|\s*$"), "tables are not supported by the fiction compiler"),
    (re.compile(r"^\s*([-*+]|\d+[.)])\s+\S"), "lists are not supported by the fiction compiler"),
    (re.compile(r"^\s*<[a-zA-Z]"), "raw HTML is not supported by the fiction compiler"),
)


def _inline(text: str) -> str:
    escaped = _xml_escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    return escaped


def md_to_xhtml_body(md: str, *, source: str = "<chapter>") -> str:
    lines = md.splitlines()
    out: List[str] = []
    para: List[str] = []
    quote: List[str] = []

    def flush_para() -> None:
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    def flush_quote() -> None:
        if quote:
            out.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>")
            quote.clear()

    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip()

        if not line.strip():
            flush_para()
            flush_quote()
            continue

        if _SCENE_BREAK.match(line):
            flush_para()
            flush_quote()
            out.append('<hr class="scene-break"/>')
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_para()
            flush_quote()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            continue

        bq = _BLOCKQUOTE.match(line)
        if bq:
            flush_para()
            quote.append(bq.group(1).strip())
            continue
        else:
            flush_quote()

        for pattern, message in _FORBIDDEN:
            if pattern.search(line):
                raise CompileError(source, lineno, f"{message}: {line.strip()[:60]!r}")

        para.append(line.strip())

    flush_para()
    flush_quote()
    return "\n".join(out)


def xhtml_document(title: str, body: str, lang: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        f'lang="{_xml_escape(lang)}">\n'
        "<head>\n"
        f"<title>{_xml_escape(title)}</title>\n"
        '<link rel="stylesheet" type="text/css" href="../css/style.css"/>\n'
        '<meta charset="utf-8"/>\n'
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


# --------------------------------------------------------------------------
# manuscript.md
# --------------------------------------------------------------------------

def compile_manuscript_md(target: Path, meta: BookMeta) -> Path:
    chapters = collect_chapters(target)
    parts: List[str] = [f"# {meta.title or 'Untitled'}\n"]
    if meta.subtitle:
        parts.append(f"## {meta.subtitle}\n")
    parts.append(f"*by {meta.author or 'Unknown Author'}*\n")

    for kind in FRONT_MATTER_ORDER:
        for doc in collect_matter(target, kind):
            parts.append(doc.body_md.strip() + "\n")

    for c in chapters:
        parts.append(c.body_md.strip() + "\n")

    for kind in BACK_MATTER_ORDER:
        for doc in collect_matter(target, kind):
            parts.append(doc.body_md.strip() + "\n")

    out = target / "manuscript" / "full-manuscript.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return out


# --------------------------------------------------------------------------
# EPUB3
# --------------------------------------------------------------------------

_CSS = (
    "body { font-family: serif; line-height: 1.5; margin: 1em; }\n"
    "h1, h2 { text-align: center; }\n"
    "hr.scene-break { border: none; text-align: center; margin: 2em 0; }\n"
    "hr.scene-break::before { content: \"* * *\"; }\n"
    "blockquote { margin: 1em 2em; font-style: italic; }\n"
)


def _mimetype_zipinfo() -> zipfile.ZipInfo:
    info = zipfile.ZipInfo("mimetype", date_time=EPOCH)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o644 << 16
    return info


def _fixed_zipinfo(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def _container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
        '  </rootfiles>\n'
        '</container>\n'
    )


@dataclass(frozen=True)
class _ManifestItem:
    item_id: str
    href: str
    media_type: str
    in_spine: bool
    nav_title: str = ""


def _content_opf(meta: BookMeta, items: Sequence[_ManifestItem]) -> str:
    identifier = meta.resolved_identifier()
    manifest_lines = []
    for item in items:
        props = ' properties="nav"' if item.item_id == "nav" else ""
        manifest_lines.append(
            f'    <item id="{item.item_id}" href="{item.href}" media-type="{item.media_type}"{props}/>'
        )
    spine_lines = [f'    <itemref idref="{item.item_id}"/>' for item in items if item.in_spine]

    meta_lines = [
        f'    <dc:title>{_xml_escape(meta.title or "Untitled")}</dc:title>',
        f'    <dc:creator>{_xml_escape(meta.author or "Unknown Author")}</dc:creator>',
        f'    <dc:language>{_xml_escape(meta.language or "en")}</dc:language>',
        f'    <dc:identifier id="book-id">{_xml_escape(identifier)}</dc:identifier>',
    ]
    if meta.publisher:
        meta_lines.append(f'    <dc:publisher>{_xml_escape(meta.publisher)}</dc:publisher>')
    if meta.rights:
        meta_lines.append(f'    <dc:rights>{_xml_escape(meta.rights)}</dc:rights>')
    if meta.description:
        meta_lines.append(f'    <dc:description>{_xml_escape(meta.description)}</dc:description>')
    if meta.pubdate:
        meta_lines.append(f'    <dc:date>{_xml_escape(meta.pubdate)}</dc:date>')
    meta_lines.append('    <meta property="dcterms:modified">1980-01-01T00:00:00Z</meta>')

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        + "\n".join(meta_lines) + "\n"
        '  </metadata>\n'
        '  <manifest>\n'
        + "\n".join(manifest_lines) + "\n"
        '  </manifest>\n'
        '  <spine>\n'
        + "\n".join(spine_lines) + "\n"
        '  </spine>\n'
        '</package>\n'
    )


def _nav_xhtml(meta: BookMeta, entries: Sequence[_ManifestItem]) -> str:
    li = "\n".join(
        f'      <li><a href="{item.href}">{_xml_escape(item.nav_title or item.item_id)}</a></li>'
        for item in entries if item.in_spine and item.nav_title
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head><title>Table of Contents</title><meta charset=\"utf-8\"/></head>\n"
        "<body>\n"
        '  <nav epub:type="toc" id="toc">\n'
        f"    <h1>{_xml_escape(meta.title or 'Contents')}</h1>\n"
        "    <ol>\n" + li + "\n    </ol>\n"
        "  </nav>\n"
        "</body>\n</html>\n"
    )


@dataclass
class CompileResult:
    manuscript_md: Optional[Path] = None
    epub: Optional[Path] = None
    pdf: Optional[Path] = None
    docx: Optional[Path] = None
    errors: List[str] = field(default_factory=list)


def build_epub(target: Path, meta: BookMeta, *, out: Optional[Path] = None) -> Path:
    problems = validate_book_meta(meta)
    if problems:
        raise CompileError("BOOK.yaml", 0, "; ".join(problems))

    chapters = collect_chapters(target)
    order_problems = validate_chapter_order(chapters)
    if order_problems:
        raise CompileError("manuscript/chapters", 0, "; ".join(order_problems))

    entries: List[_ManifestItem] = []
    xhtml_by_href: Dict[str, str] = {}

    def add_doc(doc: ChapterDoc, item_id: str, subdir: str) -> None:
        href = f"text/{subdir}-{item_id}.xhtml"
        body = md_to_xhtml_body(doc.body_md, source=str(doc.path))
        xhtml_by_href[href] = xhtml_document(doc.title, body, meta.language or "en")
        entries.append(_ManifestItem(item_id, href, "application/xhtml+xml", True, doc.title))

    for kind in FRONT_MATTER_ORDER:
        for doc in collect_matter(target, kind):
            add_doc(doc, kind, "front")

    for c in chapters:
        item_id = f"chapter-{c.number if c.number is not None else c.order + 1:02d}"
        add_doc(c, item_id, "ch")

    for kind in BACK_MATTER_ORDER:
        for doc in collect_matter(target, kind):
            add_doc(doc, kind, "back")

    nav_item = _ManifestItem("nav", "nav.xhtml", "application/xhtml+xml", False)

    out_path = out or (target / "delivery" / "epub" / "book.epub")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    opf = _content_opf(meta, [nav_item, *entries])
    nav = _nav_xhtml(meta, entries)

    if out_path.exists():
        out_path.unlink()

    with zipfile.ZipFile(out_path, "w") as zf:
        zf.writestr(_mimetype_zipinfo(), b"application/epub+zip")
        zf.writestr(_fixed_zipinfo("META-INF/container.xml"), _container_xml())
        zf.writestr(_fixed_zipinfo("OEBPS/content.opf"), opf)
        zf.writestr(_fixed_zipinfo("OEBPS/nav.xhtml"), nav)
        zf.writestr(_fixed_zipinfo("OEBPS/css/style.css"), _CSS)
        for href, xhtml in sorted(xhtml_by_href.items()):
            zf.writestr(_fixed_zipinfo(f"OEBPS/{href}"), xhtml)

    return out_path


def validate_epub(path: Path) -> List[str]:
    problems: List[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if not names or names[0] != "mimetype":
                problems.append("mimetype is not the first entry in the archive")
            else:
                info = zf.getinfo("mimetype")
                if info.compress_type != zipfile.ZIP_STORED:
                    problems.append("mimetype entry must be stored uncompressed")
                if zf.read("mimetype") != b"application/epub+zip":
                    problems.append("mimetype content is wrong")

            xhtml_names = [n for n in names if n.endswith(".xhtml")]
            for name in xhtml_names:
                try:
                    ElementTree.fromstring(zf.read(name))
                except ElementTree.ParseError as exc:
                    problems.append(f"{name}: malformed XHTML ({exc})")

            if "OEBPS/content.opf" not in names:
                problems.append("OEBPS/content.opf is missing")
            else:
                try:
                    opf = ElementTree.fromstring(zf.read("OEBPS/content.opf"))
                except ElementTree.ParseError as exc:
                    problems.append(f"OEBPS/content.opf: malformed XML ({exc})")
                    opf = None
                if opf is not None:
                    ns = {"opf": "http://www.idpf.org/2007/opf"}
                    hrefs = {
                        item.get("href") for item in opf.findall(".//opf:manifest/opf:item", ns)
                    }
                    for href in hrefs:
                        full = f"OEBPS/{href}"
                        if full not in names:
                            problems.append(f"manifest references missing file: {href}")
                    ids = {item.get("id") for item in opf.findall(".//opf:manifest/opf:item", ns)}
                    for itemref in opf.findall(".//opf:spine/opf:itemref", ns):
                        if itemref.get("idref") not in ids:
                            problems.append(f"spine references unknown manifest id: {itemref.get('idref')}")
    except (zipfile.BadZipFile, KeyError) as exc:
        problems.append(f"could not open EPUB: {exc}")
    return problems


# --------------------------------------------------------------------------
# Optional pandoc export (never required, never gating)
# --------------------------------------------------------------------------

def export_via_pandoc(target: Path, meta: BookMeta, fmt: str) -> Optional[Path]:
    if shutil.which("pandoc") is None:
        return None
    manuscript = target / "manuscript" / "full-manuscript.md"
    if not manuscript.exists():
        compile_manuscript_md(target, meta)
    out_path = target / "delivery" / fmt / f"book.{fmt}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pandoc", str(manuscript), "-o", str(out_path),
         "--metadata", f"title={meta.title}", "--metadata", f"author={meta.author}"],
        check=True, capture_output=True,
    )
    return out_path if out_path.exists() else None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def compile_all(target: Path, *, formats: Sequence[str] = ("md", "epub")) -> CompileResult:
    meta = load_book_meta(target)
    result = CompileResult()

    if "md" in formats:
        try:
            result.manuscript_md = compile_manuscript_md(target, meta)
        except CompileError as exc:
            result.errors.append(str(exc))

    if "epub" in formats:
        try:
            result.epub = build_epub(target, meta)
        except CompileError as exc:
            result.errors.append(str(exc))

    if "pdf" in formats:
        try:
            result.pdf = export_via_pandoc(target, meta, "pdf")
        except subprocess.CalledProcessError as exc:
            result.errors.append(f"pandoc pdf export failed: {exc}")

    if "docx" in formats:
        try:
            result.docx = export_via_pandoc(target, meta, "docx")
        except subprocess.CalledProcessError as exc:
            result.errors.append(f"pandoc docx export failed: {exc}")

    return result
