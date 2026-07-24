from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import json
from pathlib import Path
from typing import Dict, List

from runner import paths as _paths


@dataclass(frozen=True)
class Phase:
    key: str
    label: str
    prompt: str
    gate: str
    outputs: List[str]
    next: str
    checks: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class AgentSpec:
    key: str
    label: str
    skill: str
    mission: str
    timing: str
    inputs: List[str]
    outputs: List[str]
    gates: List[str]
    score_floor: str


ARTIFACT_HEADINGS: Dict[str, str] = {
    "00-brief.md": "Brief",
    "01-market-map.md": "Market Map",
    "02-story-engine.md": "Story Engine",
    "03-characters.md": "Characters",
    "04-theme.md": "Theme",
    "05-outline.md": "Outline",
    "06-emotional-curve.md": "Emotional Curve",
    "07-opening-strategy.md": "Opening Strategy",
    "08-adversarial-audit.md": "Adversarial Audit",
    "09-genesis-score-codex.md": "Genesis Score",
    "10-editorial-package.md": "Editorial Package",
}

def load_manifest() -> List[Phase]:
    entries = _load_simple_yaml_map(_paths.manifest_path())
    return [
        Phase(
            key=key,
            label=str(entry.get("label", "")),
            prompt=str(entry.get("prompt", "")),
            gate=str(entry.get("gate", "")),
            outputs=list(entry.get("outputs", [])),
            next=str(entry.get("next", "")),
            checks=list(entry.get("checks", [])),
        )
        for key, entry in entries.items()
    ]


def load_agent_registry() -> List[AgentSpec]:
    entries = _load_simple_yaml_map(_paths.agent_registry_path())
    return [
        AgentSpec(
            key=key,
            label=str(entry.get("label", "")),
            skill=str(entry.get("skill", "")),
            mission=str(entry.get("mission", "")),
            timing=str(entry.get("timing", "")),
            inputs=list(entry.get("inputs", [])),
            outputs=list(entry.get("outputs", [])),
            gates=list(entry.get("gates", [])),
            score_floor=str(entry.get("score_floor", "")),
        )
        for key, entry in entries.items()
    ]


def get_agent_spec(agent_key: str) -> AgentSpec:
    normalized = _slugify(agent_key).replace("-", "_")
    for agent in load_agent_registry():
        if agent.key == agent_key or agent.key == normalized or _slugify(agent.label) == _slugify(agent_key):
            return agent
    available = ", ".join(agent.key for agent in load_agent_registry())
    raise KeyError(f"Unknown agent {agent_key!r}. Available agents: {available}")


def scaffold_project(
    target: Path,
    *,
    idea: str,
    adapter: str,
    model_name: str,
    language: str = "",
    force: bool = False,
) -> None:
    if (target / "PROJECT_STATE.yaml").exists() and not force:
        raise FileExistsError(f"{target} already contains PROJECT_STATE.yaml")

    phases = load_manifest()
    first_phase = phases[0]
    gates = "\n".join(f'  {phase.gate}: "pending"' for phase in phases)

    target.mkdir(parents=True, exist_ok=True)
    (target / "artifacts").mkdir(exist_ok=True)
    (target / "manuscript" / "chapters").mkdir(parents=True, exist_ok=True)
    (target / "evaluations").mkdir(exist_ok=True)
    (target / "delivery").mkdir(exist_ok=True)
    (target / "work").mkdir(exist_ok=True)

    write_if_needed(
        target / "PROJECT_STATE.yaml",
        _project_state_template(
            idea=idea,
            adapter=adapter,
            model_name=model_name,
            language=language,
            first_phase=first_phase.label,
            gates=gates,
        ),
        force=force,
    )
    write_if_needed(target / "ASSUMPTIONS.md", assumptions_template(idea), force=force)
    write_if_needed(target / "RUN_REPORT.md", run_report_template(), force=force)

    for phase in phases:
        for output in phase.outputs:
            path = target / output
            if output.startswith("artifacts/"):
                write_if_needed(path, artifact_template(Path(output).name), force=force)
            elif output == "BOOK.yaml":
                from runner.compile import book_meta_template  # local import: avoid a cycle
                write_if_needed(path, book_meta_template(), force=force)
            elif output.endswith(".md") and "/" in output:
                # e.g. manuscript/full-manuscript.md, delivery/production/*.md
                # -- non-artifact file outputs that still need a template
                # stub so pending_outputs() has something to check.
                write_if_needed(path, artifact_template(Path(output).name), force=force)


