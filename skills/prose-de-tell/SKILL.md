---
name: prose-de-tell
description: "Remove the deep AI-writing tells from NOVEL PROSE specifically — the ones that survive a clean surface (no em-dash overuse, no rule-of-three, no purple vocabulary) because they live in the machine's underlying habits of thought, not its word choice. Use on fiction manuscripts, especially after runner/lint.py and the 20-pattern anti-AI scan (agents/book-evaluator.md) flag deep patterns #11-20: Explanatory Extension, Binary Negation Opener, Precision Flex, Emotional Control Demonstration, Authoritative Description, Philosophical Asides, Clean Dialogue, Thematic Echo Chamber, Graduated Reveal, Emotional Temperature Report. Not for non-fiction, articles, or marketing copy — see skills/humanizer for those."
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
metadata:
  version: 1.0.0
---

# Prose De-Tell: Deep AI Patterns in Fiction

## Why this exists, and why it isn't `humanizer`

`skills/humanizer` is derived from Wikipedia's "Signs of AI writing" guide — a real, useful list, but written for encyclopedia articles and marketing copy. About a third of it does not apply to fiction and some of it actively contradicts this pipeline's own typographic convention: its Pattern #18 ("Curly Quotation Marks") tells you to convert `"..."` to straight quotes, which reverses `runner/proof.py`'s quote-style consistency check — every published novel uses curly quotes, and flagging them as an AI tell on a manuscript is simply wrong. Use `humanizer` for non-fiction, marketing, and editorial copy. Use this skill for narrative prose.

The patterns here are the ones a *surface* scan cannot catch. A chapter can have zero em dashes, no "rule of three," no inflated vocabulary, and still read as machine-written, because these ten patterns live in how the prose *thinks*, not in which words it picked. They are patterns #11-20 of the 20-pattern anti-AI scan already defined in `agents/book-evaluator.md` — that file scores them; this skill fixes them. Read `agents/book-evaluator.md`'s "ANTI-AI SCAN — 20 PATTERNS" section for the canonical definitions and genre-adjusted density thresholds before using this skill; do not restate or renumber them here.

## Process

