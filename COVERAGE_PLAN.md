# Coverage Plan

Best Seller Studio is not conventional software; it is a pipeline of Markdown-defined agents. "Coverage" here means confidence that the pipeline produces correct behavior across the input space, not line coverage of a compiled binary.

## What we test

### 1. Agent prompt correctness

Every agent in `/agents/` has:
- A minimum-viable input brief that must pass its exit criteria
- A known-bad brief that must fail its exit criteria (to catch regressions where the agent stops enforcing rules)

Location: `tests/agents/<agent-name>/{good,bad}/`

### 2. Phase 1.5 — Premise Forge

The forge is the highest-leverage phase; a bad premise poisons everything downstream. We test:
- **Variant generation:** raw idea → 5 variants with distinct irony engines (asserted by classifier or manual review)
- **6-dimension scoring:** each variant scored across hook, irony engine, native escalation, central question, gap fit, retellability
- **Floor mechanic:** minimum dimension IS the score (not average, not weighted average)
- **ELEVATE-DON'T-REPLACE:** the winning premise must retain the concept-DNA of the raw input

Location: `tests/premise-forge/`

### 3. 8.5 Gate enforcement

The gate is the second highest-leverage mechanism. We test:
- **Per-chapter block:** a chapter with any dimension < 8.5 cannot advance
- **Anti-inflation:** polish loop caps +0.5/cycle; a 7.5 → 8.5 jump in one cycle must be rejected
- **Exit criteria:** manuscript-level exit requires all chapters ≥ 8.5 AND CVI-Launch ≥ 9.0

Location: `tests/gate/`

### 4. Judge/writer separation

The judge never talks to the writer. Communication is only through artifacts on disk. We test:
- **No direct channel:** static analysis of agent prompts to ensure no cross-agent conversation calls
- **Evidence citation:** every score in the evaluator output must cite a quoted line from the manuscript

Location: `tests/separation/`

### 5. Cross-agent portability

The pipeline is agent-agnostic. We spot-check on:
- Claude Code (canonical)
- Codex
- Kimi
- Antigravity

Location: `tests/portability/`, run manually before each release.

## What we don't test

- Literary quality of generated prose — that is a taste judgment, not a testable property
- Whether a book will sell — market outcomes are outside the pipeline's control
- Cost per book — instrumented in observability, not gated

## Test suite size (target for V5)

| Layer | Tests | Priority |
|-------|-------|----------|
| Agent prompt correctness | 16 (2 per agent) | must-have |
| Premise Forge | 12 | must-have |
| 8.5 Gate | 8 | must-have |
| Judge/writer separation | 4 (static) | must-have |
| Cross-agent portability | 4 (manual) | nice-to-have |
| **Total** | **44** | |

Current status: skeleton in place, populated as V5 lands.

## How to add a test

1. Pick the smallest failing scenario you can express as a brief + expected outcome
2. Add it to the appropriate `tests/` subfolder
3. Document the assertion in the test's README
4. Reference the test from the relevant agent's prompt when the agent's rule enforces that behavior
