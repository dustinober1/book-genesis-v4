from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from runner.filesystem import (  # type: ignore  # noqa: E402
    advance_phase,
    create_demo,
    load_agent_registry,
    load_manifest,
    load_state_summary,
    prepare_agent_packet,
    prepare_phase,
    prepare_swarm_run,
    scaffold_project,
    state_set,
    validate_project,
)
from runner.gates import evaluate_gate  # type: ignore  # noqa: E402


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="book-genesis-runner-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def test_manifest_loads_universal_pipeline(self) -> None:
        phases = load_manifest()
        self.assertEqual("Phase 0: Intake", phases[0].label)
        self.assertEqual("Phase 7: Production", phases[-1].label)
        self.assertEqual(8, len(phases))

    def test_market_level_skills_are_packaged(self) -> None:
        bestseller = REPO_ROOT / "skills" / "book-bestseller-studio" / "SKILL.md"
        swarm = REPO_ROOT / "skills" / "book-swarm-panel" / "SKILL.md"
        self.assertTrue(bestseller.exists())
        self.assertTrue(swarm.exists())
        self.assertIn("book-genesis-codex", bestseller.read_text(encoding="utf-8"))
        self.assertIn("MiroFish", swarm.read_text(encoding="utf-8"))

    def test_agent_registry_loads_bestseller_team(self) -> None:
        agents = load_agent_registry()
        keys = {agent.key for agent in agents}
        self.assertIn("worldbuilder", keys)
        self.assertIn("prose_writer", keys)
        self.assertIn("pacing_engineer", keys)
        self.assertIn("viral_framing_strategist", keys)
        self.assertIn("scorekeeper", keys)
        self.assertGreaterEqual(len(agents), 12)

    def test_init_creates_project_contract(self) -> None:
        scaffold_project(
            self.tempdir,
            idea="a detective audits a haunted manuscript",
            adapter="codex",
            model_name="gpt-5.5",
            language="en",
        )
        self.assertTrue((self.tempdir / "PROJECT_STATE.yaml").exists())
        self.assertTrue((self.tempdir / "ASSUMPTIONS.md").exists())
        self.assertTrue((self.tempdir / "RUN_REPORT.md").exists())
        self.assertTrue((self.tempdir / "artifacts" / "00-brief.md").exists())
        self.assertTrue((self.tempdir / "manuscript" / "chapters").is_dir())
        self.assertTrue((self.tempdir / "evaluations").is_dir())
        self.assertTrue((self.tempdir / "delivery").is_dir())
        summary = load_state_summary(self.tempdir)
        self.assertEqual("codex", summary["adapter"])
        self.assertEqual("Phase 0: Intake", summary["current_phase"])

    def test_validate_checks_required_files(self) -> None:
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        result = validate_project(self.tempdir)
        self.assertTrue(result["ok"])
        self.assertEqual([], result["missing"])

    def test_prepare_phase_embeds_prompt_packet(self) -> None:
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        packet_path = prepare_phase(self.tempdir)
        packet = packet_path.read_text(encoding="utf-8")
        self.assertIn("Phase 0: Intake", packet)
        self.assertIn("references/prompts/intake.md", packet)
        self.assertIn("ASSUMPTIONS.md", packet)
        self.assertIn("Phase Prompt", packet)

    def test_prepare_swarm_run_creates_mirofish_bridge_contract(self) -> None:
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        chapters = self.tempdir / "manuscript" / "chapters"
        (chapters / "chapter-01.md").write_text("# Chapter 1\n\nText.\n", encoding="utf-8")
        run_dir = prepare_swarm_run(
            self.tempdir,
            slug="Launch Reaction",
            mode="public-opinion",
            run_date="2026-05-10",
        )
        self.assertEqual("2026-05-10-launch-reaction", run_dir.name)
        self.assertTrue((run_dir / "persona-roster.json").exists())
        self.assertTrue((run_dir / "mirofish-requirement.md").exists())
        sample_map = (run_dir / "sample-map.md").read_text(encoding="utf-8")
        self.assertIn("manuscript/chapters/chapter-01.md", sample_map)
        self.assertIn("public-opinion", sample_map)

    def test_prepare_agent_packet_creates_specialist_contract(self) -> None:
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        packet_path = prepare_agent_packet(self.tempdir, "pacing_engineer")
        packet = packet_path.read_text(encoding="utf-8")
        self.assertIn("Agent Packet: Pacing Engineer", packet)
        self.assertIn("8.5 pacing/opening target", packet)
        self.assertIn("artifacts/05-outline.md", packet)
        self.assertIn("skills/prose-craft/SKILL.md", packet)

    def test_advance_blocks_unfilled_templates(self) -> None:
        scaffold_project(self.tempdir, idea="seed idea", adapter="codex", model_name="gpt-5.5")
        result = advance_phase(self.tempdir)
        self.assertFalse(result["ok"])
        self.assertIn("ASSUMPTIONS.md", result["pending"])
        self.assertIn("artifacts/00-brief.md", result["pending"])

    def test_advance_moves_after_phase_outputs_are_filled(self) -> None:
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        for relative in [
            "ASSUMPTIONS.md",
            "artifacts/00-brief.md",
            "artifacts/01-market-map.md",
            "artifacts/02-story-engine.md",
        ]:
            path = self.tempdir / relative
            path.write_text(f"# Filled {relative}\n\nReal content.\n", encoding="utf-8")
        result = advance_phase(self.tempdir)
        summary = load_state_summary(self.tempdir)
        self.assertTrue(result["ok"])
        self.assertEqual("Phase 1: Foundation", summary["current_phase"])

    def test_demo_runs_to_completion(self) -> None:
        create_demo(self.tempdir, adapter="codex", model_name="gpt-5.5")
        summary = load_state_summary(self.tempdir)
        self.assertEqual("completed", summary["status"])
        self.assertTrue((self.tempdir / "manuscript" / "chapters" / "chapter-01.md").exists())
        self.assertIn("mechanical demo", (self.tempdir / "RUN_REPORT.md").read_text(encoding="utf-8"))

    def test_demo_passes_all_gates(self) -> None:
        # The demo must genuinely pass the deterministic gates (lint,
        # chronology, chapter order), not merely produce non-empty files --
        # that is the whole point of code-enforced gates existing.
        create_demo(self.tempdir, adapter="codex", model_name="gpt-5.5")
        gate_report = self.tempdir / "work" / "gate-report.md"
        self.assertTrue(gate_report.exists())
        text = gate_report.read_text(encoding="utf-8")
        self.assertIn("PASS", text)
        self.assertNotIn("FAIL", text)

    def test_advance_blocked_by_broken_chronology(self) -> None:
        # Drafting is the first phase with a "timeline" check. Fill its
        # outputs normally, then corrupt the timeline with a genuine
        # contradiction and confirm advance_phase refuses to advance.
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        for relative in [
            "ASSUMPTIONS.md",
            "artifacts/00-brief.md",
            "artifacts/01-market-map.md",
            "artifacts/02-story-engine.md",
        ]:
            (self.tempdir / relative).write_text(f"# Filled {relative}\n\nReal content.\n", encoding="utf-8")
        self.assertTrue(advance_phase(self.tempdir)["ok"])  # -> Phase 1

        for relative in ["artifacts/03-characters.md", "artifacts/04-theme.md", "artifacts/06-emotional-curve.md"]:
            (self.tempdir / relative).write_text(f"# Filled {relative}\n\nReal content.\n", encoding="utf-8")
        self.assertTrue(advance_phase(self.tempdir)["ok"])  # -> Phase 2

        for relative in ["artifacts/05-outline.md", "artifacts/07-opening-strategy.md"]:
            (self.tempdir / relative).write_text(f"# Filled {relative}\n\nReal content.\n", encoding="utf-8")
        self.assertTrue(advance_phase(self.tempdir)["ok"])  # -> Phase 3: Drafting

        chapters_dir = self.tempdir / "manuscript" / "chapters"
        chapters_dir.mkdir(parents=True, exist_ok=True)
        (chapters_dir / "chapter-01.md").write_text(
            "# Chapter 1\n\n"
            "A quiet morning passed without incident, the kind of ordinary "
            "hour that gives a reader room to breathe before the trouble "
            "starts down the road.\n",
            encoding="utf-8",
        )

        # A timeline with a genuine age contradiction: nine years pass
        # between two events, but the stated ages only differ by one.
        (self.tempdir / "TIMELINE.md").write_text(
            'event  id=start  day=0     label="Story opens"\n'
            'event  id=later  day=3287  label="Nine years later"\n\n'
            'age    person=kid  at=start  years=9   src="Ch1"\n'
            'age    person=kid  at=later  years=10  src="Ch1"\n',
            encoding="utf-8",
        )

        result = advance_phase(self.tempdir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("timeline" in item for item in result["failed_checks"]))

    def test_gate_reports_error_on_unknown_check_token(self) -> None:
        # A typo in the manifest's checks: list must block the gate, not
        # silently skip it.
        scaffold_project(self.tempdir, idea="", adapter="codex", model_name="gpt-5.5")
        phase = load_manifest()[0]
        broken_phase = type(phase)(
            key=phase.key, label=phase.label, prompt=phase.prompt, gate=phase.gate,
            outputs=[], next=phase.next, checks=["not_a_real_check"],
        )
        verdict = evaluate_gate(self.tempdir, broken_phase)
        self.assertFalse(verdict.ok)
        self.assertEqual(["error"], [r.status for r in verdict.results])

    def test_cli_init_runs_by_path(self) -> None:
        project = self.tempdir / "cli-project"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "runner" / "cli.py"),
                "init",
                str(project),
                "--idea",
                "a short test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, msg=result.stderr)
        self.assertTrue((project / "PROJECT_STATE.yaml").exists())


if __name__ == "__main__":
    unittest.main()