def validate_project(target: Path) -> Dict[str, object]:
    required = [
        target / "PROJECT_STATE.yaml",
        target / "ASSUMPTIONS.md",
        target / "RUN_REPORT.md",
        target / "artifacts",
        target / "manuscript" / "chapters",
        target / "evaluations",
        target / "delivery",
    ]
    missing = [str(path) for path in required if not path.exists()]
    return {"ok": not missing, "missing": missing}


def load_state_summary(target: Path) -> Dict[str, str]:
    text = (target / "PROJECT_STATE.yaml").read_text(encoding="utf-8")
    return {
        "title": _extract_scalar(text, "title"),
        "adapter": _extract_scalar(text, "adapter"),
        "model_name": _extract_scalar(text, "model_name"),
        "current_phase": _extract_scalar(text, "current_phase"),
        "status": _extract_scalar(text, "status"),
    }


def prepare_phase(target: Path) -> Path:
    phase = current_phase(target)
    prompt_path = _paths.skill_root() / phase.prompt
    prompt_text = prompt_path.read_text(encoding="utf-8")
    output_list = "\n".join(f"- {item}" for item in phase.outputs)

    packet = (
        f"# Current Phase\n\n"
        f"- Label: {phase.label}\n"
        f"- Gate: {phase.gate}\n"
        f"- Prompt: {phase.prompt}\n"
        f"- Required outputs:\n{output_list}\n\n"
        f"## Phase Prompt\n\n"
        f"{prompt_text.rstrip()}\n"
    )

    work_dir = target / "work"
    work_dir.mkdir(exist_ok=True)
    packet_path = work_dir / "current-phase.md"
    packet_path.write_text(packet, encoding="utf-8")
    _update_state_value(target / "PROJECT_STATE.yaml", "current_gate", phase.gate)
    _update_state_value(target / "PROJECT_STATE.yaml", "status", "in_progress")
    return packet_path


