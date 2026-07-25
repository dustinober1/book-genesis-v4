# Genesis Score

## Purpose

Genesis Score is the single scoring contract for the Universal Book Genesis Core in `book-genesis-codex`.
It must be used consistently across prompts, adapters, examples, reports, and manual review.

The score exists to answer one question:

> Is this manuscript ready to survive contact with demanding readers, skeptical agents, and the market it claims to serve?

## Order Of Operations

The score only happens after Phase 4: Adversarial Audit.

If the adversarial audit concludes `MAJOR REWRITE`, the score may be recorded provisionally but the manuscript is not eligible for approval.

## Dimensions

The score uses 10 GATED dimensions (count toward Floor Score, Weighted Average, and the Approval Gate):

1. Originality
2. Theme
3. Characters
4. Prose
5. Pacing
6. Emotion
7. Coherence
8. Market
9. Voice
10. Opening

Plus one INFORMATIONAL dimension, tracked but never gated — see Risk below and "Why Risk Is Not Gated" under Calculation.

11. Risk (informational only)

## What Each Dimension Measures

### Originality

- novelty of premise, lens, or execution
- freedom from stale imitation

### Theme

- depth of the central question
- resonance beyond plot mechanics

### Characters

- wound, desire, need, contradiction, and memory value

### Prose

- sentence quality
- precision
- texture
- avoidance of cliche and explanatory drag

### Pacing

- tension control
- variation
- forward pull

### Emotion

- whether the book actually lands its intended feeling

### Coherence

- internal logic
- continuity
- causal integrity

### Market

- comp clarity
- audience legibility
- packaging viability

### Voice

- recognizability
- distinctiveness
- durability over pages

### Opening

- first-page grip
- first-chapter promise
- whether the ending ultimately justifies that promise

### Risk (informational — see "Why Risk Is Not Gated" below)

- evidence of a choice that could have failed: a refused payoff, a protagonist decision left unredeemed, a formal device sustained at real cost, a scene that serves nothing but itself and earns its place anyway
- absence of evidence is not a penalty by itself — score 6.0 ("no identifiable risk taken") and say so plainly; this dimension exists to surface competent-but-safe manuscripts, not to punish a book that had no reason to take one
- do not confuse Risk with recklessness: a risk that simply doesn't work is still evidence for this dimension (the book tried something), but is also evidence AGAINST whichever gated dimension the failure actually damaged (Coherence, Emotion, Pacing) — score both honestly rather than letting one excuse the other

## Scoring Rules

- baseline assumption is competence, not excellence
- any score above 8.0 must cite evidence
- any score above 9.0 must cite multiple pieces of evidence
- evidence must be textual, structural, or reader-impact based

## Calculation

Floor Score = minimum of the 10 GATED dimension scores (Risk excluded)
Weighted Average = weighted mean of the 10 GATED dimensions (Risk excluded)

Suggested weights:

- Originality: 1.1
- Theme: 1.0
- Characters: 1.2
- Prose: 1.0
- Pacing: 1.0
- Emotion: 1.1
- Coherence: 0.9
- Market: 0.8
- Voice: 1.1
- Opening: 0.8

Risk has no weight and is never averaged into Weighted Average or compared against Floor Score.

### Why Risk Is Not Gated

Three simultaneous minimums (Floor >= 8.5, Average >= 9.0, no dimension < 8.0) select for the manuscript with no weak dimension — which is also, mechanically, the manuscript with no dimension pushed hard enough to risk becoming a weak one. A book that never gambles never fails, and under a pure floor-and-average gate, never failing scores exactly as well as a book that gambled and won. Making Risk a THIRD kind of gate criterion (a floor of its own) would just relocate the safe-optimum problem one dimension over — the system would learn to hit a Risk floor exactly as reliably as it hits every other floor, at which point "risk" stops meaning risk. Tracking it as informational, never gated, is what keeps it honest: a low score here costs nothing and is never something the pipeline optimizes toward, so it stays a genuine signal for the human reading the report at CHECKPOINT 2, not one more number for the polish loop to chase.

## Approval Gate

Approval requires all of the following:

- Floor Score >= 8.5 (10 GATED dimensions only)
- Weighted Average >= 9.0 (10 GATED dimensions only)
- no GATED dimension below 8.0
- evidence present for every dimension, including Risk
- adversarial audit not marked `MAJOR REWRITE`

Risk is reported alongside the gate verdict but never blocks it, regardless of score.

## Revision Logic

If the manuscript fails:

1. identify the weakest dimension
2. define the concrete intervention
3. verify that the intervention does not damage stronger dimensions
4. rescore after revision

## Output Contract

The final report saved to `artifacts/09-genesis-score.md` or `artifacts/09-genesis-score-codex.md` must include:

- project and runtime context
- Dimension Scores table, including Risk marked "(informational, not gated)"
- Floor Score
- Weighted Average
- Risk score with its evidence, reported separately from the gate verdict
- Gate Verdict
- weakest GATED dimension
- required intervention or approval note
