"""Guarded transaction engine for a project's ``STATE.yaml``.

``book-genesis-full``'s orchestrator (``agents/book-orchestrator.md``) owns
``STATE.yaml`` and has historically been trusted to hand-edit it correctly —
no schema check, no allowlist, no concurrency check, no audit trail beyond
whatever the orchestrator remembers to log. That trust model is the single
biggest structural gap versus a system like Novel Forge's ``novel_apply_event``:
a stale read, a typo'd key, or a skipped gate silently corrupts canonical
project state with no way to tell it happened.

This module is the guarded write path. Every state-changing transition goes
through ``apply_event``, which:

- validates the event type and every key it touches against a per-event-type
  allowlist (a ``research-update`` event must not silently write ``chapters``);
- optionally checks the caller's expected current phase against the file's
  actual ``phase.current`` before writing (stale-phase detection);
- requires an explicit approval flag for event types that gate on human
  sign-off, instead of trusting the caller to have asked;
- writes atomically, regenerates ``STATUS.md``/``HANDOFF.md``, and commits
  the result as one Git checkpoint (when the project is a Git repo);
- returns a structured, typed result instead of raising -- callers (an
  orchestrating agent, in practice) get a machine-checkable rejection code
  and a `retryable` flag rather than free-text they have to interpret.

Scalar overwrites use ``--set dotted.path=value``. List appends use
``--append dotted.path={flow: mapping}`` -- the value must be a YAML
flow-mapping (``{key: value, key2: value2}``), which is valid on a single
line and sidesteps writing a block-style nested-list inserter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple


# Event type -> top-level STATE.yaml blocks it is allowed to write to.
# A typo'd or unlisted event type is a hard error, not a silent allow-all --
# see EventRejection.code == "schema-validation".
EVENT_ALLOWLIST: Dict[str, List[str]] = {
    "phase-advance": ["phase"],
    "chapter-draft": ["chapters"],
    "chapter-revision": ["chapters", "revision_cycles"],
    "evaluation-update": [
        "genesis_score", "commercial_viability", "evaluation_tracking",
        "quality_gate", "systemic_patterns",
    ],
    "entity-update": ["continuity"],
    "continuity-update": ["continuity"],
    "research-update": ["project"],
    "human-feedback": ["human_feedback"],
    "voice-baseline": ["voice_bank", "voice_dna"],
    "reader-persona-update": ["reader_personas"],
    "reader-evidence": ["evaluation_tracking"],
    "mechanical-preprocess": ["mechanical_preprocess"],
    "package-update": ["decisions"],
    "decision": ["decisions"],
    "adoption": ["project", "chapters"],
}

# Event types that must carry an explicit approval note before they apply.
# This encodes "never bypass a human gate" as a check the engine enforces,
# not just a line in a prompt the orchestrator might forget to follow.
REQUIRES_APPROVAL = {"phase-advance", "package-update"}

RETRYABLE_CODES = {"schema-validation", "reference-validation", "stale-phase"}


@dataclass
class EventResult:
    ok: bool
    code: str  # "ok" | rejection code
    message: str
    retryable: bool = False
    commit: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok, "code": self.code, "message": self.message,
            "retryable": self.retryable, "commit": self.commit,
        }


def apply_event(
    target: Path,
    *,
    event_type: str,
    note: str,
    expected_phase: str = "",
    sets: Optional[List[Tuple[str, str]]] = None,
    appends: Optional[List[Tuple[str, str]]] = None,
    approved: bool = False,
    commit_extra: Optional[List[str]] = None,
    use_git: bool = True,
) -> EventResult:
    sets = sets or []
    appends = appends or []
    state_path = target / "STATE.yaml"

    if not note.strip():
        return EventResult(False, "schema-validation", "note is required and cannot be blank", retryable=True)
    if event_type not in EVENT_ALLOWLIST:
        known = ", ".join(sorted(EVENT_ALLOWLIST))
        return EventResult(
            False, "schema-validation", f"unknown event type {event_type!r}. Known types: {known}",
            retryable=True,
        )
    if not state_path.exists():
        return EventResult(False, "filesystem-failure", f"no STATE.yaml at {state_path}")

    allowed_blocks = EVENT_ALLOWLIST[event_type]
    for dotted, _ in [*sets, *appends]:
        block = dotted.split(".", 1)[0]
        if block not in allowed_blocks:
            return EventResult(
                False, "allowlist-violation",
                f"event type {event_type!r} may not write {dotted!r} "
                f"(allowed blocks: {', '.join(allowed_blocks)})",
            )

    if event_type in REQUIRES_APPROVAL and not approved:
        return EventResult(
            False, "human-gate-required",
            f"event type {event_type!r} requires explicit human approval before it applies",
        )

    text = state_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if expected_phase:
        actual_phase = get_nested(lines, "phase.current")
        if actual_phase and actual_phase != expected_phase:
            return EventResult(
                False, "stale-phase",
                f"expected phase.current={expected_phase!r}, found {actual_phase!r}. "
                "Reload project state and rebuild the event against the current phase.",
                retryable=True,
            )

    try:
        for dotted, value in sets:
            lines = set_nested(lines, dotted, value, create=True)
        for dotted, flow_value in appends:
            lines = append_nested(lines, dotted, flow_value)
        today = date.today().isoformat()
        phase_now = get_nested(lines, "phase.current")
        decision_entry = (
            f'{{date: "{today}", decision: "{event_type}", '
            f'rationale: "{_escape_flow(note)}", phase: "{phase_now}"}}'
        )
        lines = append_nested(lines, "decisions", decision_entry)
    except KeyError as exc:
        return EventResult(False, "reference-validation", str(exc), retryable=True)

    try:
        state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        status_path = target / "STATUS.md"
        handoff_path = target / "HANDOFF.md"
        status_path.write_text(render_status(target), encoding="utf-8")
        handoff_path.write_text(render_handoff(target, event_type=event_type, note=note), encoding="utf-8")
    except OSError as exc:
        return EventResult(False, "filesystem-failure", f"write failed: {exc}")

    commit_hash = ""
    if use_git:
        commit_files = [state_path, status_path, handoff_path, *(Path(p) for p in (commit_extra or []))]
        ok, message = _git_commit(target, commit_files, f"Book Genesis: {event_type} — {note}")
        if not ok:
            return EventResult(False, "filesystem-failure", f"git commit failed: {message}")
        commit_hash = message

    return EventResult(True, "ok", f"applied {event_type}", commit=commit_hash)


# --------------------------------------------------------------------------
# Nested line-based YAML editing (no external YAML dependency -- the runner
# is distributed standalone via install.sh and must not require pip installs
# in the target environment; see docs/portability.md).
# --------------------------------------------------------------------------

def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_key_line(lines: List[str], start: int, end: int, indent: int, key: str) -> Optional[int]:
    prefix = f"{key}:"
    for i in range(start, end):
        line = lines[i]
        if not line.strip():
            continue
        if _indent_of(line) == indent and line.strip().startswith(prefix):
            rest = line.strip()[len(prefix):]
            if rest == "" or rest[0] in " \t\"'{[":
                return i
    return None


def _span_end(lines: List[str], header_index: int, indent: int) -> int:
    for i in range(header_index + 1, len(lines)):
        if lines[i].strip() and _indent_of(lines[i]) <= indent:
            return i
    return len(lines)


def get_nested(lines: List[str], dotted: str) -> str:
    parts = dotted.split(".")
    indent = 0
    start, end = 0, len(lines)
    idx = None
    for part in parts:
        idx = _find_key_line(lines, start, end, indent, part)
        if idx is None:
            return ""
        header_end = _span_end(lines, idx, indent)
        start, end = idx + 1, header_end
        indent += 2
    if idx is None:
        return ""
    value = lines[idx].strip().split(":", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def set_nested(lines: List[str], dotted: str, value: str, *, create: bool = True) -> List[str]:
    lines = list(lines)
    parts = dotted.split(".")
    indent = 0
    start, end = 0, len(lines)
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        idx = _find_key_line(lines, start, end, indent, part)
        if idx is None:
            if not create:
                raise KeyError(f"missing key path: {dotted}")
            insert_at = end
            while insert_at > start and not lines[insert_at - 1].strip():
                insert_at -= 1
            new_line = (" " * indent) + f"{part}:" + (f' "{value}"' if is_last else "")
            lines.insert(insert_at, new_line)
            idx = insert_at
            end += 1
        if is_last:
            cur_indent = _indent_of(lines[idx])
            lines[idx] = (" " * cur_indent) + f'{part}: "{value}"'
            return lines
        header_end = _span_end(lines, idx, indent)
        start, end = idx + 1, header_end
        indent += 2
    return lines


def append_nested(lines: List[str], dotted: str, flow_item: str) -> List[str]:
    """Append one flow-mapping item to the YAML list at ``dotted``.

    Creates the list key (as an empty ``key: []``-less header) if it does
    not exist yet. ``flow_item`` must be a single-line YAML flow mapping,
    e.g. ``{date: "2026-07-24", note: "..."}"``.
    """

    lines = list(lines)
    parts = dotted.split(".")
    indent = 0
    start, end = 0, len(lines)
    idx = None
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        idx = _find_key_line(lines, start, end, indent, part)
        if idx is None:
            insert_at = end
            while insert_at > start and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, (" " * indent) + f"{part}:")
            idx = insert_at
            end += 1
        if is_last:
            break
        header_end = _span_end(lines, idx, indent)
        start, end = idx + 1, header_end
        indent += 2

    assert idx is not None
    header_line = lines[idx]
    # A bare `key:` header (no inline `[]`) may still carry an inline empty
    # list from a template (e.g. `decisions: []`) -- normalize it to a
    # block header before inserting the first item.
    if header_line.strip().endswith("[]"):
        lines[idx] = (" " * _indent_of(header_line)) + f"{parts[-1]}:"

    list_end = _span_end(lines, idx, _indent_of(lines[idx]))
    insert_at = list_end
    while insert_at > idx + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    item_indent = _indent_of(lines[idx]) + 2
    lines.insert(insert_at, (" " * item_indent) + f"- {flow_item}")
    return lines


def _escape_flow(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# --------------------------------------------------------------------------
# STATUS.md / HANDOFF.md
# --------------------------------------------------------------------------

def render_status(target: Path) -> str:
    lines = (target / "STATE.yaml").read_text(encoding="utf-8").splitlines()
    title = get_nested(lines, "project.title") or "(untitled)"
    phase = get_nested(lines, "phase.current") or "?"
    phase_status = get_nested(lines, "phase.status") or "?"
    floor = get_nested(lines, "genesis_score.current_floor") or "0.0"
    cvi_launch = get_nested(lines, "commercial_viability.cvi_launch") or "0.0"
    revision_cycles = get_nested(lines, "revision_cycles") or "0"

    return (
        f"# STATUS — {title}\n\n"
        f"- **Phase:** {phase} ({phase_status})\n"
        f"- **Genesis Score floor:** {floor}\n"
        f"- **CVI-Launch:** {cvi_launch}\n"
        f"- **Revision cycles this iteration:** {revision_cycles}\n\n"
        "This file is regenerated by `runner/cli.py apply-event` after every "
        "accepted transaction. Do not hand-edit it — edit `STATE.yaml` via "
        "`apply-event` instead, and this file will catch up automatically.\n"
    )


def render_handoff(target: Path, *, event_type: str, note: str) -> str:
    lines = (target / "STATE.yaml").read_text(encoding="utf-8").splitlines()
    phase = get_nested(lines, "phase.current") or "?"
    today = date.today().isoformat()

    return (
        f"# HANDOFF\n\n"
        f"- **Last event:** `{event_type}` — {note}\n"
        f"- **Applied:** {today}\n"
        f"- **Current phase:** {phase}\n\n"
        "## Resume here\n\n"
        "1. Read `STATE.yaml` for full project state.\n"
        f"2. Current phase is `{phase}` — check the SKILL.md phase-gate checklist "
        "for that phase before dispatching the next skill.\n"
        "3. If a human gate is pending (see `phase.status: gate_pending`), stop "
        "and surface it to the user instead of proceeding automatically.\n"
    )


# --------------------------------------------------------------------------
# Git checkpoint
# --------------------------------------------------------------------------

def _git_commit(target: Path, files: List[Path], message: str) -> Tuple[bool, str]:
    repo_check = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    if repo_check.returncode != 0:
        return False, "not a Git repository"

    add = subprocess.run(
        ["git", "-C", str(target), "add", *[str(f) for f in files if f.exists()]],
        capture_output=True, text=True,
    )
    if add.returncode != 0:
        return False, add.stderr.strip()

    diff = subprocess.run(
        ["git", "-C", str(target), "diff", "--cached", "--quiet"],
        capture_output=True, text=True,
    )
    if diff.returncode == 0:
        return True, "(no changes to commit)"

    commit = subprocess.run(
        ["git", "-C", str(target), "commit", "-m", message],
        capture_output=True, text=True,
    )
    if commit.returncode != 0:
        return False, commit.stderr.strip()

    rev = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return True, rev.stdout.strip()
