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
from runner.gates import evaluate_gate, render_gate_report, write_gate_report  # noqa: E402
from runner.lint import lint_manuscript, render_report  # noqa: E402
from runner.timeline import check_timeline_file, find_timeline, render_issues  # noqa: E402
from runner.discover import load_chapters, render_structure_report  # noqa: E402
from runner.proof import proof_manuscript, render_proof_report  # noqa: E402


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

    tl_parser = subparsers.add_parser("check-timeline", help="Validate chronology arithmetic")
    tl_parser.add_argument("path", help="Project root or a TIMELINE file")
    tl_parser.add_argument("--out", default="", help="Write the report to this path")

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
        chapters = target if target.name == "chapters" else target / "manuscript" / "chapters"
        if not chapters.is_dir():
            print(f"No chapters directory at {chapters}")
            return 2
        report = lint_manuscript(chapters, profile=args.profile)
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

    if args.command == "structure":
        chapters = target if target.name == "chapters" else target / "manuscript" / "chapters"
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
        chapters = target if target.name == "chapters" else target / "manuscript" / "chapters"
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
                    {"name": r.name, "status": r.status, "summary": r.summary}
                    for r in verdict.results
                ],
            }, indent=2))
        else:
            print(render_gate_report(verdict))
            print(f"\nReport written to {report_path}")
        return 0 if verdict.ok else 1

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
