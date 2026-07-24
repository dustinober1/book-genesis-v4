# Genre Pack: Historical Fiction

**Matches:** `historical fiction`, `historical`, `biblical fiction`, `biblical`, `ancient history`

Loaded per `knowledge/genre-packs/README.md`. This pack adds fidelity rules on top of the base pipeline. It does not modify the 20-pattern anti-AI scan, the base prose research, the phase list, or the PASS criteria.

## Why this pack exists

Historical fiction fails in a way contemporary fiction does not: the reader stops believing the world. The base pipeline evaluates story, character, voice, and market. Nothing in it owns *"is this world materially real and internally consistent."* This pack owns that.

The biblical subgenre has a second problem on top of the first. The model knows the source material extremely well, and that fluency is the tell — it produces prose that sounds like a retelling rather than a novel, and characters who are theologically articulate in a way no one in the period was.

## Dimension 7 Recommendation

Set `dimension_7: {name: "period-fidelity"}` in STATE.yaml during Foundation.

Score 6.0–10.0 like every other dimension. It is a floor dimension — a book with a beautiful voice and a fake world is a failed historical novel.

**What earns each band:**

- **≤ 7.0** — Costume drama. Period signaled by props and names only. Characters are moderns in robes.
- **7.5** — Materially plausible but frictionless. Nobody is hungry, indebted, sick, or inconvenienced by distance.
- **8.5** — The world has economy and consequence. Constraint drives at least one plot decision. Sensory texture is specific and non-decorative.
- **9.0+** — The period *causes* the story. The plot could not be relocated to another century without collapsing.

## Supplemental Scan

Seven patterns, `H1`–`H7`. **Reported separately from the 20-pattern scan and never summed into it.** Score by density per 1000 words using the same intensity bands the base scan uses (`<0.5` minor, `0.5–1.0` moderate, `>1.0` strong).

### H1 — Scripture Register Bleed
Prose drifting into the cadence of a translation. The single strongest tell in biblical fiction.

Detect: `and it came to pass`, `behold`, `unto`, `verily`, `spake`, `whosoever`, `in those days`; sentence-initial `And` used as a chronicle connective; verb-subject inversion (`Then went he up`); the lectionary triple-clause rhythm.

Why it fails: it signals retelling, not narration. The reader hears a pulpit, not a person.

**Exception:** deliberate register-shift inside quoted liturgy, prayer, or recitation is correct and does not count — mark it as scoped.

### H2 — Theological Articulacy
Characters explain doctrine fluently and accurately. Everyone sounds catechized.

Detect: dialogue that would function unaltered in a sermon; characters naming abstractions (covenant, atonement, righteousness) as concepts rather than as practice or obligation; any character explaining the significance of their own religious act.

Fix direction: replace doctrine with *practice, cost, and fear*. People knew what they owed, what was unclean, and what would shame them. They did not know systematics.

### H3 — Foreknowledge Leak
The narration or a character leans toward the historical significance of an event they cannot know is significant.

Detect: portentous closing lines on ordinary scenes; a character noticing that a moment "felt like the beginning of something"; weather or light turning symbolic exactly when the canon says something important happened.

This is the most common source of unearned solemnity, and it reads as AI because the model knows the ending and cannot stop gesturing at it.

### H4 — Sanitization
The world has no bodies. Sunday-school staging.

Detect: absence across a full chapter of dirt, smell, insects, teeth, illness, menstruation, animal death, latrine logistics, or physical labor leaving a mark. Also: violence with no aftermath, and meals with no scarcity.

Calibrate to POV plausibility — a wealthy urban character notices different discomforts than a field laborer, but both notice something.

### H5 — Anachronistic Interiority
Modern psychological vocabulary in an ancient mind. Distinct from H2 and worth counting separately.

Detect: therapy register — `process`, `boundaries`, `closure`, `space`, `trauma`, `self-worth`, `I need to be heard`; individualist framing of decisions in an honor/shame society; a character psychoanalyzing their own motive.

Fix direction: the period's emotional grammar is honor, shame, debt, purity, obligation, and fear of exposure — not affect labeling.

### H6 — Costume Without Economy
Setting as scenery rather than as a system of constraint.

Detect: nobody owes money, pays a toll, fears a tax farmer, hauls water, rations lamp oil, or is limited by how far a person walks in a day. Travel that takes exactly as long as the plot requires.