1. Read the chapter (and, if it exists, the evaluator's report naming which of #11-20 it flagged and where).
2. For each flagged instance, find the pattern below, apply the fix, and verify the fix didn't just relocate the tell three sentences over.
3. Re-read the passage aloud (or simulate doing so) — every fix here should make the prose sound MORE like a specific person talked, not just less like a checklist violation.
4. Never fix a pattern by deleting the moment it was protecting (a real emotional beat, a genuine reveal) — fix the MACHINERY around it, not the substance.

## The 10 Deep Patterns

### #11 — Explanatory Extension

**The tell:** An observation or simile that unpacks its own comparison instead of leaving it raw. `runner/lint.py`'s `explanatory_extension` check catches a mechanical proxy of this (`grep`-able "not because / the kind of X that" constructions) — this skill fixes what that check flags, plus the subtler cases regex can't reach.

**Before:** "Her voice was flat, the kind of flat that meant she had already decided and was daring him to notice."
**After:** "Her voice was flat. She was daring him to notice."

**Fix:** Cut the clause that explains the image. If the reader needs the explanation, the image was wrong — pick a better one, don't gloss the weak one.

### #12 — Binary Negation Opener

**The tell:** "Not X. Not Y. [What it is]." Defining a thing by what it isn't before asserting what it is. `runner/lint.py`'s `not_x_but_y` check catches the single-sentence form; this pattern also covers the multi-sentence version regex can't span.

**Before:** "This wasn't fear. It wasn't even dread, exactly. It was something colder, something with no name yet."
**After:** "Something colder than fear moved through her, something with no name yet."

**Fix:** Assert first. If the negation is doing real work (a character explicitly ruling out an interpretation), keep ONE negation, not a ladder of them.

### #13 — Precision Flex

**The tell:** Unnecessarily exact numbers. A character who counts things precisely under stress, in a genre/scene where mid-1970s levels of precision would be more human ("a few," "maybe a dozen," "some").

**Before:** "Forty-three seconds passed before he answered. She had counted eleven cracks in the ceiling by then."
**After:** "It took him a while to answer. She'd lost count of the cracks in the ceiling."

**Fix:** Ask whether the character would actually have counted. Precision is earned by a character trait (an accountant, an engineer, an anxiety-driven counter) — it isn't a free intensifier.

### #14 — Emotional Control Demonstration

**The tell:** Notice emotion → manage it → continue, every time, successfully. Real people lose control sometimes; a narrator who never does reads as simulated.

**Before:** "She felt the anger rise. She took a breath, set it aside, and answered calmly."
**After:** "'Fine,' she said, in a voice that came out one register too high."

**Fix:** Let the management FAIL sometimes — the voice cracks, the hand shakes, the sentence trails off. This is what `agents/book-disruptor.md`'s "Emotional Control Break" operation targets directly; if the Disruptor already ran on this chapter, check whether it addressed this instance before adding another fix on top.

### #15 — Authoritative Description

**The tell:** Settings described with encyclopedic confidence — no gaps, no wrong first impressions, no confusion about what something is.

**Before:** "The room was a converted study, twelve feet by fourteen, with oak shelving along the north wall and a reading lamp from the 1940s."
**After:** "The room used to be a study — you could tell from the shelves, too tall for anything but books nobody read anymore."

**Fix:** Route description through a PERCEIVING character, not an omniscient measuring tape. Let them get something wrong, notice it late, or not know what a thing is for.

### #16 — Philosophical Asides

**The tell:** A universal truth extractable from context — a line that would work on a coffee mug. Distinct from Theme (which should recede in most chapters per `agents/book-writer.md`'s flexible obligations) — this is about a THOUGHT that reads as generated wisdom rather than a situated, character-specific reaction.

**Before:** "Grief, she realized, is not an event but a permanent renovation of the self."
**After:** "She kept setting two plates at dinner. Had for a month now. She didn't know how to stop."

**Fix:** Replace the extractable aphorism with a concrete, situated detail that only makes sense in this exact moment for this exact character — test: does the line still work if you delete everything around it? If yes, cut it.

### #17 — Clean Dialogue

**The tell:** Orderly turn-based exchanges, each line precisely responsive to the one before it. No interruptions, false starts, cross-talk, or non-answers.

**Before:**
> "Where were you?"
> "I was at the office. I had a deadline."
> "You could have called."
> "I know. I'm sorry."

**After:**
> "Where were —"
> "Office. Deadline. I know, I know, I should've—" He didn't finish it.

**Fix:** Break turn-taking. Let someone interrupt, answer the wrong question, or not answer at all. `agents/book-disruptor.md`'s "Dialogue Mess" operation and `agents/book-writer.md`'s DIALOGUE CRAFT section both target this — check whether either already ran before stacking a third fix on the same passage.

### #18 — Thematic Echo Chamber

**The tell:** Every detail resonates with the theme. Zero texture, zero noise — a world that exists only to illustrate an argument.

**Before (theme: control):** A character who is a control freak notices a perfectly organized spice rack, a precisely mowed lawn, an alphabetized bookshelf — every object reinforcing the same point.

**After:** Same character, same scene — but also a junk drawer nobody's touched in years, a plant she keeps forgetting to water, a coffee ring on the counter she hasn't wiped up. Some things just exist.

**Fix:** `agents/book-architect.md`'s SYMBOL & MOTIF SYSTEM already specifies this directly: allow 30-40% of descriptive detail to be TEXTURE — things that exist because the world is full of things, not because the theme requires them. If a chapter is failing this pattern, the fix is usually SUBTRACTION of thematic resonance, not addition of texture on top.

### #19 — Graduated Reveal

**The tell:** Every chapter follows the same shape: establish normal → anomaly → escalate → close on tension. Structurally competent, mechanically predictable across a whole book.

**Fix:** This is a book-level pattern, not a line-level one — it's what `agents/book-writer.md`'s STRUCTURAL DIVERSITY section and the `structure_variety` gate check (`runner/gates.py`) exist to prevent (8 structural types, no consecutive repeats, no single type over ~40% of chapters). If this skill is dispatched on a single chapter and this pattern is flagged, the real fix is at the outline level — check `outline.md`'s structural-approach assignment for this chapter and `work/retired.md` for what's already been used, and flag it back to `book-architect` rather than trying to line-edit a structural problem into looking different.

### #20 — Emotional Temperature Report

**The tell:** Regular, periodic body-state check-ins at even intervals — "her heart pounded," "his stomach twisted," "a chill ran down her spine" — showing up like a scheduled instrument reading rather than an actual reaction.

**Before:** "Her heart pounded. [two paragraphs of action] Her stomach twisted. [two paragraphs of action] A chill ran down her spine."
**After:** Cut two of the three. Let the one that remains carry more specific, situated weight — not "her heart pounded" but the exact physical thing THIS fear does to THIS body ("she couldn't remember how to swallow").

**Fix:** Count body-state check-ins per scene. If they land at roughly even intervals regardless of what's happening in the scene, that's the tell — real physical reactions cluster around what's actually frightening/exciting and go quiet everywhere else.

## Output

Report which of the 10 patterns were found, how many instances of each, and what was changed — in the same finding format `agents/book-evaluator.md` uses (location, what happens now, why it fails, revision direction), so the fix is auditable against the evaluation that flagged it. Do not report patterns you did not find; a clean chapter should say so, not pad the report.
