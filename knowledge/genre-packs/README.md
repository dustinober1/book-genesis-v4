# Genre Packs

A genre pack is an **optional overlay** that adds genre-specific fidelity rules to the Book Genesis pipeline without changing the default path.

The core pipeline stays genre-neutral. A pack is loaded only when it matches the project, and a project with no matching pack behaves exactly as it did before packs existed.

## Resolution

1. Read `project.genre` and `project.subgenre` from `STATE.yaml` (or `PROJECT_STATE.yaml`).
2. Slugify each (lowercase, spaces and slashes to `-`).
3. Look for `knowledge/genre-packs/<subgenre-slug>.md`, then `knowledge/genre-packs/<genre-slug>.md`.
4. **If neither filename exists**, check the `**Matches:**` line at the top of each pack file in this directory for the raw genre or subgenre string. This is what lets `genre: "Biblical Fiction"` resolve to `historical-fiction.md` without a duplicate file.
5. First match wins. **No match is not an error** — proceed with the base pipeline and say nothing.

Only one pack loads per project. Packs do not stack or inherit.

## What a pack MAY do

| Capability | Mechanism |
|---|---|
| Add a supplemental scan | Patterns numbered in its own namespace (`H1`, `H2`, …) with its own threshold table |
| Add required artifacts | Declared under `## Conditional Artifacts`, produced in the phase the pack names |
| Add prose targets | An **override table** consulted *after* the base profile, never a rewrite of it |
| Recommend Dimension 7 | A suggested `dimension_7.name` — the existing configurable slot |
| Require a field in an existing artifact | Named under `## Required Fields`, scoped to the artifact and phase |

## What a pack MUST NOT do

These are hard constraints. A pack that violates one is broken.

- **Never renumber or modify the 20-pattern anti-AI scan.** Its thresholds are calibrated against benchmark data (human-written bestsellers score 0–13/20). Supplemental patterns live in a separate namespace with a separate table and are never summed into the 20.
- **Never edit `knowledge/bestseller-prose-patterns.md` or the other `bestseller-*.md` files.** Those are sourced research documents. Packs override by adding a table, not by retuning the base numbers.
- **Never add, remove, or reorder pipeline phases.** The manifest is 7 phases for every project. Pack artifacts attach to an existing phase.
- **Never change a Genesis Score dimension definition** other than by recommending a value for the already-configurable Dimension 7.
- **Never change hard floors or PASS criteria.** Genesis Floor ≥ 8.5 AND Casual ≥ 8.5 remains the only PASS for every genre.

## Contract with the core

The core references packs in exactly two inert places:

- `agents/book-evaluator.md` — one conditional load step, which no-ops when no pack matches.
- `skills/book-genesis-codex/references/pipeline/manifest.yaml` — one documentation key on Phase 1, ignored by `runner/filesystem.py` (the `Phase` constructor reads only known keys).

If adding a pack changes gate behavior for a project that does not match it, the isolation has failed. Verify with the regression check below.

## Regression check

Any change to a pack or to the loader contract must keep this green:

```bash
python3 -m unittest tests.test_runner -v
```

Then confirm a non-matching project is untouched: scaffold a project whose genre has no pack file and verify its phase count, gate list, and required outputs are byte-identical to a run from before the pack was added.

## Available packs

| File | Matches | Adds |
|---|---|---|
| `historical-fiction.md` | `historical fiction`, `biblical fiction`, `historical` | H1–H7 fidelity scan, Period Bible, Canon Ledger, momentum engine field |

## Adding a pack

Copy the section headings from `historical-fiction.md`. A pack is read by an agent, not parsed by code, so prose is fine — but keep the headings stable, because the evaluator looks for `## Supplemental Scan` and `## Prose Override Table` by name.
