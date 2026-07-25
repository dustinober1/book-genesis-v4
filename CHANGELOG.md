# Changelog

## V4.3 — 2026-07-25

The existing quality gates catch a manuscript-shaped problem after it's already in the manuscript. This release adds prevention alongside detection, anchors the prose to a specific human's writing instead of a stranger's editorial report, and closes three live bugs the earlier work would otherwise have inherited.

### Fixed: HTML comments leaking into the compiled EPUB and corrupting lint counts

Every chapter carries a `<!-- Word count: ... -->` metadata header (`agents/book-writer.md`). `md_to_xhtml_body` had no comment handling, so that header compiled straight into the reader-facing EPUB as visible garbage text. Separately, `<!--`/`-->` each contain `--`, which `lint.py`'s em-dash counter read as two prose em dashes per comment — a single header alone was +2 phantom em dashes against a 4.0/1k FAIL threshold. Fixed with one new primitive, `discover.strip_comments`, wired into the compiler, lint, proof, and the word-count gate. The demo fixture now includes a comment-bearing chapter so this class of bug can't hide again.

### Added: advisory gate checks

New deterministic checks can now run on every gate and report their real status — visible in the report and `--json` — without blocking `advance-phase` while their thresholds are still uncalibrated. `gates.ADVISORY_CHECKS` names them; promotion to a real, blocking gate is deleting one name from that set. `macro`, `texture`, and `voice_lexicon` (below) all ship this way.

### Added: word echo, sentence-opener repeats, and voice drift (`lint`)

Three new manuscript-lint findings, all warn-severity pending real-world calibration: **word echo** catches a distinctive word repeating within a close window even when manuscript-wide repetition looks clean; **sentence-opener repeats** catches a paragraph where several consecutive sentences share an opening word (narrower than the existing paragraph-level opener check); **voice drift** catches speaker pairs that were distinguishable early in the manuscript and have statistically converged by the end — the failure mode neither a single-chapter check nor a whole-book average can see.

### Added: book-level template detection (`macro`, advisory)

Chapter opening/closing mode share (dialogue / question / image-action / fragment / maxim), scene-break count uniformity, and chapter-title parallelism, at manuscript scale rather than chapter scale. Needs six or more chapters to say anything — below that it reports `skip`, not a false "no template detected."

### Added: the retired-phrase ledger (`ledger`)

Turns the pipeline's repetition checks from post-mortem into prevention. After each finalized chapter, `runner/cli.py ledger` scans every chapter and writes `work/retired.md`: phrases, simile vehicles, chapter-opening words, and dialogue tags already used, plus (from a new `meta` record in the writer's self-report) the most recently used structural approach and hook type. The next chapter's writer dispatch reads this as a banned list instead of finding out from the evaluator two chapters later.

### Added: sourced world-texture research (`texture`, advisory)

For books with a specific real-world or historical setting: `research/texture-bank.md` holds sourced, verified sensory detail (place/object/jargon/price/weather), and `runner/cli.py texture` reports which entries made it into the manuscript, which are unused, and — the important one — which have no source, since that is exactly where a hallucinated "researched" fact would hide. `book-researcher` gained a WORLD-TEXTURE RESEARCH PROTOCOL and a conditional Phase 2.6 dispatch.

### Added: the human pass (`human-pass`) — new CHECKPOINT 3

The one lever nothing else in this system can substitute for: a small, mechanically-selected set of lines per chapter (opening, closing, a simile, a line of dialogue) for a person to hand-rewrite. `human-pass plan` builds the worksheet; `human-pass apply` splices accepted rewrites back in, wrapped in `<!-- hp:start -->...<!-- hp:end -->` markers that no later automated pass (editor, disruptor, writer) may touch. This is a real, non-advisory gate on Phase 7: Production — set `project.skip_human_pass=true` to opt out explicitly. The pipeline now has **4 checkpoints**, not 3; delivery moved from Checkpoint 3 to Checkpoint 4.

### Added: personal baseline calibration (`baseline`)

Compares a manuscript against a directory of the author's own writing and writes `work/baseline-report.md` — a metric-by-metric comparison, not a gate. Derived lint-threshold overrides are written to `style-profile.suggested.yaml`, never to the active `style-profile.yaml`, and never looser than the genre default unless `--allow-loosen` is passed explicitly. `style-profile.yaml` (new: `runner/styleprofile.py`) lets any project override `lint.Thresholds` fields directly, reviewed and hand-edited.

### Added: voice lexicon checks (`voice-lexicon`, advisory)

`voice-lexicon.yaml` (new `book-architect` output, alongside `voice-dna.md`) gives each character's "never says" list a machine-checkable form — `runner/cli.py voice-lexicon` flags attributed dialogue that violates it.

### Added: stylometric fingerprinting (`fingerprint`)

Burrows' Delta comparison against a small library of prior manuscripts, meant to answer one question: does a new book measure closer to the author's own writing than to a previous book this pipeline wrote? Deliberately the least trusting module in the runner — a null simulation showed the ranking is a coin flip below 6 reference profiles, so no winner is ever named below that floor, and every report carries an explicit confound warning (Delta is dominated by genre/tense/POV/dialogue ratio at least as much as by authorial voice).