def prepare_swarm_run(
    target: Path,
    *,
    slug: str = "reader-swarm",
    mode: str = "hybrid",
    run_date: str = "",
) -> Path:
    run_slug = _slugify(slug or mode or "reader-swarm")
    run_id = f"{run_date or date.today().isoformat()}-{run_slug}"
    run_dir = target / "evaluations" / "book-swarm" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    chapters_dir = target / "manuscript" / "chapters"
    chapters = sorted(chapters_dir.glob("*.md")) if chapters_dir.exists() else []
    chapter_lines = "\n".join(f"- `{chapter.relative_to(target).as_posix()}`" for chapter in chapters)
    if not chapter_lines:
        chapter_lines = "- No chapter files found yet."

    files = {
        "persona-roster.json": json.dumps(
            {
                "mode": mode,
                "run_slug": run_slug,
                "personas": [],
                "note": "Fill with fictional diagnostic personas before running cohort reports.",
            },
            indent=2,
        )
        + "\n",
        "sample-map.md": (
            "# Sample Map\n\n"
            f"- Mode: `{mode}`\n"
            f"- Run slug: `{run_slug}`\n\n"
            "## Available Manuscript Files\n\n"
            f"{chapter_lines}\n\n"
            "## Required Coverage\n\n"
            "- First chapter\n"
            "- Final chapter if available\n"
            "- Climax or strongest tension sample\n"
            "- Weakest flagged chapters\n"
            "- Strongest flagged chapters\n"
        ),
        "cohort-reports.md": swarm_template("Cohort Reports"),
        "interviews.md": swarm_template("Interviews"),
        "public-opinion-report.md": swarm_template("Public Opinion Report"),
        "risk-heatmap.md": (
            "# Risk Heatmap\n\n"
            "| Area | Chapter/Asset | Cohort | Severity | Evidence | Fix Type | Owner |\n"
            "|---|---|---|---|---|---|---|\n"
        ),
        "revision-tickets.md": swarm_template("Revision Tickets"),
        "score-calibration.md": (
            "# Score Calibration\n\n"
            "Raw swarm score:\n"
            "Calibrated score:\n"
            "Confidence:\n"
            "Coverage:\n"
            "Weakest cohort:\n"
            "Best cohort:\n"
            "Human validation still needed:\n"
        ),
        "mirofish-requirement.md": (
            "# MiroFish Requirement\n\n"
            "Use this only when an external MiroFish project/server is available.\n\n"
            "## Seed Inputs\n\n"
            "- Manuscript/package files listed in `sample-map.md`\n"
            "- Persona roster from `persona-roster.json`\n\n"
            "## Import Contract\n\n"
            "- Persona files\n"
            "- Action logs\n"
            "- Interviews\n"
            "- Summary report\n\n"
            "Do not copy AGPL MiroFish code into this repository.\n"
        ),
        "SUMMARY.md": swarm_template("Summary"),
    }

    for filename, content in files.items():
        write_if_needed(run_dir / filename, content, force=False)

    return run_dir


def prepare_agent_packet(target: Path, agent_key: str) -> Path:
    agent = get_agent_spec(agent_key)
    packet_dir = target / "work" / "agent-packets"
    packet_dir.mkdir(parents=True, exist_ok=True)

    input_lines = _path_status_lines(target, agent.inputs)
    output_lines = "\n".join(f"- `{item}`" for item in agent.outputs) or "- No required outputs listed."
    gate_lines = "\n".join(f"- {item}" for item in agent.gates) or "- No gates listed."

    skill_path = _paths.repo_root() / agent.skill
    skill_excerpt = ""
    if skill_path.exists():
        skill_excerpt = skill_path.read_text(encoding="utf-8").strip()
    else:
        skill_excerpt = f"Skill file not found: `{agent.skill}`"

    packet = (
        f"# Agent Packet: {agent.label}\n\n"
        f"- Agent key: `{agent.key}`\n"
        f"- Timing: {agent.timing}\n"
        f"- Score floor: {agent.score_floor or 'project default'}\n"
        f"- Skill: `{agent.skill}`\n\n"
        "## Mission\n\n"
        f"{agent.mission}\n\n"
        "## Input Status\n\n"
        f"{input_lines}\n\n"
        "## Required Outputs\n\n"
        f"{output_lines}\n\n"
        "## Gates\n\n"
        f"{gate_lines}\n\n"
        "## Operating Rule\n\n"
        "Produce durable files only. Do not claim market-ready, viral-ready, or 8.5+ readiness unless every listed gate passes with evidence. "
        "When a gate fails, write blockers and revision tickets instead of inflating scores.\n\n"
        "## Skill Prompt\n\n"
        f"{skill_excerpt}\n"
    )

    packet_path = packet_dir / f"{agent.key}.md"
    packet_path.write_text(packet, encoding="utf-8")
    return packet_path


