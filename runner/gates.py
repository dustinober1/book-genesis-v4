"""Code-enforced quality gates.

The pipeline prompts (``references/prompts/orchestrator.md`` and friends)
declare hard gates — chronology must pass, lint must pass — and say a hard
gate failure halts the pipeline "at every autonomy level, including auto".
Historically that was aspirational: ``filesystem.advance_phase`` only ever
checked that declared output files existed and were non-empty. An agent
could report "gates: passed" on a manuscript nobody ever ran lint or
chronology check against.

This module is what makes the gates real. A phase's manifest entry can
declare a ``checks:`` list; ``evaluate_gate`` runs each named check against
the project and returns a verdict that ``advance_phase`` obeys.

Each check token is a colon-delimited string, e.g. ``"lint"`` or
``"wordcount:0.85:1.25"``. An unrecognized token is an *error*, not a
silent skip — a typo in the manifest must not quietly disable a gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Callable, Dict, List, Set

from runner import discover, lint, proof, timeline

CheckFn = Callable[[Path, List[str]], "CheckResult"]

# Checks whose thresholds are new or not yet calibrated against real
# manuscripts. They run on every gate and report their true status, but a
# fail/error here never blocks `GateVerdict.ok` -- so `advance_phase` still
# advances and the check stays *visible* instead of silently disabled.
# Promotion to a real, blocking gate is deleting the name from this set.
#
# Do not "fix" a fail-here by downgrading the result's status to pass inside
# run_check: that would print PASS in the gate table and in --json, which
# hides the finding instead of flagging it. advisory=True is what keeps the
# real status visible while keeping it non-blocking.
#
# "macro" (runner/macro.py): book-level template detection -- chapter
# opening/closing mode share, scene-break uniformity, title parallelism.
# "texture" (runner/texture.py): texture-bank source/coverage checks.
# "voice_lexicon" (runner/voicelexicon.py): never_say checks against
# attributed dialogue -- a real hit is a real problem, but the underlying
# speaker-attribution primitive (discover.dialogue_by_speaker) has known
# false-negative cases (see its docstring), so a clean run here is not yet
# trustworthy enough to block on.
# None of these three are calibrated against a real corpus yet.
ADVISORY_CHECKS: Set[str] = {"macro", "texture", "voice_lexicon"}


@dataclass
class CheckResult:
    name: str
    status: str  # "pass" | "fail" | "skip" | "error"
    summary: str
    detail: str = ""
    report_path: str = ""
    advisory: bool = False


@dataclass
class GateVerdict:
    phase_label: str
    gate: str
    pending_outputs: List[str] = field(default_factory=list)
    results: List[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.pending_outputs:
            return False
        return not any(
            r.status in ("fail", "error") and not r.advisory for r in self.results)

    @property
    def blocking(self) -> List[CheckResult]:
        return [
            r for r in self.results
            if r.status in ("fail", "error") and not r.advisory
        ]

    @property
    def advisory_flagged(self) -> List[CheckResult]:
        """Advisory checks that failed or errored -- visible, not blocking."""
        return [
            r for r in self.results
            if r.status in ("fail", "error") and r.advisory
        ]


# --------------------------------------------------------------------------
# Individual checks
# --------------------------------------------------------------------------

def _chapters_dir(target: Path) -> Path:
    return target / "manuscript" / "chapters"


def check_timeline_check(target: Path, args: List[str]) -> CheckResult:
    required = "required" in args
    tl_path = timeline.find_timeline(target)
    if tl_path is None:
        if required:
            return CheckResult(
                "timeline", "fail", "no TIMELINE file found",
                "Expected TIMELINE.md, TIMELINE.txt, or artifacts/TIMELINE.md.",
            )
        return CheckResult("timeline", "skip", "no TIMELINE file present")

    tl, issues = timeline.check_timeline_file(tl_path)
    fails = [i for i in issues if i.severity == "fail"]
    report = timeline.render_issues(tl, issues)
    if fails:
        return CheckResult(
            "timeline", "fail",
            f"{len(fails)} chronology contradiction(s)", report,
        )
    return CheckResult("timeline", "pass", "chronology consistent", report)


def check_lint_check(target: Path, args: List[str]) -> CheckResult:
    from runner.filesystem import state_get  # local import: avoid a cycle
    from runner.styleprofile import STYLE_PROFILE_FILENAME, resolve_thresholds  # local import: avoid a cycle

    chapters = _chapters_dir(target)
    if not chapters.is_dir() or not any(chapters.glob("*.md")):
        return CheckResult("lint", "skip", "no chapters to lint")

    profile = args[0] if args else ""
    if not profile:
        profile = (
            state_get(target, "project.lint_profile")
            or state_get(target, "project.subgenre")
            or state_get(target, "project.genre")
        )
    # Honor the same personal style-profile.yaml the `lint` CLI command
    # uses, so the gate that actually blocks advance_phase doesn't diverge
    # from what a manual `python3 runner/cli.py lint` reports.
    thresholds, style_warnings = resolve_thresholds(
        profile=profile, style_profile_path=target / STYLE_PROFILE_FILENAME)
    report = lint.lint_manuscript(chapters, profile=profile, thresholds=thresholds)
    text = "\n".join(f"warning: {w}" for w in style_warnings)
    text += ("\n\n" if text else "") + lint.render_report(report)
    if report.failed:
        fails = [f for f in report.findings if f.severity == "fail"]
        return CheckResult(
            "lint", "fail", f"{len(fails)} lint failure(s) (profile={profile or 'default'})", text,
        )
    return CheckResult("lint", "pass", f"lint clean (profile={profile or 'default'})", text)


def check_chapter_order(target: Path, args: List[str]) -> CheckResult:
    chapters = _chapters_dir(target)
    files = sorted(p for p in chapters.glob("*.md") if p.is_file()) if chapters.is_dir() else []
    if not files:
        return CheckResult("chapter_order", "skip", "no chapters to check")

    numbers: List[int] = []
    problems: List[str] = []
    for p in files:
        m = re.search(r"(\d+)", p.stem)
        if not m:
            problems.append(f"{p.name}: no chapter number in filename")
            continue
        numbers.append(int(m.group(1)))

    if problems:
        return CheckResult("chapter_order", "fail", f"{len(problems)} filename issue(s)", "\n".join(problems))

    gaps = []
    for i in range(1, len(numbers)):
        if numbers[i] <= numbers[i - 1]:
            gaps.append(f"{files[i].name} (#{numbers[i]}) does not follow {files[i-1].name} (#{numbers[i-1]})")
    if gaps:
        return CheckResult("chapter_order", "fail", f"{len(gaps)} ordering issue(s)", "\n".join(gaps))
    return CheckResult("chapter_order", "pass", f"{len(files)} chapters in order")


def check_wordcount(target: Path, args: List[str]) -> CheckResult:
    from runner.filesystem import state_get_int  # local import: avoid a cycle

    min_mult = float(args[0]) if len(args) > 0 and args[0] else 0.85
    max_mult = float(args[1]) if len(args) > 1 and args[1] else 1.25

    target_words = state_get_int(target, "project.word_count_target", default=0)
    if target_words <= 0:
        return CheckResult("wordcount", "skip", "no word_count_target set")

    chapters = _chapters_dir(target)
    if not chapters.is_dir():
        return CheckResult("wordcount", "skip", "no chapters directory")
    texts = discover.load_chapters(chapters)
    # Editorial comments are not prose and must not count toward the target.
    total = sum(
        len(discover.WORD.findall(discover.strip_comments(t)))
        for t in texts.values()
    )

    lo, hi = target_words * min_mult, target_words * max_mult
    if not (lo <= total <= hi):
        return CheckResult(
            "wordcount", "fail",
            f"{total:,} words vs target {target_words:,} "
            f"(expected {lo:,.0f}-{hi:,.0f})",
        )
    return CheckResult("wordcount", "pass", f"{total:,} words (target {target_words:,})")


def check_proof(target: Path, args: List[str]) -> CheckResult:
    chapters = _chapters_dir(target)
    if not chapters.is_dir() or not any(chapters.glob("*.md")):
        return CheckResult("proof", "skip", "no chapters to proof")
    report = proof.proof_manuscript(chapters)
    text = proof.render_proof_report(report)
    if report.failed:
        fails = [i for i in report.issues if i.severity == "fail"]
        return CheckResult("proof", "fail", f"{len(fails)} typographic defect(s)", text)
    return CheckResult("proof", "pass", "no typographic defects", text)


def check_macro(target: Path, args: List[str]) -> CheckResult:
    from runner import macro  # local import: avoid a cycle
    from runner.filesystem import state_get  # local import: avoid a cycle

    chapters = _chapters_dir(target)
    if not chapters.is_dir() or not any(chapters.glob("*.md")):
        return CheckResult("macro", "skip", "no chapters to analyze")
    language = state_get(target, "project.language").strip().lower()
    if language and not language.startswith("en"):
        # MAXIM_MARKERS/CONCRETE_MARKERS (imported from lint.py) and the
        # dialogue-quote-character classification are English-word and
        # Latin-quote-convention heuristics; running them against another
        # language's prose would silently mismeasure it rather than say so.
        return CheckResult(
            "macro", "skip", f"language={language!r} -- macro's heuristics are English-only")
    report = macro.macro_manuscript(chapters)
    if report.skipped:
        return CheckResult("macro", "skip", report.skipped)
    text = macro.render_macro_report(report)
    if report.findings:
        # Every finding this module produces is internally "warn" severity
        # (see macro.py's docstring): none of these thresholds are
        # calibrated yet, so this check is registered in ADVISORY_CHECKS
        # below and never blocks GateVerdict.ok regardless of this status.
        # "fail" here means "worth a human's attention", not "broken".
        return CheckResult(
            "macro", "fail", f"{len(report.findings)} macro-structure pattern(s) flagged", text)
    return CheckResult("macro", "pass", "no macro-structure patterns flagged", text)


def check_texture(target: Path, args: List[str]) -> CheckResult:
    from runner import texture  # local import: avoid a cycle

    bank_path = target / texture.TEXTURE_BANK_NAME
    if not bank_path.is_file():
        # No bank is the normal case for a project that hasn't run a
        # texture-research pass -- not a defect, unlike an unparsable one.
        return CheckResult("texture", "skip", "no texture bank at research/texture-bank.md")
    chapters = _chapters_dir(target)
    report = texture.texture_manuscript(bank_path, chapters)
    text = texture.render_texture_report(report)
    if report.failed:
        fails = [f for f in report.findings if f.severity == "fail"]
        return CheckResult("texture", "fail", f"{len(fails)} texture-bank parse error(s)", text)
    if report.findings:
        # Coverage/src findings are all "warn" severity internally -- see
        # texture.py's docstring -- but this check is registered in
        # ADVISORY_CHECKS below regardless, same reasoning as "macro".
        return CheckResult(
            "texture", "fail", f"{len(report.findings)} texture-bank finding(s) flagged", text)
    return CheckResult("texture", "pass", "texture bank clean", text)


def check_human_pass(target: Path, args: List[str]) -> CheckResult:
    from runner.filesystem import state_get  # local import: avoid a cycle

    chapters = _chapters_dir(target)
    if not chapters.is_dir() or not any(chapters.glob("*.md")):
        return CheckResult("human_pass", "skip", "no chapters yet")

    if state_get(target, "project.skip_human_pass").strip().lower() in ("true", "1", "yes"):
        return CheckResult(
            "human_pass", "pass",
            "human pass explicitly skipped (project.skip_human_pass=true)")

    worksheet = target / "work" / "human-pass.md"
    if not worksheet.is_file():
        return CheckResult(
            "human_pass", "fail",
            "no work/human-pass.md",
            "Run `python3 runner/cli.py human-pass plan <project>` and hand-rewrite "
            "at least the lines you want protected, then `human-pass apply`. Or set "
            "project.skip_human_pass=true to opt out (e.g. a mechanical demo with no "
            "human in the loop).\n\n"
            "This check verifies the worksheet was generated, not that a human "
            "reviewed it -- that judgment belongs to the delivery checkpoint, not to "
            "a deterministic check.",
        )
    return CheckResult("human_pass", "pass", "human-pass worksheet exists")


def check_voice_lexicon(target: Path, args: List[str]) -> CheckResult:
    from runner import voicelexicon  # local import: avoid a cycle

    lexicon_path = target / voicelexicon.VOICE_LEXICON_NAME
    chapters = _chapters_dir(target)
    report = voicelexicon.check_lexicon(lexicon_path, chapters)
    if report.skipped:
        return CheckResult("voice_lexicon", "skip", report.skipped)
    text = voicelexicon.render_report(report)
    if report.violations:
        return CheckResult(
            "voice_lexicon", "fail",
            f"{len(report.violations)} never_say violation(s)", text)
    return CheckResult("voice_lexicon", "pass", "no never_say violations", text)


def check_book_meta(target: Path, args: List[str]) -> CheckResult:
    from runner import compile as _compile  # local import: avoid a cycle

    meta = _compile.load_book_meta(target)
    problems = _compile.validate_book_meta(meta)
    if problems:
        return CheckResult("book_meta", "fail", f"{len(problems)} issue(s)", "\n".join(problems))
    return CheckResult("book_meta", "pass", f'"{meta.title}" by {meta.author}')


def check_epub(target: Path, args: List[str]) -> CheckResult:
    from runner import compile as _compile  # local import: avoid a cycle

    meta = _compile.load_book_meta(target)
    try:
        epub_path = _compile.build_epub(target, meta)
    except _compile.CompileError as exc:
        return CheckResult("epub", "fail", str(exc))
    problems = _compile.validate_epub(epub_path)
    if problems:
        return CheckResult("epub", "fail", f"{len(problems)} structural issue(s)", "\n".join(problems))
    return CheckResult("epub", "pass", f"valid EPUB at {epub_path}")


CHECK_REGISTRY: Dict[str, CheckFn] = {
    "timeline": check_timeline_check,
    "lint": check_lint_check,
    "chapter_order": check_chapter_order,
    "wordcount": check_wordcount,
    "proof": check_proof,
    "book_meta": check_book_meta,
    "epub": check_epub,
    "macro": check_macro,
    "texture": check_texture,
    "human_pass": check_human_pass,
    "voice_lexicon": check_voice_lexicon,
}


def run_check(target: Path, token: str) -> CheckResult:
    parts = token.split(":")
    name, args = parts[0], parts[1:]
    fn = CHECK_REGISTRY.get(name)
    if fn is None:
        # An unknown token is deliberately NOT advisory, even if `name`
        # happens to collide with an ADVISORY_CHECKS entry -- a manifest typo
        # must still be visible as an error, not silently swallowed twice
        # over.
        return CheckResult(
            name, "error", f"unknown check {name!r}",
            f"Registered checks: {', '.join(sorted(CHECK_REGISTRY))}. "
            "A manifest typo must not silently disable a gate.",
        )
    advisory = name in ADVISORY_CHECKS
    try:
        result = fn(target, args)
    except Exception as exc:  # noqa: BLE001 - a check crashing must block, not vanish
        # Covers ADVISORY_CHECKS too: an uncalibrated new module that raises
        # on real prose must not hard-block the pipeline either.
        return CheckResult(
            name, "error", f"check raised {type(exc).__name__}: {exc}",
            advisory=advisory)
    result.advisory = advisory
    return result


def run_phase_checks(target: Path, checks: List[str]) -> List[CheckResult]:
    return [run_check(target, token) for token in checks]


def evaluate_gate(target: Path, phase=None) -> GateVerdict:
    from runner.filesystem import current_phase, pending_outputs  # local import: avoid a cycle

    phase = phase or current_phase(target)
    pending = pending_outputs(target, phase.outputs)
    results = [] if pending else run_phase_checks(target, getattr(phase, "checks", []))
    return GateVerdict(
        phase_label=phase.label, gate=phase.gate,
        pending_outputs=pending, results=results,
    )


def render_gate_report(verdict: GateVerdict) -> str:
    lines = [f"# Gate Report — {verdict.phase_label}", ""]
    lines.append(f"**Verdict: {'PASS' if verdict.ok else 'FAIL'}**")
    lines.append("")

    if verdict.pending_outputs:
        lines.append("## Pending Outputs")
        for item in verdict.pending_outputs:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("Checks did not run — required outputs are missing or unfilled.")
        return "\n".join(lines)

    if not verdict.results:
        lines.append("No checks declared for this phase.")
        return "\n".join(lines)

    lines.append("| Check | Status | Summary |")
    lines.append("|---|---|---|")
    for r in verdict.results:
        marker = " (advisory)" if r.advisory else ""
        lines.append(f"| {r.name} | {r.status.upper()}{marker} | {r.summary} |")
    lines.append("")

    if verdict.advisory_flagged:
        lines.append(
            "**Advisory checks flagged (not blocking):** "
            + ", ".join(f"{r.name} ({r.status})" for r in verdict.advisory_flagged))
        lines.append("")

    for r in verdict.results:
        if not r.detail:
            continue
        lines.append(f"## {r.name}")
        lines.append("")
        lines.append(r.detail)
        lines.append("")

    return "\n".join(lines)


def write_gate_report(target: Path, verdict: GateVerdict) -> Path:
    work_dir = target / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "gate-report.md"
    path.write_text(render_gate_report(verdict), encoding="utf-8")
    return path
