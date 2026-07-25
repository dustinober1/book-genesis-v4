# Local Runner

Book Genesis is still a markdown-first, agent-run workflow. The local runner exists to make the workflow reproducible: it scaffolds the project tree, prepares the active phase packet, validates required outputs, runs deterministic quality gates, and compiles the final manuscript. `advance-phase` refuses to advance when a phase's gate checks fail — the gates are enforced in code, not just documented in the prompts.

If you installed via `install.sh`/`install.ps1`, the runner and the skill directories it depends on are both under `~/.claude/book-genesis-runner/`; run it from there, or set `BOOK_GENESIS_HOME` to point at that directory (see `runner/paths.py`).

It does not call an LLM and it does not claim literary quality. Agents still write, audit, score, and package the manuscript using the active phase prompt.

## Commands

```bash
python runner/cli.py init my-book --idea "a detective audits a haunted manuscript"
python runner/cli.py status my-book
python runner/cli.py prepare-phase my-book
python runner/cli.py advance-phase my-book
python runner/cli.py validate my-book
python runner/cli.py prepare-swarm my-book --mode hybrid --slug launch-reaction
python runner/cli.py prepare-agent-packet my-book prose_writer
python runner/cli.py set my-book project.autonomy auto
python runner/cli.py get my-book project.autonomy
python runner/cli.py lint my-book --profile literary
python runner/cli.py check-timeline my-book
python runner/cli.py proof my-book
python runner/cli.py structure my-book
python runner/cli.py gate my-book
python runner/cli.py macro my-book
python runner/cli.py ledger my-book
python runner/cli.py texture my-book
python runner/cli.py human-pass plan my-book
python runner/cli.py voice-lexicon my-book
python runner/cli.py baseline my-book --corpus ~/my-writing
python runner/cli.py fingerprint compare my-book
```

### `gate`

Runs every deterministic check the current (or `--phase`-named) phase declares in `manifest.yaml`'s `checks:` list — chronology, manuscript lint, chapter ordering, word count, typographic proofing, EPUB build/validation — in one pass, and writes `work/gate-report.md`. This is the same logic `advance-phase` runs internally; run it standalone anytime to see why a phase isn't ready. Exit 0 pass, 1 gate failure, 2 usage/environment error. `--json` prints a machine-readable verdict instead of Markdown.

An unrecognized check name in the manifest is reported as an `error`, not silently skipped — a typo can't quietly disable a gate.

Some checks are **advisory**: they run and report their real status on every gate, but a fail/error there never blocks `advance-phase` (see `gates.ADVISORY_CHECKS` in `runner/gates.py`). `--json`'s per-result objects carry an `"advisory": true/false` field, and the Markdown report marks them `STATUS (advisory)` in the table plus a summary line naming any that flagged. Currently advisory: `macro`, `texture`, `voice_lexicon` — none of their thresholds are calibrated against a real corpus yet. Promotion to a real, blocking gate is a one-line change (deleting the name from `ADVISORY_CHECKS`), not a rewrite.

### `set` / `get`

Read or write a `PROJECT_STATE.yaml` value. A bare key (`status`) uses the original first-match scan; a `block.key` path (`project.autonomy`, `project.word_count_target`) is scoped to that top-level block only, so `manuscript.status` can never accidentally shadow `pipeline.status`.

### `lint` / `check-timeline` / `proof` / `structure`

Standalone versions of the checks `gate` runs as a group — useful when iterating on one specific problem. `lint` catches machine-prose patterns (em-dash density, phrase repetition, opener monotony, close-proximity word echo, sentence-opener repeats within a paragraph, voice drift between the first and last third of the manuscript). `check-timeline` validates a `TIMELINE.md`/`TIMELINE.txt` chronology sheet for age/span contradictions. `proof` catches typographic defects (unbalanced quotes, doubled words, chapter numbering gaps) as distinct from lint's stylistic checks. `structure` reports a character presence matrix, absence gaps, and per-speaker dialogue differentiation.

`lint` auto-discovers a `style-profile.yaml` at the project root (or pass `--style-profile <path>`) and applies any threshold overrides it declares on top of the genre profile — see "Personal calibration" below.

### `macro` (advisory)