def advance_phase(target: Path, *, skip_checks: bool = False) -> Dict[str, object]:
    from runner.gates import evaluate_gate, write_gate_report  # local import: avoid a cycle

    phase = current_phase(target)
    pending = pending_outputs(target, phase.outputs)
    if pending:
        return {"ok": False, "pending": pending, "next_phase": phase.label, "failed_checks": [], "report": ""}

    state = target / "PROJECT_STATE.yaml"

    failed_checks: List[str] = []
    report_text = ""
    if skip_checks:
        state_set(target, "pipeline.gates_bypassed", phase.gate, create=True)
    else:
        verdict = evaluate_gate(target, phase)
        write_gate_report(target, verdict)
        report_text = "\n".join(f"{r.name}: {r.status}" for r in verdict.results)
        if not verdict.ok:
            failed_checks = [f"{r.name}: {r.summary}" for r in verdict.blocking]
            return {
                "ok": False, "pending": [], "next_phase": phase.label,
                "failed_checks": failed_checks, "report": report_text,
            }

    _update_state_value(state, phase.gate, "passed")

    if phase.next:
        _update_state_value(state, "current_phase", phase.next)
        _update_state_value(state, "current_gate", "")
        _update_state_value(state, "status", "ready")
    else:
        _update_state_value(state, "status", "completed")
        _update_state_value(state, "current_gate", "")

    return {
        "ok": True, "pending": [], "next_phase": phase.next or "completed",
        "failed_checks": [], "report": report_text,
    }


def create_demo(target: Path, *, adapter: str, model_name: str) -> None:
    scaffold_project(
        target,
        idea="Mechanical smoke-test novella about an archivist who audits a haunted manuscript.",
        adapter=adapter,
        model_name=model_name,
        language="en",
        force=True,
    )

    while load_state_summary(target)["status"] != "completed":
        phase = current_phase(target)
        fill_outputs_for_demo(target, phase)
        result = advance_phase(target)
        if not result["ok"]:
            raise RuntimeError(f"Demo could not advance: {result['pending']}")

    (target / "RUN_REPORT.md").write_text(
        "# Run Report\n\n"
        "## Run Summary\n\n"
        "This is a deterministic mechanical demo. It proves the file workflow, gates, "
        "and phase advancement, not literary quality.\n\n"
        "## Result\n\n"
        "- Status: completed\n"
        "- Chapters: 2 demo chapters\n",
        encoding="utf-8",
    )


def current_phase(target: Path) -> Phase:
    label = load_state_summary(target)["current_phase"]
    for phase in load_manifest():
        if phase.label == label:
            return phase
    raise KeyError(f"Unknown current phase: {label}")


def pending_outputs(target: Path, outputs: List[str]) -> List[str]:
    pending: List[str] = []
    for output in outputs:
        path = target / output
        # Any directory-shaped output (manuscript/chapters, delivery/epub,
        # etc.) is satisfied by >=1 non-empty file inside it, not by a
        # single hardcoded special case -- a second directory output must
        # not need a second branch here (and must not IsADirectoryError
        # below when we try to read it as a file).
        if path.is_dir() or output.endswith("/") or "." not in Path(output).name:
            files = [p for p in path.glob("**/*") if p.is_file()] if path.exists() else []
            if not any(f.stat().st_size > 0 for f in files):
                pending.append(output)
            continue
        if not path.exists():
            pending.append(output)
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text or "BOOK_GENESIS_TEMPLATE" in text or text == template_for_output(output).strip():
            pending.append(output)
    return pending


def fill_outputs_for_demo(target: Path, phase: Phase) -> None:
    for output in phase.outputs:
        path = target / output
        if output == "manuscript/chapters":
            chapters_dir = target / "manuscript" / "chapters"
            chapters_dir.mkdir(parents=True, exist_ok=True)
            for name, text in _DEMO_CHAPTERS.items():
                (chapters_dir / name).write_text(text, encoding="utf-8")
            (target / "TIMELINE.md").write_text(_DEMO_TIMELINE, encoding="utf-8")
            state_set(target, "project.word_count_target", "900", create=True)
            continue
        if output == "BOOK.yaml":
            from runner.compile import book_meta_template  # local import: avoid a cycle
            path.write_text(
                book_meta_template(title="The Ledger", author="Demo Author"),
                encoding="utf-8",
            )
            continue
        if output == "manuscript/full-manuscript.md":
            from runner.compile import compile_manuscript_md, load_book_meta  # local import
            compile_manuscript_md(target, load_book_meta(target))
            continue
        if output == "delivery/epub":
            from runner.compile import build_epub, load_book_meta  # local import
            build_epub(target, load_book_meta(target))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Demo Output: {phase.label}\n\n"
            f"Generated for `{output}` by the mechanical demo runner.\n\n"
            "This content is intentionally short. It exists to prove the workflow contract.\n",
            encoding="utf-8",
        )


