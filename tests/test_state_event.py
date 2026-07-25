from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.state_event import (  # noqa: E402
    apply_event,
    append_nested,
    get_nested,
    set_nested,
)

STATE_TEMPLATE = """project:
  title: "Test Book"
  genre: "thriller"
  created: ""

phase:
  current: 1
  status: "in_progress"

chapters:
  total_planned: 0
  completed: []

genesis_score:
  current_floor: 0.0

decisions: []
human_feedback: []
revision_cycles: 0
"""


def _init_project(with_git: bool = True) -> Path:
    tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-state-event-"))
    (tempdir / "STATE.yaml").write_text(STATE_TEMPLATE, encoding="utf-8")
    if with_git:
        subprocess.run(["git", "init", "-q", str(tempdir)], check=True)
        subprocess.run(["git", "-C", str(tempdir), "config", "user.email", "test@test.com"], check=True)
        subprocess.run(["git", "-C", str(tempdir), "config", "user.name", "test"], check=True)
    return tempdir


class NestedYamlEditingTests(unittest.TestCase):
    def test_set_nested_overwrites_existing_scalar(self) -> None:
        lines = STATE_TEMPLATE.splitlines()
        lines = set_nested(lines, "phase.current", "2", create=True)
        self.assertEqual("2", get_nested(lines, "phase.current"))
        # sibling untouched
        self.assertEqual("in_progress", get_nested(lines, "phase.status"))

    def test_set_nested_creates_missing_leaf(self) -> None:
        lines = STATE_TEMPLATE.splitlines()
        lines = set_nested(lines, "genesis_score.dimension_7_score", "8.0", create=True)
        self.assertEqual("8.0", get_nested(lines, "genesis_score.dimension_7_score"))
        self.assertEqual("0.0", get_nested(lines, "genesis_score.current_floor"))

    def test_append_nested_to_empty_inline_list(self) -> None:
        lines = STATE_TEMPLATE.splitlines()
        lines = append_nested(lines, "chapters.completed", '{number: 1, title: "Ch1"}')
        text = "\n".join(lines)
        self.assertIn('- {number: 1, title: "Ch1"}', text)

    def test_append_nested_twice_preserves_order(self) -> None:
        lines = STATE_TEMPLATE.splitlines()
        lines = append_nested(lines, "decisions", '{note: "first"}')
        lines = append_nested(lines, "decisions", '{note: "second"}')
        text = "\n".join(lines)
        self.assertLess(text.index('"first"'), text.index('"second"'))


class ApplyEventTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = _init_project()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_unknown_event_type_rejected(self) -> None:
        result = apply_event(self.tempdir, event_type="not-a-type", note="x")
        self.assertFalse(result.ok)
        self.assertEqual("schema-validation", result.code)
        self.assertTrue(result.retryable)

    def test_blank_note_rejected(self) -> None:
        result = apply_event(self.tempdir, event_type="research-update", note="   ")
        self.assertFalse(result.ok)
        self.assertEqual("schema-validation", result.code)

    def test_allowlist_violation(self) -> None:
        result = apply_event(
            self.tempdir, event_type="research-update", note="try to write chapters",
            sets=[("chapters.total_planned", "10")],
        )
        self.assertFalse(result.ok)
        self.assertEqual("allowlist-violation", result.code)

    def test_stale_phase_rejected(self) -> None:
        result = apply_event(
            self.tempdir, event_type="phase-advance", note="advance", expected_phase="99",
            sets=[("phase.current", "2")], approved=True,
        )
        self.assertFalse(result.ok)
        self.assertEqual("stale-phase", result.code)
        self.assertTrue(result.retryable)

    def test_human_gate_required_without_approval(self) -> None:
        result = apply_event(
            self.tempdir, event_type="phase-advance", note="advance",
            sets=[("phase.current", "2")],
        )
        self.assertFalse(result.ok)
        self.assertEqual("human-gate-required", result.code)

    def test_successful_event_writes_state_status_handoff_and_commits(self) -> None:
        result = apply_event(
            self.tempdir, event_type="phase-advance", note="advance to 2", expected_phase="1",
            sets=[("phase.current", "2")], approved=True,
        )
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.commit)
        self.assertTrue((self.tempdir / "STATUS.md").exists())
        self.assertTrue((self.tempdir / "HANDOFF.md").exists())

        state_text = (self.tempdir / "STATE.yaml").read_text(encoding="utf-8")
        self.assertIn('current: "2"', state_text)
        self.assertIn('rationale: "advance to 2"', state_text)  # decisions[] entry

        log = subprocess.run(
            ["git", "-C", str(self.tempdir), "log", "--oneline"],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("phase-advance", log.stdout)

    def test_missing_state_file_is_filesystem_failure(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="book-genesis-no-state-"))
        try:
            result = apply_event(empty, event_type="research-update", note="x")
            self.assertFalse(result.ok)
            self.assertEqual("filesystem-failure", result.code)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_no_git_skips_commit(self) -> None:
        nogit = _init_project(with_git=False)
        try:
            result = apply_event(
                nogit, event_type="research-update", note="x",
                sets=[("project.genre", "romantasy")], use_git=False,
            )
            self.assertTrue(result.ok)
            self.assertEqual("", result.commit)
        finally:
            shutil.rmtree(nogit, ignore_errors=True)

    def test_cli_apply_event_json(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "runner" / "cli.py"), "apply-event",
             str(self.tempdir), "--type", "research-update", "--note", "cli test",
             "--set", "project.genre=romantasy", "--json"],
            capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('"ok": true', result.stdout)


if __name__ == "__main__":
    unittest.main()
