from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.filesystem import (  # noqa: E402
    advance_phase,
    create_demo,
    current_phase,
    load_manifest,
    load_state_summary,
    prepare_agent_packet,
    prepare_phase,
    prepare_swarm_run,
    scaffold_project,
    state_get,
    state_set,
    validate_project,
)
from runner.gates import evaluate_gate, render_gate_report, run_check, write_gate_report  # noqa: E402
from runner.lint import lint_manuscript, render_report  # noqa: E402
from runner.styleprofile import (  # noqa: E402
    STYLE_PROFILE_FILENAME, render_style_profile, resolve_thresholds,
)
from runner.timeline import check_timeline_file, find_timeline, render_issues  # noqa: E402
from runner.corpus import build_baseline_report, render_baseline_report  # noqa: E402
from runner.discover import load_chapters, render_structure_report, resolve_chapters_dir  # noqa: E402
from runner.fingerprint import (  # noqa: E402
    build_profile as build_fingerprint_profile,
    compare as compare_fingerprints,
    load_library as load_fingerprint_library,
    render_report as render_fingerprint_report,
    save_profile as save_fingerprint_profile,
)
from runner.humanpass import (  # noqa: E402
    apply_plan, build_plan, render_apply_result, render_plan, status_manuscript,
)
from runner.ledger import MOTIF_BANK_NAME, build_ledger, render_ledger  # noqa: E402
from runner.macro import macro_manuscript, render_macro_report  # noqa: E402
from runner.proof import proof_manuscript, render_proof_report  # noqa: E402
from runner.texture import render_texture_report, texture_manuscript  # noqa: E402
from runner.voicelexicon import check_lexicon as check_voice_lexicon  # noqa: E402
from runner.voicelexicon import render_report as render_voice_lexicon_report  # noqa: E402
from runner.state_event import apply_event  # noqa: E402
from runner.reader_evidence import import_reader_evidence, render_evidence_report  # noqa: E402
from runner.adopt import adopt_manuscript, render_adoption_report  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="book-genesis")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a Book Genesis project tree")
    init_parser.add_argument("path")
    init_parser.add_argument("--idea", default="")
    init_parser.add_argument("--language", default="")
    init_parser.add_argument("--adapter", default="codex")
    init_parser.add_argument("--model", default="gpt-5.5")
    init_parser.add_argument("--force", action="store_true")

    status_parser = subparsers.add_parser("status", help="Print project status")
    status_parser.add_argument("path")

    validate_parser = subparsers.add_parser("validate", help="Validate required project files")
    validate_parser.add_argument("path")

    prepare_parser = subparsers.add_parser("prepare-phase", help="Write work/current-phase.md")
    prepare_parser.add_argument("path")

    advance_parser = subparsers.add_parser("advance-phase", help="Advance after required outputs exist")
    advance_parser.add_argument("path")
    advance_parser.add_argument(
        "--no-checks", action="store_true",
        help="Skip deterministic gate checks (recorded in PROJECT_STATE.yaml). Use only for debugging.")

    swarm_parser = subparsers.add_parser("prepare-swarm", help="Create a book-swarm run folder")
    swarm_parser.add_argument("path")
    swarm_parser.add_argument("--slug", default="reader-swarm")
    swarm_parser.add_argument("--mode", default="hybrid")

    agent_parser = subparsers.add_parser("prepare-agent-packet", help="Create a specialist agent packet")
    agent_parser.add_argument("path")
    agent_parser.add_argument("agent")

    demo_parser = subparsers.add_parser("demo", help="Create a deterministic mechanical demo")
    demo_parser.add_argument("path")
    demo_parser.add_argument("--adapter", default="codex")
    demo_parser.add_argument("--model", default="gpt-5.5")

    lint_parser = subparsers.add_parser("lint", help="Scan the manuscript for machine-prose patterns")
    lint_parser.add_argument("path", help="Project root or a chapters directory")
    lint_parser.add_argument("--profile", default="", help="literary | commercial | thriller")
    lint_parser.add_argument("--out", default="", help="Write the report to this path")
    lint_parser.add_argument(
        "--style-profile", default="",
        help="Path to a style-profile.yaml with per-project threshold overrides "
             "(default: auto-discover <project root>/style-profile.yaml)")

    tl_parser = subparsers.add_parser("check-timeline", help="Validate chronology arithmetic")
    tl_parser.add_argument("path", help="Project root or a TIMELINE file")
    tl_parser.add_argument("--out", default="", help="Write the report to this path")

    macro_parser = subparsers.add_parser(
        "macro", help="Book-level template check: chapter opening/closing modes, "
                       "scene-break uniformity, title parallelism (advisory)")
    macro_parser.add_argument("path", help="Project root or a chapters directory")
    macro_parser.add_argument("--out", default="", help="Write the report to this path")

    ledger_parser = subparsers.add_parser(
        "ledger", help="Build the retired-phrase ledger from finalized chapters "
                        "(default: <project root>/work/retired.md)")
    ledger_parser.add_argument("path", help="Project root or a chapters directory")
    ledger_parser.add_argument(
        "--out", default="", help="Write the report to this path instead of work/retired.md")

    texture_parser = subparsers.add_parser(
        "texture", help="Texture-bank coverage: which sourced details made it into "
                         "the manuscript, which are unsourced (advisory)")
    texture_parser.add_argument("path", help="Project root")
    texture_parser.add_argument(
        "--bank", default="", help="Path to texture-bank.md (default: <path>/research/texture-bank.md)")
    texture_parser.add_argument("--out", default="", help="Write the report to this path")

    hp_parser = subparsers.add_parser(
        "human-pass", help="Human pass: plan a worksheet of lines to hand-rewrite, "
                            "apply the rewrites, or check status")
    hp_parser.add_argument("action", choices=["plan", "apply", "status"])
    hp_parser.add_argument("path", help="Project root or a chapters directory")
    hp_parser.add_argument(
        "--out", default="",
        help="plan: write the worksheet here; apply: read the worksheet from here "
             "(default for both: <project root>/work/human-pass.md)")

    lexicon_parser = subparsers.add_parser(
        "voice-lexicon", help="Check attributed dialogue against each character's "
                               "never_say list in voice-lexicon.yaml (advisory)")
    lexicon_parser.add_argument("path", help="Project root or a chapters directory")
    lexicon_parser.add_argument(
        "--lexicon", default="", help="Path to voice-lexicon.yaml (default: <project root>/voice-lexicon.yaml)")
    lexicon_parser.add_argument("--out", default="", help="Write the report to this path")

    baseline_parser = subparsers.add_parser(
        "baseline", help="Compare this manuscript against the author's own writing "
                          "and suggest personal lint threshold overrides")
    baseline_parser.add_argument("path", help="Project root")
    baseline_parser.add_argument(
        "--corpus", required=True, help="Directory of the author's own .md/.txt writing")
    baseline_parser.add_argument("--profile", default="", help="literary | commercial | thriller")
    baseline_parser.add_argument(
        "--allow-loosen", action="store_true",
        help="Allow a derived override to be looser than the genre default (off by default)")
    baseline_parser.add_argument(
        "--out", default="", help="Write the report to this path (default: work/baseline-report.md)")

    fp_parser = subparsers.add_parser(
        "fingerprint", help="Stylometric fingerprint: save this manuscript to the "
                             "reference library, or compare it against the library")
    fp_parser.add_argument("action", choices=["save", "compare"])
    fp_parser.add_argument("path", help="Project root or a chapters directory")
    fp_parser.add_argument("--name", default="", help="save: label for this profile (default: project title)")
    fp_parser.add_argument(
        "--library-dir", default="", help="Override the fingerprint library directory "
                                           "(default: ~/.claude/book-genesis/fingerprints, "
                                           "or $BOOK_GENESIS_FINGERPRINT_DIR)")
    fp_parser.add_argument("--out", default="", help="compare: write the report to this path")

    st_parser = subparsers.add_parser(
        "structure", help="Character presence matrix and per-speaker dialogue metrics")
    st_parser.add_argument("path", help="Project root or a chapters directory")
    st_parser.add_argument("--names", default="", help="Comma-separated cast (default: auto-detect)")
    st_parser.add_argument("--out", default="", help="Write the report to this path")

    set_parser = subparsers.add_parser("set", help="Write a PROJECT_STATE.yaml value")
    set_parser.add_argument("path")
    set_parser.add_argument("key", help="Bare key (status) or block.key (project.autonomy)")
    set_parser.add_argument("value")
    set_parser.add_argument("--no-create", action="store_true", help="Fail if the key does not already exist")

    get_parser = subparsers.add_parser("get", help="Read a PROJECT_STATE.yaml value")
    get_parser.add_argument("path")
    get_parser.add_argument("key", help="Bare key (status) or block.key (project.autonomy)")

    proof_parser = subparsers.add_parser("proof", help="Scan the manuscript for typographic defects")
    proof_parser.add_argument("path", help="Project root or a chapters directory")
    proof_parser.add_argument("--out", default="", help="Write the report to this path")

    gate_parser = subparsers.add_parser("gate", help="Run the current (or named) phase's deterministic checks")
    gate_parser.add_argument("path")
    gate_parser.add_argument("--phase", default="", help="Phase label to evaluate (default: current phase)")
    gate_parser.add_argument("--out", default="", help="Write the report to this path (default: work/gate-report.md)")
    gate_parser.add_argument("--json", action="store_true", help="Print a JSON verdict instead of Markdown")

    check_parser = subparsers.add_parser(
        "check", help="Run one gates.CHECK_REGISTRY check standalone, without a manifest/phase. "
                       "For pipelines (e.g. book-orchestrator.md) that dispatch individual checks "
                       "directly instead of going through the codex manifest's `gate` command.")
    check_parser.add_argument("token", help="Check name, optionally with positional args: "
                                             "'lint', 'structure_variety', 'dynamic_range:0.01', 'wordcount:0.85:1.25'")
    check_parser.add_argument("path")

    event_parser = subparsers.add_parser(
        "apply-event", help="Guarded, validated write to STATE.yaml (book-genesis-full schema)")
    event_parser.add_argument("path")
    event_parser.add_argument("--type", dest="event_type", required=True, help="Event type (see EVENT_ALLOWLIST)")
    event_parser.add_argument("--note", required=True, help="One-line summary; becomes the commit message and a decisions[] entry")
    event_parser.add_argument("--phase", dest="expected_phase", default="", help="Expected phase.current; rejects as stale-phase on mismatch")
    event_parser.add_argument("--set", dest="sets", action="append", default=[], metavar="dotted.key=value",
                               help="Scalar overwrite, repeatable")
    event_parser.add_argument("--append", dest="appends", action="append", default=[], metavar="dotted.key={flow: mapping}",
                               help="Append a YAML flow-mapping list item, repeatable")
    event_parser.add_argument("--approved", action="store_true", help="Confirms human approval for gated event types")
    event_parser.add_argument("--no-git", action="store_true", help="Skip the Git commit checkpoint")
    event_parser.add_argument("--json", action="store_true", help="Print a JSON result instead of text")

    evidence_parser = subparsers.add_parser(
        "import-reader-evidence", help="Import real (human) beta-reader responses from CSV, distinct from simulated evaluation")
    evidence_parser.add_argument("path", help="Project root")
    evidence_parser.add_argument("csv", help="CSV file: reader_id,chapter,rating,comment,delayed")
    evidence_parser.add_argument("--experiment", default="RE-001", help="Reader-evidence experiment ID")
    evidence_parser.add_argument("--out", default="", help="Write the report to this path")

    adopt_parser = subparsers.add_parser(
        "adopt", help="Safely import an existing manuscript's chapters into a project")
    adopt_parser.add_argument("source", help="Directory of existing chapter files (.md/.txt)")
    adopt_parser.add_argument("path", help="Project root")
    adopt_parser.add_argument("--out", default="", help="Write the adoption report to this path")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    target = Path(args.path)

    if args.command == "init":
        scaffold_project(
            target,
            idea=args.idea,
            language=args.language,
            adapter=args.adapter,
            model_name=args.model,
            force=args.force,
        )
        print(f"Initialized project at {target}")
        return 0

    if args.command == "status":
        summary = load_state_summary(target)
        print(f"title={summary['title']}")
        print(f"adapter={summary['adapter']}")
        print(f"model_name={summary['model_name']}")
        print(f"current_phase={summary['current_phase']}")
        print(f"status={summary['status']}")
        return 0

    if args.command == "validate":
        result = validate_project(target)
        if not result["ok"]:
            print("Validation failed")
            for item in result["missing"]:
                print(item)
            return 1
        print("Validation ok")
        return 0

    if args.command == "prepare-phase":
        packet_path = prepare_phase(target)
        print(f"Prepared phase packet at {packet_path}")
        return 0

    if args.command == "advance-phase":
        result = advance_phase(target, skip_checks=args.no_checks)
        if not result["ok"]:
            print("Advance failed")
            for item in result["pending"]:
                print(item)
            for item in result.get("failed_checks", []):
                print(f"gate check failed: {item}")
            return 1
        print(f"Advanced to {result['next_phase']}")
        return 0

    if args.command == "prepare-swarm":
        run_dir = prepare_swarm_run(target, slug=args.slug, mode=args.mode)
        print(f"Prepared book-swarm run at {run_dir}")
        return 0

    if args.command == "prepare-agent-packet":
        packet_path = prepare_agent_packet(target, args.agent)
        print(f"Prepared agent packet at {packet_path}")
        return 0

    if args.command == "demo":
        create_demo(target, adapter=args.adapter, model_name=args.model)
        print(f"Created completed mechanical demo at {target}")
        return 0

    if args.command == "lint":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        if args.style_profile:
            style_profile_path = Path(args.style_profile)
        else:
            # target may already BE the chapters dir (resolve_chapters_dir's
            # other branch) -- walk back up to the project root for
            # auto-discovery: chapters -> manuscript -> root.
            project_root = target.parent.parent if target.name == "chapters" else target
            style_profile_path = project_root / STYLE_PROFILE_FILENAME
        thresholds, style_warnings = resolve_thresholds(
            profile=args.profile, style_profile_path=style_profile_path)
        for warning in style_warnings:
            print(f"warning: {warning}")
        report = lint_manuscript(chapters, profile=args.profile, thresholds=thresholds)
        text = render_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote lint report to {args.out}")
        print(text)
        return 1 if report.failed else 0

    if args.command == "check-timeline":
        tl_path = target if target.is_file() else find_timeline(target)
        if tl_path is None:
            print(f"No TIMELINE file found under {target}")
            return 2
        timeline, issues = check_timeline_file(tl_path)
        text = render_issues(timeline, issues)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote chronology report to {args.out}")
        print(text)
        return 1 if any(i.severity == "fail" for i in issues) else 0

    if args.command == "macro":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        report = macro_manuscript(chapters)
        text = render_macro_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote macro-structure report to {args.out}")
        print(text)
        # Advisory by design (see gates.ADVISORY_CHECKS) -- exit 1 flags
        # findings for a human or CI log to notice, but the gate this backs
        # never blocks advance_phase on this command's result.
        if report.skipped:
            return 0
        return 1 if report.findings else 0

    if args.command == "ledger":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        project_root = target.parent.parent if target.name == "chapters" else target
        # foundation/motifs.md is an optional overlay, same contract as
        # research/texture-bank.md -- absent is the normal case, a no-op.
        motif_bank_path = project_root / MOTIF_BANK_NAME
        # The self-report for chapter-N.md (chapter-N-report.md) is written
        # to the same directory as the chapter itself -- always true of the
        # chapters dir regardless of which form `target` was given as.
        report = build_ledger(chapters, report_dir=chapters, motif_bank_path=motif_bank_path)
        text = render_ledger(report)
        if args.out:
            out_path = Path(args.out)
        else:
            out_path = project_root / "work" / "retired.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote retired-phrase ledger to {out_path}")
        print(text)
        return 0

    if args.command == "texture":
        bank_path = Path(args.bank) if args.bank else target / "research" / "texture-bank.md"
        chapters = resolve_chapters_dir(target)
        report = texture_manuscript(bank_path, chapters)
        text = render_texture_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote texture report to {args.out}")
        print(text)
        if report.skipped:
            return 0
        return 1 if report.failed else 0

    if args.command == "human-pass":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        project_root = target.parent.parent if target.name == "chapters" else target
        worksheet_path = Path(args.out) if args.out else project_root / "work" / "human-pass.md"

        if args.action == "plan":
            plan = build_plan(chapters)
            text = render_plan(plan)
            worksheet_path.parent.mkdir(parents=True, exist_ok=True)
            worksheet_path.write_text(text, encoding="utf-8")
            print(f"Wrote human-pass worksheet to {worksheet_path}")
            print(text)
            return 0

        if args.action == "apply":
            if not worksheet_path.is_file():
                print(f"No worksheet at {worksheet_path} -- run `human-pass plan` first")
                return 2
            result = apply_plan(chapters, worksheet_path.read_text(encoding="utf-8"))
            print(render_apply_result(result))
            return 1 if (result.rejected_chapters or result.parse_errors) else 0

        # args.action == "status"
        counts = status_manuscript(chapters)
        if not counts:
            print("No finalized chapters.")
            return 0
        for name in sorted(counts):
            print(f"{name}: {counts[name]} protected span(s)")
        return 0

    if args.command == "voice-lexicon":
        lexicon_path = Path(args.lexicon) if args.lexicon else (
            (target.parent.parent if target.name == "chapters" else target) / "voice-lexicon.yaml")
        chapters = resolve_chapters_dir(target)
        report = check_voice_lexicon(lexicon_path, chapters)
        text = render_voice_lexicon_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote voice lexicon report to {args.out}")
        print(text)
        if report.skipped:
            return 0
        return 1 if report.violations else 0

    if args.command == "baseline":
        corpus_dir = Path(args.corpus)
        chapters = resolve_chapters_dir(target)
        manuscript_dir = chapters if chapters.is_dir() else None
        report = build_baseline_report(
            corpus_dir, manuscript_dir, profile=args.profile,
            allow_loosen=args.allow_loosen)
        text = render_baseline_report(report)

        out_path = Path(args.out) if args.out else target / "work" / "baseline-report.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote baseline report to {out_path}")
        print(text)

        if report.derived_overrides:
            suggested_path = target / "style-profile.suggested.yaml"
            suggested_path.write_text(
                render_style_profile(report.derived_overrides), encoding="utf-8")
            print(f"\nWrote {suggested_path} -- review it, then copy/rename to "
                  "style-profile.yaml to activate. Never applied automatically.")
        return 0 if not report.skipped else 2

    if args.command == "fingerprint":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        texts = load_chapters(chapters)
        joined = "\n\n".join(texts.values())
        library_dir = Path(args.library_dir) if args.library_dir else None

        if args.action == "save":
            name = args.name or target.name
            profile = build_fingerprint_profile(name, joined)
            path = save_fingerprint_profile(profile, library_dir=library_dir)
            print(f"Saved fingerprint profile {name!r} to {path}")
            return 0

        # args.action == "compare"
        name = args.name or target.name
        target_profile = build_fingerprint_profile(name, joined)
        references = load_fingerprint_library(library_dir)
        report = compare_fingerprints(target_profile, references)
        text = render_fingerprint_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote fingerprint report to {args.out}")
        print(text)
        return 0

    if args.command == "structure":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        texts = load_chapters(chapters)
        if not texts:
            print(f"No chapter files in {chapters}")
            return 2
        names = [n.strip() for n in args.names.split(",") if n.strip()] or None
        text = render_structure_report(texts, names)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote structure report to {args.out}")
        print(text)
        return 0

    if args.command == "proof":
        chapters = resolve_chapters_dir(target)
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        report = proof_manuscript(chapters)
        text = render_proof_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Wrote proof report to {args.out}")
        print(text)
        return 1 if report.failed else 0

    if args.command == "set":
        try:
            state_set(target, args.key, args.value, create=not args.no_create)
        except KeyError as exc:
            print(str(exc))
            return 1
        print(f"{args.key}={args.value}")
        return 0

    if args.command == "get":
        value = state_get(target, args.key)
        print(value)
        return 0

    if args.command == "gate":
        if args.phase:
            phase = next((p for p in load_manifest() if p.label == args.phase), None)
            if phase is None:
                print(f"Unknown phase: {args.phase}")
                return 2
        else:
            phase = current_phase(target)
        verdict = evaluate_gate(target, phase)
        report_path = Path(args.out) if args.out else write_gate_report(target, verdict)
        if args.out:
            Path(args.out).write_text(render_gate_report(verdict), encoding="utf-8")
        if args.json:
            import json as _json
            print(_json.dumps({
                "phase_label": verdict.phase_label,
                "gate": verdict.gate,
                "ok": verdict.ok,
                "pending_outputs": verdict.pending_outputs,
                "results": [
                    {
                        "name": r.name, "status": r.status, "summary": r.summary,
                        "advisory": r.advisory,
                    }
                    for r in verdict.results
                ],
            }, indent=2))
        else:
            print(render_gate_report(verdict))
            print(f"\nReport written to {report_path}")
        return 0 if verdict.ok else 1

    if args.command == "check":
        result = run_check(target, args.token)
        marker = " (advisory)" if result.advisory else ""
        print(f"{result.name}: {result.status.upper()}{marker} -- {result.summary}")
        if result.detail:
            print()
            print(result.detail)
        if result.status in ("fail", "error") and not result.advisory:
            return 1
        return 0

    if args.command == "apply-event":
        def _split_kv(items: list[str]) -> list[tuple[str, str]]:
            pairs = []
            for item in items:
                if "=" not in item:
                    print(f"malformed --set/--append (expected key=value): {item}")
                    raise SystemExit(2)
                key, _, value = item.partition("=")
                pairs.append((key, value))
            return pairs

        result = apply_event(
            target,
            event_type=args.event_type,
            note=args.note,
            expected_phase=args.expected_phase,
            sets=_split_kv(args.sets),
            appends=_split_kv(args.appends),
            approved=args.approved,
            use_git=not args.no_git,
        )
        if args.json:
            import json as _json
            print(_json.dumps(result.as_dict(), indent=2))
        else:
            print(f"{'OK' if result.ok else 'REJECTED'}: {result.code} — {result.message}")
            if result.commit:
                print(f"commit: {result.commit}")
        return 0 if result.ok else 1

    if args.command == "import-reader-evidence":
        report = import_reader_evidence(target, Path(args.csv), experiment_id=args.experiment)
        text = render_evidence_report(report)
        out_path = Path(args.out) if args.out else target / "feedback" / "beta-readers" / f"{args.experiment}-report.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(text)
        print(f"\nWrote reader-evidence report to {out_path}")
        return 1 if report.rejected_rows else 0

    if args.command == "adopt":
        report = adopt_manuscript(Path(args.source), target)
        text = render_adoption_report(report)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        print(text)
        return 1 if report.rejected else 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