# The demo fixture must genuinely pass the deterministic gates (runner/gates.py),
# not merely produce non-empty files. It exists to prove the whole workflow
# contract end to end, gates included -- see tests/test_runner.py::test_demo_passes_all_gates.
_DEMO_CHAPTERS: Dict[str, str] = {
    "chapter-01.md": (
        "# Chapter 1: The Ledger\n\n"
        "Mira Voss set the lantern on the workbench and pried open the crate. "
        "Sawdust drifted across her sleeve and settled on the floorboards. "
        "Inside, wrapped in oilcloth, lay a bound ledger stamped with a seal "
        "she failed to place.\n\n"
        "\"You are not supposed to touch that,\" said Devon from the doorway. "
        "He carried a mug of cold coffee and looked like he had not slept in "
        "two days.\n\n"
        "\"Somebody has to open it,\" Mira said, turning the first page. The "
        "ink had faded to rust, but the handwriting shifted between three "
        "different hands, switching mid-sentence without warning.\n\n"
        "\"Read it out loud,\" Devon said. \"I want to hear how bad it "
        "actually is.\"\n\n"
        "She read the first line aloud. The old pipes ticked louder than "
        "usual, and Devon set his mug down on the workbench, careful not to "
        "spill it near the open crate.\n\n"
        "\"That is my handwriting,\" he said, leaning closer. \"I never wrote "
        "a word of this.\"\n\n"
        "Mira closed the ledger and pressed her palm flat against the "
        "leather cover, feeling the grain under her fingers. Outside, a "
        "truck rumbled past on the gravel road, and the window glass "
        "rattled once before it settled.\n\n"
        "Devon reached for the ledger, then stopped, his hand hovering an "
        "inch above the cover. \"Put it back in the crate,\" he said. "
        "\"Tonight. Before anyone else sees it.\"\n"
    ),
    "chapter-02.md": (
        "# Chapter 2: Second Hand\n\n"
        "By dawn the crate sat right where Devon had left it, but the "
        "ledger was gone from the shelf. Mira found it open on the kitchen "
        "table, a fresh page filling itself while she watched, the pen "
        "resting untouched beside it.\n\n"
        "\"Devon,\" she called. No answer came from upstairs.\n\n"
        "She sat down across from the ledger and read the new line: a "
        "description of the argument they had just had, word for word, "
        "written before either of them said it aloud a second time. She "
        "pushed the plate of toast aside and leaned in.\n\n"
        "Footsteps came down the stairs, slow and uneven. Devon stopped in "
        "the kitchen doorway, one hand braced against the frame.\n\n"
        "\"It wrote what we said last night,\" Mira told him, sliding the "
        "ledger across the table. \"Before we said it.\"\n\n"
        "He picked up the pen and turned it over between his fingers, "
        "studying the nib as though it might explain itself. \"Then we stop "
        "talking near it,\" he said finally, setting the pen down beside "
        "the plate.\n\n"
        "Mira shook her head and closed the cover. \"Somebody wrote the "
        "first page decades ago. That did not stop anything.\" She carried "
        "the ledger to the window and held it up to the grey morning "
        "light, checking the binding for a printer's mark.\n\n"
        "Outside, a dog barked twice at the mail truck and went quiet.\n"
    ),
    "chapter-03.md": (
        "# Chapter 3: The Archive\n\n"
        "The county archive smelled of dust and cold radiator paint. Mira "
        "handed the clerk a slip with the ledger's seal copied onto it in "
        "pencil.\n\n"
        "\"Where did you find this mark?\" the clerk asked, turning the "
        "paper under the desk lamp.\n\n"
        "\"On a ledger my neighbor inherited,\" Mira said. \"It keeps "
        "writing things that have not happened yet.\"\n\n"
        "The clerk set the paper down without laughing, which surprised "
        "her more than a dismissal would have. He walked to a locked "
        "cabinet in the back room and returned with a thin folder tied in "
        "twine.\n\n"
        "\"Three families have brought me that seal,\" he said, untying the "
        "string with careful fingers. \"Each one swore the book started "
        "blank.\"\n\n"
        "Inside the folder were photographs of the same ledger, cracked "
        "spine and all, dated across nearly a hundred years. Mira spread "
        "them across the counter and counted the handwriting styles: five, "
        "maybe six.\n\n"
        "\"Somebody keeps passing it along,\" she said.\n\n"
        "\"Or something keeps bringing it back,\" the clerk answered. He "
        "tapped the earliest photograph, a sepia print of a woman holding "
        "the ledger against her chest like a shield. \"That one disappeared "
        "three weeks after this was taken.\"\n\n"
        "Mira gathered the photographs into a neat stack and slid them "
        "back into the folder, her hands steadier than she expected them "
        "to be.\n"
    ),
    "chapter-04.md": (
        "# Chapter 4: What the Page Knew\n\n"
        "Devon was waiting on the porch steps when Mira got home, the "
        "ledger closed on his knees. He had not gone inside.\n\n"
        "\"It wrote your name again,\" he said, holding the cover shut with "
        "both hands. \"And a date. Tomorrow's date.\"\n\n"
        "Mira sat down beside him and took the ledger carefully, the "
        "leather still warm from his grip. She opened it to the last page "
        "and read the line under the date: a single sentence, plain and "
        "short, naming the archive and the clerk's folder of "
        "photographs.\n\n"
        "\"It already knows where we went,\" she said.\n\n"
        "\"Then we stop feeding it new pages,\" Devon said. \"We put it "
        "back in the ground where the crate came from and we leave it.\"\n\n"
        "Mira turned to the first blank leaf after the newest entry. For a "
        "long moment neither of them spoke, and the porch light buzzed "
        "once overhead. She had never liked that porch light, the way it "
        "hummed before it caught, but tonight she did not reach to turn it "
        "off. She reached for the pen resting in the ledger's spine.\n\n"
        "\"Or we write the next line ourselves,\" she said, \"before it "
        "gets the chance.\"\n\n"
        "She set the nib against the paper. Devon did not stop her. Down "
        "the street, someone's screen door banged shut, and the ledger's "
        "blank page waited under her hand.\n"
    ),
}

