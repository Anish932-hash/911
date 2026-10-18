"""Section 19.6 & Section 11: Automated tests for organic capability development and evaluation."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent911.capabilities import CapabilityContext
from agent911.capabilities.distill_ops import InstructionDistiller
from agent911.config import AgentConfig
from agent911.models import CapabilityAvailability, TaskOutcome
from agent911.orchestrator import Agent911Orchestrator


class TestCapabilityGrowth(unittest.TestCase):
    """Tests for Section 19.6: Organic capability development, verification, live testing, and persistence."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name)
        self.config = AgentConfig(workspace_root=str(self.workspace))
        self.orchestrator = Agent911Orchestrator(config=self.config)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_01_develop_register_discover_invoke_and_persist_capability(self) -> None:
        """
        Test developing a new capability ('text.metrics'), verifying it via AST/bytecode,
        exercising it via Live Run Testing, invoking it in a task, and reloading it across restart.
        """
        self.assertEqual(
            self.orchestrator.registry.get_availability("text.metrics"),
            CapabilityAvailability.NOT_IMPLEMENTED,
        )

        # Execute a task that requires 'text.metrics' (which does not exist yet!)
        sample_file = self.workspace / "article.txt"
        sample_file.write_text("Agent 911 builds working capabilities.\nSecond line here.\n", encoding="utf-8")

        task = self.orchestrator.execute_task(
            f"Compute word count and text metrics on '{sample_file.name}' using text.metrics"
        )
        self.assertEqual(task.final_outcome, TaskOutcome.SUCCESS)

        # Verify 'text.metrics' is now registered and AVAILABLE
        self.assertTrue(self.orchestrator.registry.has("text.metrics"))
        self.assertEqual(
            self.orchestrator.registry.get_availability("text.metrics"),
            CapabilityAvailability.AVAILABLE,
        )

        # Invoke the newly grown capability directly through the registry
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=self.orchestrator.model_interface,
            registry=self.orchestrator.registry,
            task_id="direct-invoke",
        )
        res = self.orchestrator.registry.invoke(
            "text.metrics", {"path": "article.txt"}, ctx
        )
        self.assertTrue(res.success)
        self.assertEqual(res.data["word_count"], 8)
        self.assertEqual(res.data["line_count"], 2)

        # Create a fresh Agent911Orchestrator instance to simulate process restart
        restarted_orch = Agent911Orchestrator(config=self.config)
        self.assertTrue(restarted_orch.registry.has("text.metrics"))
        self.assertEqual(
            restarted_orch.registry.get_availability("text.metrics"),
            CapabilityAvailability.AVAILABLE,
        )

    def test_02_broken_capability_rejected_by_verification_or_live_test(self) -> None:
        """
        Confirm that source code generation alone does NOT mark a capability operational
        if Verification or Live Run Testing fails.
        """
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=self.orchestrator.model_interface,
            registry=self.orchestrator.registry,
            task_id="bad-cap-test",
        )

        # 1. Syntax error in implementation_code -> fails Verification
        res_syntax = self.orchestrator.registry.invoke(
            "capability.develop",
            {
                "capability_id": "broken.syntax",
                "name": "Broken Syntax Cap",
                "purpose": "Should fail verification",
                "implementation_code": "def invalid python syntax(((",
            },
            ctx,
        )
        self.assertFalse(res_syntax.success)
        self.assertEqual(res_syntax.error_type, "CapabilityVerificationError")
        self.assertFalse(self.orchestrator.registry.has("broken.syntax"))

        # 2. Compiles cleanly (passes Verification), but raises RuntimeError during Live Run Testing
        res_runtime = self.orchestrator.registry.invoke(
            "capability.develop",
            {
                "capability_id": "broken.runtime",
                "name": "Broken Runtime Cap",
                "purpose": "Compiles but fails live runtime test",
                "implementation_code": "raise RuntimeError('runtime failure inside capability')",
                "test_params": {"x": 1},
            },
            ctx,
        )
        self.assertFalse(res_runtime.success)
        self.assertEqual(res_runtime.error_type, "CapabilityLiveTestError")
        self.assertTrue(res_runtime.data["verified"])
        self.assertFalse(res_runtime.data["live_tested"])
        self.assertFalse(res_runtime.data["operational"])
        # Failed candidates must never leak into the production registry.
        self.assertEqual(
            self.orchestrator.registry.get_availability("broken.runtime"),
            CapabilityAvailability.NOT_IMPLEMENTED,
        )
        self.assertFalse((self.config.capabilities_path / "cap_broken_runtime.py").exists())
        self.assertTrue(Path(res_runtime.data["workbench_path"]).exists())

    def test_03_unknown_offline_capability_does_not_get_a_placeholder(self) -> None:
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=self.orchestrator.model_interface,
            registry=self.orchestrator.registry,
            task_id="unsupported-offline-capability",
        )
        result = self.orchestrator.registry.invoke(
            "capability.develop",
            {
                "capability_id": "project.automate",
                "name": "Project Automation",
                "purpose": "Coordinate a multi-step project workflow",
            },
            ctx,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "CapabilityOracleRequired")
        self.assertFalse(self.orchestrator.registry.has("project.automate"))
        self.assertFalse((self.config.capabilities_path / "cap_project_automate.py").exists())

    def test_04_report_writing_does_not_turn_an_audit_into_an_artifact_build(self) -> None:
        spec = InstructionDistiller.distill(
            "Audit this project, run the tests, and write a report of the findings."
        )
        self.assertFalse(spec.is_build_intent)

    def test_05_skill_package_is_staged_validated_and_reports_behavioral_limit(self) -> None:
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=self.orchestrator.model_interface,
            registry=self.orchestrator.registry,
            task_id="skill-build",
        )
        markdown = (
            "---\nname: repo-auditor\n"
            "description: Review a repository and give an evidence-based quality report.\n"
            "---\n# Workflow\n\nInspect the repository files, identify important findings, "
            "run relevant checks, and report the exact evidence with paths."
        )
        result = self.orchestrator.registry.invoke(
            "skill.develop", {"skill_markdown": markdown}, ctx
        )
        self.assertTrue(result.success)
        self.assertTrue(result.data["structurally_valid"])
        self.assertFalse(result.data["behavior_tested"])
        self.assertFalse(result.data["operational"])
        self.assertTrue(Path(result.data["skill_path"]).is_file())
        self.assertTrue(Path(result.data["workbench_path"]).exists())

    def test_06_model_generation_repairs_with_failed_evidence_in_disposable_workspace(self) -> None:
        class FakeModel:
            def __init__(self) -> None:
                self.calls = []

            def generate(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    source = "not valid python !!!"
                else:
                    source = '''from typing import Any, Dict
from agent911.capabilities.base import Capability, CapabilityContext
from agent911.capabilities.filesystem import resolve_in_workspace
from agent911.models import CapabilityResult
class FixtureReadCapability(Capability):
    identifier = "fixture.read"
    name = "Fixture Reader"
    purpose = "Read a fixture from the disposable test workspace"
    input_schema = {"required": ["path"], "properties": {"path": {"type": "string"}}}
    output_format = {"content": "str"}
    is_custom_grown = True
    def execute(self, params: Dict[str, Any], context: CapabilityContext) -> CapabilityResult:
        p = resolve_in_workspace(context.workspace_path, params["path"])
        return CapabilityResult(capability_id=self.identifier, success=True, data={"content": p.read_text(encoding="utf-8")})
'''
                return SimpleNamespace(
                    structured_data={"implementation_code": source}, content=""
                )

        fake_model = FakeModel()
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=fake_model,
            registry=self.orchestrator.registry,
            task_id="model-capability-repair",
        )
        search_payload = {"web": {"results": [{
            "title": "Python Path Documentation",
            "url": "https://docs.python.org/3/library/pathlib.html",
            "description": "Official documentation for path operations.",
        }]}}

        class FakeSearchResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit: int) -> bytes:
                return json.dumps(search_payload).encode("utf-8")[:limit]

        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test-search-key"}), \
                patch("agent911.capabilities.web_research.urllib.request.urlopen", return_value=FakeSearchResponse()) as web_call:
            result = self.orchestrator.registry.invoke(
                "capability.develop",
                {
                    "capability_id": "fixture.read",
                    "name": "Fixture Reader",
                    "purpose": "Read a fixture from a dedicated test workspace",
                    "input_schema": {
                        "required": ["path"],
                        "properties": {"path": {"type": "string"}},
                    },
                    "test_params": {"path": "input.txt"},
                    "expected_test_output": {"content": "fixture-value"},
                    "test_workspace_files": {"input.txt": "fixture-value"},
                    "max_revisions": 1,
                },
                ctx,
            )
        self.assertTrue(result.success, result.error)
        self.assertEqual(len(fake_model.calls), 2)
        self.assertIn("failed_attempt_evidence", fake_model.calls[1]["context_payload"])
        research = fake_model.calls[0]["context_payload"]["technical_research"]
        self.assertEqual(research["status"], "searched")
        self.assertEqual(research["results"][0]["url"], "https://docs.python.org/3/library/pathlib.html")
        self.assertIn("untrusted", fake_model.calls[0]["system_prompt"].lower())
        self.assertEqual(web_call.call_count, 1, "one task should reuse its research results for repairs")
        self.assertIn("untrusted", fake_model.calls[0]["system_prompt"].lower())
        self.assertTrue(self.orchestrator.registry.has("fixture.read"))
        attempt_root = Path(result.data["workbench_path"])
        self.assertTrue((attempt_root / "attempt-01" / "evidence.json").exists())
        self.assertTrue((attempt_root / "attempt-01" / "repair-request.json").exists())
        self.assertTrue((attempt_root / "attempt-02" / "test-workspace" / "input.txt").exists())
        self.assertFalse((self.workspace / "input.txt").exists())

    def test_07_failed_model_generation_is_bounded_and_never_promoted(self) -> None:
        class AlwaysBadModel:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, **kwargs):
                self.calls += 1
                return SimpleNamespace(
                    structured_data={"implementation_code": "not valid python !!!"},
                    content="",
                )

        fake_model = AlwaysBadModel()
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=fake_model,
            registry=self.orchestrator.registry,
            task_id="model-capability-failure",
        )
        result = self.orchestrator.registry.invoke(
            "capability.develop",
            {
                "capability_id": "fixture.broken",
                "name": "Broken Fixture",
                "purpose": "A model-generated capability with explicit acceptance cases",
                "input_schema": {"required": [], "properties": {}},
                "test_params": {"value": 1},
                "expected_test_output": {"value": 1},
                "max_revisions": 1,
            },
            ctx,
        )
        self.assertFalse(result.success)
        self.assertEqual(fake_model.calls, 2)
        self.assertFalse(self.orchestrator.registry.has("fixture.broken"))
        self.assertFalse((self.config.capabilities_path / "cap_fixture_broken.py").exists())
        self.assertTrue((Path(result.data["workbench_path"]) / "attempt-02").exists())

    def test_08_skill_can_be_authored_from_spec_and_structurally_repaired(self) -> None:
        class FakeSkillModel:
            def __init__(self) -> None:
                self.calls = 0

            def generate(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    markdown = "not valid skill structure"
                else:
                    markdown = (
                        "---\nname: log-reviewer\n"
                        "description: Inspect logs, trace errors, and produce reproducible findings.\n"
                        "---\n# Procedure\n\nRead the relevant log files, group related errors, "
                        "confirm findings against source or test evidence, and report reproduction steps."
                    )
                return SimpleNamespace(
                    structured_data={"skill_markdown": markdown}, content=""
                )

        fake_model = FakeSkillModel()
        ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orchestrator.memory_store,
            model_interface=fake_model,
            registry=self.orchestrator.registry,
            task_id="skill-authoring",
        )
        result = self.orchestrator.registry.invoke(
            "skill.develop",
            {
                "skill_spec": "Create an agent skill for reviewing application logs and reporting verified issues.",
                "test_cases": [{"input": "logs with one exception", "expected": "trace and evidence"}],
                "max_revisions": 1,
            },
            ctx,
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(fake_model.calls, 2)
        self.assertFalse(result.data["behavior_tested"])
        workbench = Path(result.data["workbench_path"])
        self.assertTrue((workbench / "attempt-01" / "SKILL.md").exists())
        self.assertTrue((workbench / "attempt-02" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