Test: cut every proper noun from a scene. If nothing about the remaining text tells you the century, this pattern is present.

### H7 — Verse-Sequence Plotting
Chapters follow the order of the source passages rather than a novel's shape.

Detect: chapters that exist because the next event in the canon is next; episodic beads with no causal chain; a climax that lands where the source says it lands rather than where the built pressure says it should.

This one is structural — flag it to the Adversarial Audit's Pass 1 (Existence Test) rather than treating it as a prose fix.

### Threshold Table

| Band | H-patterns present |
|---|---|
| Clean | 0–1 |
| Watch | 2–3 |
| Fidelity failure | 4+ |

**Calibration note, stated honestly:** unlike the 20-pattern table, these bands are not derived from a scored benchmark corpus. They are a working calibration. If you score a shelf of published historical fiction against H1–H7, replace these numbers with what you measure and record the corpus here.

**Cap rule:** Fidelity failure caps `period-fidelity` at 7.0. H1 at strong intensity caps `prose_voice` at 7.5 regardless of the total, because register bleed damages voice specifically.

## Prose Override Table

Consulted **after** the base profile in `knowledge/bestseller-prose-patterns.md`. The base numbers are not modified — they are calibrated on modern commercial thrillers (Patterson, Cornwell, Cussler) and remain correct for those genres.

Enforcing modern-thriller prose metrics on historical fiction produces a contemporary novel in costume, which reads *more* synthetic, not less.

| Metric | Base (commercial) | Historical override |
|---|---|---|
| Flesch-Kincaid grade | 6.0 | 7.0–9.0 |
| Avg sentence length | 14–20 words | 16–24 words, with wider variance |
| Dialogue ratio | 43–59% | 25–40% |
| Sensory detail density | not specified | ≥ 3 non-decorative physical specifics per scene |
| Dialogue tags | `said` near-exclusive | unchanged — `said` still wins |
| Chapter-ending hook rate | ≥ 80% | ≥ 70% (dread accumulates; not every chapter cliffhangs) |

**Comps for calibration:** Anita Diamant (*The Red Tent*), Marilynne Robinson, Hilary Mantel (*Wolf Hall*), Geraldine Brooks (*The Secret Chord*), Colm Tóibín (*The Testament of Mary*).

The `said`-default rule carries over unchanged. Archaic dialogue tags are H1, not period flavor.

## Conditional Artifacts

Produced during **Phase 1: Foundation**, alongside the standard outputs. Required only when this pack is loaded.

### `artifacts/11-period-bible.md`
The material world, sourced. Every entry carries a source note; entries that are informed guesses are marked `INFERRED`.

Required sections:
- Material culture — what is in a room, and what is *not* (no chairs, no glass windows, no stirrups, no potatoes, no paper)
- Economy — currency, wages, debt, taxation, who owes whom
- Food and water — sources, storage, scarcity, seasonality
- Distance and travel — time cost per route the plot uses
- Law and hierarchy — who can compel whom, and what happens when they do
- Religious practice as routine — purity, festival calendar, obligation. Practice, not theology.
- Health — disease load, injury outcomes, life expectancy, childbirth
- Climate and calendar — what the weather is doing during each act

This becomes a hard read-dependency for Phase 3 drafting.

### `artifacts/12-canon-ledger.md`
Four buckets, every plot beat and every attributed line assigned to exactly one, with reference:

| Beat or line | Bucket | Reference | Note |
|---|---|---|---|
| … | `canonical` / `tradition` / `reconstruction` / `invention` | passage or source | why, if invented |

- **canonical** — the source text states this directly
- **tradition** — later interpretive tradition, not the text itself. Identifying an unnamed figure with a named one lives here, as does any location the text does not specify.
- **reconstruction** — not attested, but plausible given the period record
- **invention** — deliberately extends or contradicts the source

The `tradition` bucket is the one that gets skipped, and skipping it is what informed readers punish. A traditional identification presented as established fact reads as either ignorance or dishonesty.

**Dialogue rule:** any line placed in the mouth of a figure who appears in the source is a ledger row. Invented prophetic or quasi-scriptural dialogue is the highest-risk category — a fabricated line that conveniently validates the book's own premise is the most conspicuous authorial thumb on the scale in the genre. Prefer the ordinary exchange.