### Changed: Step E (mechanical preprocess) now uses the runner, not raw grep/sed

The orchestrator's per-chapter mechanical pass previously re-implemented em-dash counting, adverb counting, and opener-repetition checking as raw bash — duplicate, less accurate versions of what `lint.py` already did properly, and out of sync with `skills/book-genesis-full/SKILL.md`'s Phase 3.8, which already routed through `lint`/`proof`. Step E now calls `runner/cli.py lint` and `runner/cli.py proof` directly; only the Pattern #11 grep and the per-chapter word-count check (which have no runner equivalent yet) remain as direct bash.

## V4.2 — 2026-06-10

### Added: Premise Forge (Phase 1.5)

The pipeline now transforms raw ideas into structurally sound premises **before** writing starts.

Previously, the system executed your idea as-is. If your shower thought lacked an irony engine — the structural contradiction that makes readers unable to put a book down — the best prose in the world couldn't fix it.

Phase 1.5 introduces a forge step between research and foundation:

- `book-architect` is dispatched in "forge mode" (dispatch 0)
- 5 premise variants are generated: Variant 1 is your raw idea scored honestly; Variants 2–5 use different irony engines (inverted protagonist, relocated stakes, market gap fusion, weaponized reader frustrations from negative comp reviews, collapsed character contradiction)
- Each variant is scored across 6 dimensions: hook, irony engine, native escalation, the central question, gap fit, retellability
- The floor IS the score — a 9/9/9/9/9/4 is a 4
- Winner needs floor ≥ 8.0; one re-forge round allowed; if still below 8.0, the system proceeds with the best variant and flags it at Checkpoint 1
- Hard rule: **ELEVATE, DON'T REPLACE** — you must recognize your idea inside the winning premise
- Output: `premise.md` — binding for the entire foundation downstream

Checkpoint 1 now opens by showing you the transformation: raw idea → forged pitch sentence → "what changed and why" in plain language.

### Added: 8.5 Gate System

The quality gate was previously a target without enforcement. V4.2 makes it a hard gate:

- **Per-chapter gate**: chapters below 8.5 on Genesis Floor or Casual score cannot advance
- **Polish Loop**: the evaluator produces a "Path to 8.5" work order; the editor targets only the blocking dimensions; max 5 iterations per chapter
- **Anti-inflation**: each polish cycle can add +0.5 maximum — jumping from 7.5 to 8.5 requires ≥ 2 real improvement cycles
- **3-state verdict**: PASS (Floor ≥ 8.5 AND Casual ≥ 8.5) / POLISH (above hard floor but below 8.5) / FAIL (below hard floor)
- **Exit gate**: manuscript only moves to packaging when ALL chapters ≥ 8.5 AND CVI-Launch ≥ 9.0

The hard floor is genre-adjusted: literary fiction and memoir set it at 7.5; commercial fiction, thriller, and prescriptive nonfiction at 7.0.

### Added: Phase 5 exit criteria

Phase 5 (full manuscript revision) now has a concrete exit condition:
- Every chapter must hold Genesis Floor ≥ 8.5
- CVI-Launch must reach ≥ 9.0 ("breakout potential, Gone Girl tier")
- Up to 3 full revision cycles
- If still below after 3 cycles: explicit decision at Checkpoint 2 (proceed anyway, keep revising, or abort)

### Changed: book-architect

- Role updated from 2 dispatches to 3 (dispatch 0 = forge mode → premise.md, dispatch 1 = foundation + outline, dispatch 2 = voice DNA)
- New section: PREMISE FORGE MODE — full scoring rules, variant generation instructions, elevate-don't-replace constraint, genre shift detection
- Foundation section now reads premise.md first; the winning variant's irony engine, escalation ladder, and central question are binding inputs
- Beat Subversion marked MANDATORY in outline section

### Changed: book-orchestrator

- Pipeline diagram updated with Phase 1.5
- PHASE 1.5 block added with full dispatch instructions, after-return state update, and genre-shift delta research trigger
- CHECKPOINT 1 updated to show premise transformation first
- Parallelism chain updated: research → premise forge → foundation → voice DNA → entity build → outline continuity
- Project init tree updated with premise.md

### Changed: README

- Full rewrite. Previous README described V3 architecture with different agent names.
- New README explains the pipeline in plain English, describes all 3 gates with concrete scoring examples, and lists all 8 agents with plain-English descriptions.

### Added: all 8 agents to `agents/` folder

Previous repo only contained `book-orchestrator.md`. All agents now included:
- `book-orchestrator.md`
- `book-architect.md`
- `book-researcher.md`
- `book-writer.md`
- `book-evaluator.md`
- `book-editor.md`
- `book-disruptor.md`
- `book-packager.md`

---

## V4.0 — 2026-05-26 (initial public release)

- First public release of Book Genesis V4
- 8.5+ editorial quality target (not yet enforced as a hard gate)
- 9-skill book studio documentation
- MIT licensed
