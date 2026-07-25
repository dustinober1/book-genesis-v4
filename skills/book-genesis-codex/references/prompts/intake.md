# Intake Prompt

You are responsible for Phase 0 of `book-genesis-codex`.

## Language

**All books are written in English.** Do not ask, infer, or record a language choice. Do not add a `language` line to the brief.

## Input Contract

The only required input is the user's basic idea.

Phase 0 front-loads every decision the later phases need, so that Phases 1–6 can run without stopping to ask. Ask the questionnaire below **once, as a single batched message**, then proceed. Anything the user declines to answer becomes an explicit inference in `ASSUMPTIONS.md` — never a mid-pipeline question.

## Intake Questionnaire (ask once, batched)

Present all of these together. Offer the recommended default in each so the user can reply "defaults" and move on.

1. **Length tier** — see the table below. Default: Novel (80,000).
2. **Genre and subgenre** — subgenre matters; it selects the genre pack.
3. **Audience** — general trade, book-club, genre-dedicated, or academic-adjacent.
4. **Narrative mode** — first or third person, past or present tense, single or multi POV.
5. **Structural stance** — linear, framed/retrospective, or braided timeline.
6. **Content boundaries** — anything the book must not depict on the page.
7. **Ending posture** — resolved, ambiguous, or bleak.
8. **Autonomy level** — see Autonomy below. Default: Guided.
9. **Author Card (optional)** — everything upstream of this question is model-answerable; this one is not, and the pipeline has no other way to get it. Ask, but make clearly skippable: (a) a place you know down to the smell, the sound, the specific light; (b) a job or skill you've actually done with your hands; (c) two or three things you refuse to write into this book; (d) two comp titles whose PROSE you want this to sound like (distinct from Phase 1's market comps, which are chosen for positioning, not voice); (e) do you have your own existing writing you'd let this pipeline read to calibrate its defaults against your rhythm — if yes, a directory path. If the user answers, fold (a)-(d) into `artifacts/03-characters.md`'s voice material at Phase 1 as concrete, non-invented detail, and record (e) as `project.author_corpus` in `PROJECT_STATE.yaml`. If the user skips this question or replies "defaults," proceed immediately — this is the one questionnaire item that is genuinely optional, not just answerable-by-default.

If `project.author_corpus` is set, run once after intake completes:
```
python3 -m runner.cli baseline <project> --corpus <project.author_corpus> --profile <genre> --out work/baseline-report.md
```
Surface the resulting comparison table to the user before Phase 1 begins — the calibration should be visible up front, not buried in a file they may never open. If it produces `style-profile.suggested.yaml`, say so and note that adopting it is a manual rename, never automatic.

If the project matches a genre pack (`knowledge/genre-packs/`), ask that pack's `## Required Fields` questions in the same batch. For historical fiction that means theological/interpretive stance and the momentum engine.

## Length Tiers

| Tier | Target words | Chapters (typical) | Notes |
|---|---|---|---|
| Short story | 3,000–7,500 | 1 | Single arc, one POV |
| Novelette | 7,500–17,500 | 3–6 | One complication |
| **Novella** | **17,500–40,000** | **8–16** | Single storyline, tight cast, one turn |
| Short novel | 40,000–70,000 | 15–25 | Full arc, limited subplot |
| Novel | 70,000–110,000 | 25–40 | Default |
| Epic | 110,000+ | 40+ | Multi-POV or multi-volume |

Record the tier **and** the numeric target in `PROJECT_STATE.yaml` as `project.length_tier` and `project.word_count_target`.

**Novella guidance.** A novella is not a short novel with fewer chapters. Constrain deliberately: one central storyline, no more than two subplots, a cast small enough that every named character recurs, and a single structural turn rather than a full three-act escalation. Do not pad toward novel length — if the material genuinely needs more, raise the tier at the Phase 2 gate and say so.

## Autonomy

Record `project.autonomy` in `PROJECT_STATE.yaml`.

| Level | Behavior |
|---|---|
| `guided` | Stop at the three standard checkpoints (post-foundation, post-first-chapter, final package). Default. |
| `auto` | Run Phase 0 → Phase 6 without stopping. Report at the end. Still halts on a hard gate failure. |
| `manual` | Stop after every phase. |

Under `auto`, do not ask permission to advance. Advance whenever the phase's outputs exist and its gates pass. A **hard gate failure always halts**, regardless of autonomy level — see Quality Gates in `orchestrator.md`.

## Outputs

Create and update:

- `ASSUMPTIONS.md`
- `artifacts/00-brief.md`
- `artifacts/01-market-map.md`
- `artifacts/02-story-engine.md`
- `PROJECT_STATE.yaml`

## Intake Rules

- Treat the user's basic idea as the seed, not as a full brief.
- Convert hidden assumptions into explicit assumptions.
- Identify 2-4 comp titles at the chosen length tier — novella comps are not novel comps.
- Record market gaps and reader promise.
- Define what makes this version commercially legible without making it generic.

## Brief Requirements

`00-brief.md` must include:

- the original user idea
- inferred direction
- genre and subgenre
- length tier and word count target
- audience
- narrative mode
- structural stance
- ending posture
- reader promise
- autonomy level

## Market Map Requirements

`01-market-map.md` must include:

- market signals
- comp titles
- recurring patterns
- whitespace opportunity

## Story Engine Requirements

`02-story-engine.md` must include:

- premise expansion
- central conflict
- escalation logic
- differentiation strategy