These four buckets map directly onto the four sections of the author's note, which is the single highest-credibility page in the genre.

### `artifacts/13-timeline.md` → also written as `TIMELINE.md` at the project root
The machine-checkable chronology. Root copy is what `python3 -m runner.cli check-timeline` reads.

Must contain every date-bearing element: character ages, deaths, arrivals, length of service, legal proceedings and adjournments, festival calendar, and every named interval the prose asserts ("eleven years", "nine days", "three nights before").

Format and validation rules are documented at the top of `runner/timeline.py`.

**This is a hard gate.** Build it before drafting and re-run the checker after every chapter block. Retrospective first-person narration makes interval arithmetic especially error-prone, because the narrator states spans in round numbers that quietly contradict each other.

### `artifacts/14-style-sheet.md`
Terminology decisions, fixed once and enforced at copyedit.

Required rows: every name with more than one possible rendering (transliterated vs. anglicized), every compound that could be open/hyphenated/closed, capitalization of institutions and structures, festival names, and the exact term for every category of household worker — with its legal meaning stated, not assumed.

A person's legal status is a research decision with ethical weight, not a synonym choice. Fix it here and never vary it.

## Required Fields

### `ASSUMPTIONS.md` — theological stance (Phase 0)
Record one of: **devotional**, **humanist**, **ambivalent**. Left unstated, drafting drifts toward reverent-default, which flattens conflict and produces H3 and H4 at volume.

### `artifacts/07-opening-strategy.md` — `momentum_engine` (Phase 2)
The base Momentum dimension assumes the reader wants to know what happens. In biblical fiction the reader already knows. Suspense must come from somewhere else, and it is an architecture decision, not something to discover mid-draft.

Set `momentum_engine` to exactly one, named explicitly:

- **`pov-displacement`** — narrate from someone whose fate is not recorded (a servant, a tax clerk, a soldier's wife). The reader's foreknowledge does not cover this person.
- **`dramatic-irony`** — the reader knows, the character does not. Tension converts from curiosity to dread.
- **`cost-not-outcome`** — the question stops being *does it happen* and becomes *what does it destroy in this person*.

The Evaluator checks that the drafted chapters actually run the declared engine. A declared engine that the prose does not use caps `pacing_coherence` at 7.5.

## Required Fields (continued)

### `artifacts/11-period-bible.md` — dependent status (Phase 1)
For every character in service, servitude, or legal dependence, fix and record:

- how they entered that status
- the exact legal category, in period terms
- its lawful duration, and why this case matches or departs from it
- what they may own, refuse, or leave
- whether their status changes during the book, and who decides

Leaving this vague while the protagonist's own autonomy is the book's theme is a contradiction readers will name. If the protagonist defends their independence while directing another person's unfree labor, the narrative must know that, whether or not the protagonist does.

## Adversarial Audit Additions

Append to the standard Phase 4 passes (which already include the deterministic Pass 8):

- **Pass 14: Anachronism Sweep** — every object, food, technology, institution, and idiom checked against `11-period-bible.md`. Flag anything absent from the bible as unverified. Watch for modern abstraction in legal, administrative, and psychological register — terminology like *liability*, *oversight*, *risk profile*, or *governance* is anachronistic unless the text explicitly frames it as a translation of an older concept.
- **Pass 15: Canon Contradiction** — every `canonical` row in `12-canon-ledger.md` re-checked against its reference. A contradiction not marked `invention` is a defect, not a choice. Every `tradition` row confirmed to be presented as tradition in the text or the author's note, never as fact.
- **Pass 16: Constraint Test** — name at least one plot decision *caused* by a period constraint (distance, debt, purity law, harvest, illness). If none exists, the setting is scenery and `period-fidelity` caps at 7.5.
- **Pass 17: Climax Causality** — the resolution must turn on demonstrated, evidenced competence, not on the accumulated moral or spiritual significance the book has assigned its protagonist. Ask the hostile question: could the same facts be argued to the opposite conclusion? If yes, the win is authorial favor rather than earned outcome. Emotional vindication and evidentiary victory are different things, and the second one has to carry the scene.
- **Pass 18: Physical Continuity** — clothing, injuries, carried objects, and time of day tracked across every scene where they matter. Adaptations of a specific detail from a source text must be internally consistent, and the ledger must record them as adaptation.
