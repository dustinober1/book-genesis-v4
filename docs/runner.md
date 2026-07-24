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
```

### `gate`

Runs every deterministic check the current (or `--phase`-named) phase declares in `manifest.yaml`'s `checks:` list — chronology, manuscript lint, chapter ordering, word count, typographic proofing, EPUB build/validation — in one pass, and writes `work/gate-report.md`. This is the same logic `advance-phase` runs internally; run it standalone anytime to see why a phase isn't ready. Exit 0 pass, 1 gate failure, 2 usage/environment error. `--json` prints a machine-readable verdict instead of Markdown.

An unrecognized check name in the manifest is reported as an `error`, not silently skipped — a typo can't quietly disable a gate.

### `set` / `get`

Read or write a `PROJECT_STATE.yaml` value. A bare key (`status`) uses the original first-match scan; a `block.key` path (`project.autonomy`, `project.word_count_target`) is scoped to that top-level block only, so `manuscript.status` can never accidentally shadow `pipeline.status`.

### `lint` / `check-timeline` / `proof` / `structure`

Standalone versions of the checks `gate` runs as a group — useful when iterating on one specific problem. `lint` catches machine-prose patterns (em-dash density, phrase repetition, opener monotony). `check-timeline` validates a `TIMELINE.md`/`TIMELINE.txt` chronology sheet for age/span contradictions. `proof` catches typographic defects (unbalanced quotes, doubled words, chapter numbering gaps) as distinct from lint's stylistic checks. `structure` reports a character presence matrix, absence gaps, and per-speaker dialogue differentiation.

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
- Phase outputs must be replaced before `advance-phase` succeeds, **and** the phase's declared `checks:` (chronology, lint, chapter order, word count, proofing, EPUB validation) must all pass — `advance-phase` runs them itself and refuses to advance on a failure. This is enforced in code, not just documented in a prompt.
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