Book-level template detection: chapter opening/closing mode share (dialogue / question / image-action / fragment / maxim), scene-break count uniformity, and chapter-title parallelism. Needs at least 6 chapters to say anything — below that it reports `skip`, not a false "no template detected". Skips cleanly on a non-English project (`project.language`) since the mode classifiers are English-word heuristics.

### `ledger`

Scans every finalized `chapter-N.md` and writes `work/retired.md`: phrases, simile vehicles, chapter-opening words, and dialogue tags already used, plus (when each chapter's self-report carries a `meta` record) the most recently used structural approach and hook type. Meant to run after each chapter clears its quality gate, with the result fed into the NEXT chapter's writer dispatch as a banned list — turning the pipeline's repetition checks from post-mortem into prevention.

### `texture` (advisory)

Coverage report for `research/texture-bank.md` (a flat `texture id=... term="..." kind=place|object|jargon|price|weather src="..."` record per line — see `agents/book-researcher.md`'s WORLD-TEXTURE RESEARCH PROTOCOL): which entries actually appear in the manuscript, which are unused, and — the important one — which have no `src=`, since that is exactly where a hallucinated "researched" detail would hide. Skips cleanly when no bank exists (most projects won't have one; it's for books with a specific real-world or historical setting).

### `human-pass plan | apply | status`

The one lever nothing else in this package can substitute for: a small, mechanically-selected set of lines per chapter (opening, closing, a simile, a line of dialogue) for a person to hand-rewrite.

- `plan` writes `work/human-pass.md` with each candidate line, its chapter's sha256, and byte offsets at plan time.
- Hand-edit the `REWRITE:` fenced block for whichever entries you want changed; leave the rest untouched to skip them.
- `apply` re-verifies each chapter's sha256 hasn't changed since `plan` (refusing that chapter's edits otherwise — stale offsets are not safe to splice), archives the pre-edit chapter, splices the accepted rewrites in, and wraps each one in `<!-- hp:start -->...<!-- hp:end -->` markers so no later automated pass overwrites it. Those markers are ordinary HTML comments as far as lint, proof, and the EPUB compiler are concerned — invisible to the reader and to every measurement.
- `status` reports how many protected spans each chapter currently has.

This is a real (non-advisory) gate on Phase 7: Production — `human_pass` fails until `work/human-pass.md` exists. Set `project.skip_human_pass=true` to opt out explicitly (this is what `demo` does, since it has no human in the loop by construction).

### `voice-lexicon` (advisory)

Checks attributed dialogue against each character's `never_say` list in `voice-lexicon.yaml` (a project-root file, two-level flat YAML — see `agents/book-architect.md`'s VOICE DNA DOCUMENT section 6). Case-insensitive, word-boundary matched, mechanical — the `signature`/`contractions`/`fragments` fields in the same file are read but not scored, since they have no single measurable pass/fail line the way a banned word does.

### `baseline`

Compares a manuscript against a directory of the author's OWN writing (`--corpus <dir>`, `.md`/`.txt` files, 1,000-word minimum) and writes `work/baseline-report.md` — a metric-by-metric comparison (em-dash density, adverb density, dialogue ratio, Flesch-Kincaid grade, "said"/"asked" tag share). Warns when the corpus looks like a poor match for the project's genre (e.g. essays calibrating a dialogue-heavy thriller). Any derived threshold overrides are written to `style-profile.suggested.yaml` — **never** to the active `style-profile.yaml`, and never looser than the genre default unless `--allow-loosen` is passed. Activating a suggestion is a manual copy/rename, by design.

### `fingerprint save | compare`

Burrows' Delta stylometric comparison — the least trustworthy command in this package, and it says so on every report. `save` adds this manuscript's profile to a small JSON library (default `~/.claude/book-genesis/fingerprints/`, override with `--library-dir` or `$BOOK_GENESIS_FINGERPRINT_DIR`); `compare` measures the target against everything in the library. Below 6 references, no winner is named — a null simulation at n=2 references split winners 1004/996 across 2000 trials, so a smaller library would just be a confident coin flip. The headline use case: is a new manuscript closer to the author's own writing (`baseline`) than to a PREVIOUS manuscript this pipeline wrote? If books converge toward one house voice, this is the one thing in this package built to catch it — treat any result as a hypothesis to go read both texts against, never as a verdict (Delta is confounded by genre, tense, POV, and dialogue ratio at least as much as by authorial voice).

## Personal Calibration

`style-profile.yaml` (project root) overrides any `lint.Thresholds` field for this project — reviewable, hand-editable, and the format `baseline`'s suggestions are written in:

```yaml
lint:
  em_dash_per_1k: "3.2"
  phrase_per_10k: "6.0"
```

An unknown key or an unparseable value is reported as a warning (on both the `lint` CLI and the gate check) and simply not applied — never silently ignored, never a crash.

`prepare-phase` writes:

```text
my-book/work/current-phase.md
```

That file contains the phase label, gate, required outputs, and the full active phase prompt from `skills/book-genesis-codex/references/`.

`prepare-swarm` writes:

```text
my-book/evaluations/book-swarm/<date>-launch-reaction/
```

That folder contains the Book Swarm Panel contract: persona roster, sample map, cohort reports, interviews, public-opinion report, risk heatmap, revision tickets, score calibration, summary, and an optional `mirofish-requirement.md` bridge file for external MiroFish runs.

`prepare-agent-packet` writes:

```text
my-book/work/agent-packets/prose_writer.md
```

That file contains the specialist mission, missing inputs, required outputs, gates, score floor, and relevant skill prompt from `skills/book-bestseller-studio/references/agent-registry.yaml`.

## Mechanical Demo

Use this before launch, CI, or a demo recording:

```bash
python runner/cli.py demo .tmp-book-genesis-demo
python runner/cli.py status .tmp-book-genesis-demo
python runner/cli.py validate .tmp-book-genesis-demo
```

The demo fills deterministic placeholder outputs and advances all gates. It proves the file contract and phase mechanics, not manuscript quality.

## Compiling To A Publishable File

Phase 7: Production (`runner/compile.py`) turns the approved manuscript into files a reader, retailer, or agent can open:

```bash
# fill my-book/BOOK.yaml with title/author/etc. by hand first, then:
python runner/cli.py gate my-book --phase "Phase 7: Production"
```

That gate run compiles `manuscript/full-manuscript.md` (a single concatenated file) and builds `delivery/epub/book.epub` — a deterministic, stdlib-only EPUB3 (byte-identical across rebuilds, self-validated by re-parsing every part it wrote). The Markdown-to-XHTML renderer only understands a narrow fiction subset: headings, paragraphs, `*em*`/`**strong**`, blockquotes, and a scene-break rule. Tables, lists, images, links, footnotes, and raw HTML in a chapter file are a compile error naming the file and line, not silently mangled output — this is a stated fiction-only scope, not a bug. `pandoc`, if present on the machine, can additionally export PDF/DOCX; its absence is reported as skipped, never as a gate failure.

## What The Runner Guarantees

- `PROJECT_STATE.yaml` exists and tracks the current phase.
- `ASSUMPTIONS.md`, `RUN_REPORT.md`, `BOOK.yaml`, `artifacts/`, `manuscript/chapters/`, `evaluations/`, and `delivery/` exist.
- Phase outputs must be replaced before `advance-phase` succeeds, **and** the phase's declared `checks:` (chronology, lint, chapter order, word count, proofing, EPUB validation, and — non-advisory — a human-pass worksheet before production) must all pass — `advance-phase` runs them itself and refuses to advance on a failure. This is enforced in code, not just documented in a prompt.
- Phase 4 cannot be skipped because phase order is read from the manifest.
- Book-swarm runs use a durable folder contract before clean-room simulation or external MiroFish import.
- Specialist agents use packet files so worldbuilding, writing, pacing, continuity, scoring, packaging, and launch work have explicit ownership.

## What The Runner Does Not Do

- It does not call Claude, Codex, Kimi, OpenAI, or any other model.
- It does not generate real prose.
- It does not score a manuscript by itself (Genesis Score dimension scoring stays a judgment call for the evaluating agent).
- It does not run MiroFish. It prepares import/export files for an external MiroFish run when available.
- It does not produce PDF or DOCX on its own — only EPUB and a compiled Markdown file are pure-stdlib; PDF/DOCX require `pandoc` on the machine and are opportunistic, not gated.
- It does not compile non-fiction constructs (lists, tables, images, footnotes) — the EPUB compiler is fiction-only by design.

Those steps belong to the agent executing the phase prompt.
