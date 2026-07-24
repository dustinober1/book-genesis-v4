from pathlib import Path
import shutil
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner import paths  # type: ignore  # noqa: E402


class PathsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-paths-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_repo_checkout_resolves_without_override(self) -> None:
        # Running from the real checkout should resolve without any env var.
        root = paths.repo_root()
        self.assertTrue((root / "skills" / "book-genesis-codex").is_dir())

    def test_installed_layout_resolves_via_override(self) -> None:
        # Simulate install.sh's target layout: runner/ and skills/ copied
        # into a shared install root (not nested the way a checkout is).
        install_root = self.tempdir / "book-genesis-runner"
        (install_root / "skills" / "book-genesis-codex" / "references" / "pipeline").mkdir(
            parents=True
        )
        (install_root / "skills" / "book-genesis-codex" / "references" / "pipeline" / "manifest.yaml").write_text(
            "phase_0_intake:\n  label: \"Phase 0\"\n", encoding="utf-8"
        )

        resolved = paths.repo_root(override=install_root)
        self.assertEqual(resolved, install_root)
        manifest = paths.manifest_path(override=install_root)
        self.assertTrue(manifest.is_file())

    def test_missing_skill_dir_raises_with_locations_named(self) -> None:
        # Neutralize the parents[1] fallback (which would otherwise resolve
        # to this real checkout) by pointing paths.__file__ somewhere with
        # no skill directory, so an invalid override genuinely has nowhere
        # left to fall back to.
        empty_root = self.tempdir / "empty"
        fake_module_dir = empty_root / "fake-install" / "runner"
        fake_module_dir.mkdir(parents=True)
        empty_root.mkdir(exist_ok=True)

        import unittest.mock as mock

        with mock.patch.object(paths, "__file__", str(fake_module_dir / "paths.py")):
            with self.assertRaises(FileNotFoundError) as ctx:
                paths.repo_root(override=empty_root)
        self.assertIn(str(empty_root), str(ctx.exception))

    def test_env_var_override(self) -> None:
        install_root = self.tempdir / "via-env"
        (install_root / "skills" / "book-genesis-codex").mkdir(parents=True)
        import os

        old = os.environ.get("BOOK_GENESIS_HOME")
        os.environ["BOOK_GENESIS_HOME"] = str(install_root)
        try:
            resolved = paths.repo_root()
            self.assertEqual(resolved, install_root)
        finally:
            if old is None:
                os.environ.pop("BOOK_GENESIS_HOME", None)
            else:
                os.environ["BOOK_GENESIS_HOME"] = old


if __name__ == "__main__":
    unittest.main()