_DEMO_TIMELINE = (
    'event  id=crate_found     day=0     label="Mira opens the crate"\n'
    'event  id=ledger_writes   day=1     label="Ledger writes overnight"\n'
    'event  id=archive_visit   day=3     label="Archive visit"\n'
    'event  id=porch_scene     day=4     label="Devon waits on the porch"\n\n'
    'span   from=crate_found   to=porch_scene   stated=4d   src="Ch1-4"\n'
)


def template_for_output(output: str) -> str:
    if output == "ASSUMPTIONS.md":
        return assumptions_template("")
    if output.startswith("artifacts/"):
        return artifact_template(Path(output).name)
    return ""


def artifact_template(filename: str) -> str:
    heading = ARTIFACT_HEADINGS.get(filename, filename)
    return (
        f"# {heading}\n\n"
        "<!-- BOOK_GENESIS_TEMPLATE: replace this file with phase output. -->\n\n"
        "## Required Content\n\n"
        "- Fill this artifact from the active phase prompt.\n"
        "- Cite assumptions and evidence where applicable.\n"
    )


def assumptions_template(idea: str) -> str:
    idea_line = f"\nUser idea: {idea}\n" if idea else ""
    return (
        "# Assumptions\n"
        f"{idea_line}\n"
        "<!-- BOOK_GENESIS_TEMPLATE: replace inferred assumptions before advancing. -->\n\n"
        "## Confirmed Inputs\n\n"
        "- TBD\n\n"
        "## Inferred Assumptions\n\n"
        "- TBD\n\n"
        "## Open Questions\n\n"
        "- TBD\n"
    )


