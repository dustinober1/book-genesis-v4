from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.filesystem import (  # type: ignore  # noqa: E402
    load_state_summary,
    scaffold_project,
    state_get,
    state_get_int,
    state_set,
)


class StateAccessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-state-"))
        scaffold_project(
            self.tempdir,
            idea="a detective audits a haunted manuscript",
            adapter="codex",
            model_name="gpt-5.5",
            language="en",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_scaffold_writes_new_schema_fields(self) -> None:
        self.assertEqual("guided", state_get(self.tempdir, "project.autonomy"))
        self.assertEqual("", state_get(self.tempdir, "project.subgenre"))
        self.assertEqual(0, state_get_int(self.tempdir, "project.word_count_target"))

    def test_set_and_get_dotted_key(self) -> None:
        state_set(self.tempdir, "project.autonomy", "auto")
        self.assertEqual("auto", state_get(self.tempdir, "project.autonomy"))

        state_set(self.tempdir, "project.word_count_target", "90000")
        self.assertEqual(90000, state_get_int(self.tempdir, "project.word_count_target"))

    def test_set_dotted_key_scopes_to_named_block_only(self) -> None:
        # "status" exists in both project-adjacent pipeline: and
        # manuscript: blocks. Setting manuscript.status must not touch
        # pipeline.status.
        state_set(self.tempdir, "manuscript.status", "drafting")
        summary = load_state_summary(self.tempdir)
        self.assertEqual("not_started", summary["status"])  # still pipeline.status
        self.assertEqual("drafting", state_get(self.tempdir, "manuscript.status"))

    def test_get_missing_dotted_key_returns_default(self) -> None:
        self.assertEqual("fallback", state_get(self.tempdir, "project.nonexistent", default="fallback"))

    def test_set_missing_key_with_no_create_raises(self) -> None:
        with self.assertRaises(KeyError):
            state_set(self.tempdir, "project.brand_new_field", "x", create=False)

    def test_set_missing_key_with_create_inserts_it(self) -> None:
        state_set(self.tempdir, "project.brand_new_field", "x", create=True)
        self.assertEqual("x", state_get(self.tempdir, "project.brand_new_field"))
        # Sibling keys in the same block must survive the insert.
        self.assertEqual("guided", state_get(self.tempdir, "project.autonomy"))

    def test_bare_key_set_preserves_legacy_behavior(self) -> None:
        state_set(self.tempdir, "status", "in_progress")
        summary = load_state_summary(self.tempdir)
        self.assertEqual("in_progress", summary["status"])

    def test_cli_set_and_get(self) -> None:
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "runner" / "cli.py"), "set",
             str(self.tempdir), "project.subgenre", "gothic horror"],
            check=True, capture_output=True, text=True,
        )
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "runner" / "cli.py"), "get",
             str(self.tempdir), "project.subgenre"],
            check=True, capture_output=True, text=True,
        )
        self.assertEqual("gothic horror", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
