# Production Prompt

You are responsible for Phase 7 of `book-genesis-codex`.

## Goal

Turn the approved, packaged manuscript into the files a retailer, agent, or beta reader can actually open: a filled `BOOK.yaml`, a single compiled manuscript file, front and back matter, a validated EPUB, and a pre-publication checklist. This is the last mile — nothing before this phase produces anything but Markdown artifacts and a chapters directory.

## Preconditions

Phase 6 (Editorial Package) must be complete. Do not start Production on a manuscript that has not cleared the adversarial audit and the Genesis floor.

## Steps

1. **Fill `BOOK.yaml`** at the project root with real metadata: title, subtitle, author, language, identifier (ISBN if one exists, otherwise leave blank — the compiler generates a stable `urn:uuid` fallback), publisher, rights statement, pubdate, description, series info, BISAC codes, and 7–10 KDP-style keywords.
2. **Write or confirm front and back matter.** Run:

   ```bash
   python3 -m runner.cli set <project> project.autonomy <level>   # if not already set
   ```

   then create front matter (half-title, title page, copyright, dedication, epigraph) under `manuscript/front-matter/` and back matter (acknowledgments, about the author, also-by) under `manuscript/back-matter/`, one file per section, each starting with a single `#` heading. Leave a section file untouched (its scaffolded stub) if the book genuinely has none — an unfilled stub is skipped at compile time, not compiled as placeholder text.
3. **Compile the manuscript and build the EPUB:**

   ```bash
   python3 -m runner.cli gate <project> --phase "Phase 7: Production"
   ```

   This runs `book_meta`, `chapter_order`, `proof`, `wordcount`, and `epub` in one pass, compiling `manuscript/full-manuscript.md` and `delivery/epub/book.epub` as part of the `epub` check and validating the result. Read `work/gate-report.md` for details on any failure.
4. **Write the pre-publication checklist** to `delivery/production/pre-publication-checklist.md`: cover art status, ISBN/ASIN status, KDP/IngramSpark metadata fields filled, EPUB validated, print interior status if applicable, and anything still open before the book can actually be listed.

## Markdown Scope

The compiler only understands a narrow fiction subset: headings, paragraphs, `*em*`/`**strong**`, blockquotes, and a scene-break rule. Tables, lists, images, links, footnotes, and raw HTML in a chapter file are a **compile error**, not silently mangled output — fix the source, not the compiler's behavior around it. This phase is fiction-only; a non-fiction manuscript needing lists, images, or footnotes is out of scope for the automated EPUB build and should note that explicitly in the checklist.

## Output

- `BOOK.yaml` — filled
- `manuscript/full-manuscript.md` — compiled, single file
- `manuscript/front-matter/`, `manuscript/back-matter/` — filled or left as skippable stubs
- `delivery/epub/book.epub` — built and gate-validated
- `delivery/production/pre-publication-checklist.md`

## Rules

- Do not hand-author the EPUB or the compiled manuscript file; both are produced by `runner.cli gate`/`runner.compile`, not written from scratch.
- A `book_meta`, `chapter_order`, `proof`, `wordcount`, or `epub` failure is a hard gate failure at every autonomy level, including `auto`. Fix the source and re-run; do not report Production complete on a failing gate.
- If `runner/` is unavailable, say so explicitly and mark this phase **UNVERIFIED** — never report it as passed without having run the gate.