def run_report_template() -> str:
    return (
        "# Run Report\n\n"
        "## Run Summary\n\n"
        "<!-- BOOK_GENESIS_TEMPLATE: update as phases complete. -->\n\n"
        "## Phase Log\n\n"
        "- TBD\n"
    )


def swarm_template(title: str) -> str:
    return (
        f"# {title}\n\n"
        "<!-- BOOK_SWARM_TEMPLATE: replace with simulated reader evidence or imported MiroFish output. -->\n\n"
        "## Required Content\n\n"
        "- Evidence-backed findings.\n"
        "- Clear simulated-signal vs editorial-judgment labels.\n"
        "- Human validation needs where applicable.\n"
    )


def write_if_needed(path: Path, content: str, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return
    path.write_text(content, encoding="utf-8")


def _project_state_template(
    *,
    idea: str,
    adapter: str,
    model_name: str,
    language: str,
    first_phase: str,
    gates: str,
) -> str:
    return (
        "project:\n"
        "  id: \"\"\n"
        "  title: \"\"\n"
        "  author: \"\"\n"
        f"  idea: \"{_escape_yaml(idea)}\"\n"
        f"  language: \"{_escape_yaml(language)}\"\n"
        "  genre: \"\"\n"
        "  subgenre: \"\"\n"
        "  audience: \"\"\n"
        "  target_length: \"\"\n"
        "  length_tier: \"\"\n"
        "  word_count_target: 0\n"
        "  autonomy: \"guided\"\n"
        "  lint_profile: \"\"\n\n"
        "runtime:\n"
        f"  adapter: \"{_escape_yaml(adapter)}\"\n"
        f"  model_family: \"{_infer_family(model_name)}\"\n"
        f"  model_name: \"{_escape_yaml(model_name)}\"\n\n"
        "pipeline:\n"
        f"  current_phase: \"{first_phase}\"\n"
        "  current_gate: \"\"\n"
        "  status: \"not_started\"\n"
        "  revision_iteration: 0\n\n"
        "artifacts:\n"
        "  generated: []\n\n"
        "manuscript:\n"
        "  chapter_count: 0\n"
        "  completed_chapters: []\n"
        "  status: \"not_started\"\n\n"
        "gates:\n"
        f"{gates}\n"
    )


def state_path(target: Path) -> Path:
    return target / "PROJECT_STATE.yaml"


def state_get(target: Path, dotted: str, default: str = "") -> str:
    """Read a value from PROJECT_STATE.yaml.

    ``dotted`` may be a bare key (``"status"``), which uses the original
    first-match-anywhere-in-file scan (preserving the long-standing
    ``pipeline.status`` vs ``manuscript.status`` resolution, since
    ``pipeline:`` precedes ``manuscript:`` in the template), or a
    ``block.key`` path (``"project.autonomy"``), which is scoped to the
    named top-level block only.
    """

    text = state_path(target).read_text(encoding="utf-8")
    if "." not in dotted:
        value = _extract_scalar(text, dotted)
        return value if value else default

    block, _, key = dotted.partition(".")
    start, end = _find_block_span(text, block)
    if start is None:
        return default
    lines = text.splitlines()
    value = _extract_scalar("\n".join(lines[start:end]), key)
    return value if value else default


def state_get_int(target: Path, dotted: str, default: int = 0) -> int:
    raw = state_get(target, dotted, default=str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def state_set(target: Path, dotted: str, value: str, *, create: bool = True) -> None:
    """Write a value into PROJECT_STATE.yaml.

    See ``state_get`` for the bare-key vs ``block.key`` distinction. When
    ``create`` is True and the key does not exist within its block, it is
    appended as the block's last line. When ``create`` is False, a missing
    key raises ``KeyError`` (matching the historical ``_update_state_value``
    contract).
    """

    path = state_path(target)
    if "." not in dotted:
        _update_state_value(path, dotted, value)
        return

    block, _, key = dotted.partition(".")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    start, end = _find_block_span(text, block)
    if start is None:
        raise KeyError(f"Could not find block {block!r} in {path}")

    prefix = f"{key}:"
    for index in range(start, end):
        stripped = lines[index].strip()
        if stripped.startswith(prefix):
            indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
            lines[index] = f'{indent}{key}: "{value}"'
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return

    if not create:
        raise KeyError(f"Could not update key {key!r} in block {block!r} in {path}")

    # Insert as the last line of the block, before its trailing blank line.
    insert_at = end
    while insert_at > start and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, f'  {key}: "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _find_block_span(text: str, block: str) -> tuple:
    """Return (start_index, end_index) line bounds for a top-level block.

    ``start_index`` points at the ``block:`` line itself; ``end_index`` is
    exclusive and points at the next top-level (zero-indent, non-blank)
    line, or ``len(lines)`` if the block runs to the end of the file.
    Returns ``(None, None)`` if the block is not found.
    """

    lines = text.splitlines()
    prefix = f"{block}:"
    start = None
    for index, line in enumerate(lines):
        if line.startswith(prefix) and (line[len(prefix) :] == "" or line[len(prefix)] in " \t"):
            start = index
            break
    if start is None:
        return None, None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line[0].isspace():
            end = index
            break
    return start, end


def _update_state_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}:"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(prefix):
            indent = line[: len(line) - len(line.lstrip())]
            lines[index] = f'{indent}{key}: "{value}"'
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return
    raise KeyError(f"Could not update key {key!r} in {path}")


def _extract_scalar(text: str, key: str) -> str:
    prefix = f"{key}:"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return _unquote(stripped.split(":", 1)[1].strip())
    return ""


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def _escape_yaml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _infer_family(model_name: str) -> str:
    normalized = model_name.lower()
    if "claude" in normalized or "opus" in normalized or "sonnet" in normalized:
        return "claude"
    if "gpt" in normalized or "codex" in normalized:
        return "openai"
    if "gemini" in normalized:
        return "google"
    if "kimi" in normalized:
        return "kimi"
    return "unknown"


def _load_simple_yaml_map(path: Path) -> Dict[str, Dict[str, object]]:
    raw = path.read_text(encoding="utf-8").splitlines()
    entries: Dict[str, Dict[str, object]] = {}
    current_key = ""
    current_list_key = ""

    for line in raw:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            current_key = line.split(":", 1)[0].strip()
            entries[current_key] = {}
            current_list_key = ""
            continue
        if not current_key:
            raise ValueError(f"Value before top-level key in {path}: {line}")
        stripped = line.strip()
        if stripped.startswith("- "):
            if not current_list_key:
                raise ValueError(f"List item without list key in {path}: {line}")
            entries[current_key].setdefault(current_list_key, [])
            entries[current_key][current_list_key].append(_unquote(stripped[2:].strip()))  # type: ignore[index]
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            entries[current_key][key] = []
            current_list_key = key
        else:
            entries[current_key][key] = _unquote(value)
            current_list_key = ""

    return entries


def _path_status_lines(target: Path, paths: List[str]) -> str:
    if not paths:
        return "- No required inputs listed."
    lines = []
    for item in paths:
        path = target / item
        status = "present" if path.exists() else "missing"
        lines.append(f"- `{item}`: {status}")
    return "\n".join(lines)


def _slugify(value: str) -> str:
    cleaned = []
    previous_dash = False
    for character in value.lower():
        if character.isalnum():
            cleaned.append(character)
            previous_dash = False
            continue
        if not previous_dash:
            cleaned.append("-")
            previous_dash = True
    return "".join(cleaned).strip("-") or "reader-swarm"
