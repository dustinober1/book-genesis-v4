# Architecture Prompt

You are responsible for Phase 2 of `book-genesis-codex`.

## Goal

Convert the story foundation into a concrete architecture that can support drafting with momentum, clarity, and strong opening pages.

## Outputs

Create and update:

- `artifacts/05-outline.md`
- `artifacts/07-opening-strategy.md`
- `PROJECT_STATE.yaml`

## Architecture Rules

- build a chapter or block outline with clear narrative function
- define the ending turn for each major block
- preserve escalation logic from the story engine
- align the architecture with the emotional curve
- include a visible tension map
- define an opening strategy that promises what the book will actually deliver
- allocate `project.word_count_target` across chapters and record a per-chapter word budget

## Per-Chapter Word Budget

Divide `project.word_count_target` across the planned chapter count, weighted by each chapter's narrative load (a climax or braided-timeline chapter carries more than a quiet bridge chapter) — not an equal split. No chapter should be budgeted at more than 2x the shortest. Record the per-chapter figure in the outline entry for that chapter (e.g. `Word budget: ~2,800`).

This budget exists so Phase 3 drafts each chapter to its intended length the first time, instead of discovering a shortfall only after the manuscript is finished and needing a bulk expansion pass. If the sum of chapter budgets doesn't land within the wordcount gate's tolerance (85%-125%) of `word_count_target`, fix the allocation now — do not defer it to drafting.

## Outline Requirements

`05-outline.md` must include:

- macro structure
- chapter outline
- narrative function for each chapter or block
- per-chapter word budget
- central conflict
- ending turn
- tension map

## Opening Strategy Requirements

`07-opening-strategy.md` must include:

- opening strategy
- first line options
- first page promise
- chapter one ending

## Opening Quality Rules

- the first line must earn the second
- the opening must establish voice, tension, or care
- the chapter one ending must increase forward pressure
