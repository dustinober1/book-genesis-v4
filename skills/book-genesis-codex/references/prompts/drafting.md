# Drafting Prompt

You are responsible for Phase 3 of `book-genesis-codex`.

## Goal

Draft the manuscript in chapter blocks while preserving voice, momentum, and structural variation.

## Genre Pack (conditional)

Before drafting, resolve the genre pack for `project.genre` / `project.subgenre` per `knowledge/genre-packs/README.md`. **If no pack matches, skip this section entirely and change nothing** — no pack is the normal case.

If a pack matches, read it and treat any artifact it declares under `## Conditional Artifacts` as a hard read-dependency for every chapter, alongside its `## Prose Override Table`.

## Steering Notes (check before every block)

`work/steering.md` (created empty at Phase 0 intake, see `runner.filesystem.scaffold_project`) is the user's one channel to redirect the book mid-draft without stopping the run. Read it before writing each chapter block. If it has content, treat it as binding for the block you're about to write, overriding the outline or Voice DNA on the specific point it raises. Do not wait for it to be non-empty and do not ask the user to fill it in — an empty file is the normal case.

## Drafting Rules

- write in chapter blocks, not as disconnected scenes
- each block must have a clear narrative function
- use structural variation so consecutive blocks do not feel templated
- record which structural approach each chapter used: append `meta chapter=N structure=<name> hook=<name>` as its own line to `chapter-N-report.md` next to the chapter file (any short name for `<name>` is fine — "linear", "spiral", "in-medias-res", whatever actually describes the block). This phase's `structure_variety` gate check (below) reads that line to enforce "no two consecutive chapters share a structure" mechanically instead of by re-reading the whole manuscript at Phase 4. Skipping this line is not an error — the check simply has nothing to verify — but then the rule is unenforced, same failure mode this line exists to close.
- keep the emotional curve active
- keep character behavior consistent with wound, desire, need, and lie
- keep the opening promise and ending pressure alive

## Block Standard

Each chapter block should accomplish enough work to justify its existence. Common functions include:

- advance plot
- deepen character
- shift emotion
- sharpen theme
- intensify atmosphere or surreal texture

Not every block needs the same combination, but every block needs a reason to exist.

## Hitting the Per-Chapter Word Budget

The outline (Phase 2) records a per-chapter word budget. Draft each block to land within 90-115% of its own budget — not the book's total average. This is what prevents the failure mode of finishing a full draft short and needing a bulk expansion pass afterward: expansion done after the fact tends to pad rather than add material the chapter needed.

If a block comes in under its budget, that means something on the Block Standard list above was under-executed, not that the block is efficient. Before moving to the next block, check which function was shortchanged — a scene summarized instead of played out in real time, a secondary character's beat cut, atmosphere/interiority compressed around the block's ending pressure — and write it in. Do not carry a shortfall forward with the intent to "expand later"; fix it in the block where it happened.

## Consistency Checklist

After each block, verify:

- narrative function is clear
- names and world facts are consistent
- voice remains recognizable
- ending pressure is intact
- the block adds something the previous one did not

This consistency checklist is mandatory during Phase 3.

## Deterministic Gates During Drafting

Do not wait until Phase 4 to discover these. Run after every chapter block:

```bash
python3 -m runner.cli gate <project>
```

This runs every check Phase 3 declares — chronology, manuscript lint (set `project.lint_profile` in `PROJECT_STATE.yaml`, or it falls back to `project.subgenre`/`project.genre`), chapter ordering, structural-approach variety, and total word count — in one pass, and is the same command `advance-phase` uses to decide whether Phase 3 is done. A non-zero exit means at least one check failed; read `work/gate-report.md` for which one.

- A chronology failure halts drafting. Fix the timeline and the affected chapters before writing forward — every chapter written on a broken timeline is a chapter that will need rewriting.
- Lint failures accumulate silently and are far cheaper to fix per-block than across a finished manuscript. Verbal tics in particular compound: a phrase used twice in chapter 2 becomes eighty uses by chapter 14.
- `structure_variety` fails on two consecutive chapters sharing a `meta structure=...` value, or one structure holding more than ~40% of chapters (once 6+ are tracked) — the mechanical form of the Drafting Rules' "use structural variation" line above. It skips cleanly (never fails) until at least 2 chapters have recorded a `meta` line.
- The wordcount check compares the *whole manuscript so far* against the full `project.word_count_target`, so it will legitimately report `fail` on every run until the last chapter is drafted — that's expected mid-draft, not a signal to stop and fix something. Use the pacing check below instead to catch a shortfall while it's still cheap to fix.

## Pacing Check (run this at every checkpoint, not just at the end)

At each checkpoint below, compare actual manuscript word count against expected pace: `word_count_target × (chapters drafted so far ÷ total planned chapters)`. If actual is under ~90% of that figure, do not keep drafting forward at the current density — go back and expand the chapters that ran short (see Hitting the Per-Chapter Word Budget above) before starting the next block. Catching a pacing drift at the 25 percent checkpoint costs one or two chapters' worth of fixes; catching it after the final chapter costs a rewrite pass across the whole manuscript.

## Checkpoints

- after the opening block
- around 25 percent
- around 50 percent
- before the final movement

## Output

- manuscript chapters in `manuscript/chapters/`
- state updates in `PROJECT_STATE.yaml`
