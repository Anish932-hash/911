"""Regression tests for placeholder prevention and evidence-based task claims."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent911.capabilities.base import CapabilityContext
from agent911.capabilities.distill_ops import InstructionDistiller
from agent911.capabilities.experience_ops import RecordExperienceCapability
from agent911.config import AgentConfig
from agent911.model_provider import ModelProviderError
from agent911.models import (
    ActionStatus,
    PlannedAction,
    TaskOutcome,
    TaskState,
    VerificationStatus,
)
from agent911.orchestrator import Agent911Orchestrator


class TestAgentTruthfulness(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.config = AgentConfig(workspace_root=str(self.workspace))
        self.agent = Agent911Orchestrator(config=self.config)
        self.context = CapabilityContext(
            config=self.config,
            memory_store=self.agent.memory_store,
            model_interface=self.agent.model_interface,
            registry=self.agent.registry,
            task_id="task-under-test",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_fs_write_refuses_placeholder_content_without_creating_file(self) -> None:
        result = self.agent.registry.invoke(
            "fs.write", {"path": "artifact.py", "content": "<PLACEHOLDER>"}, self.context
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "PlaceholderContentError")
        self.assertFalse((self.workspace / "artifact.py").exists())

    def test_fs_update_refuses_placeholder_without_mutating_file(self) -> None:
        target = self.workspace / "artifact.py"
        target.write_text("print('real content')\n", encoding="utf-8")

        result = self.agent.registry.invoke(
            "fs.update",
            {"path": "artifact.py", "append_text": "TODO: fill this in"},
            self.context,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "PlaceholderContentError")
        self.assertEqual(target.read_text(encoding="utf-8"), "print('real content')\n")

    def test_failed_task_response_does_not_claim_deliverables_work(self) -> None:
        task = TaskState(
            task_id="failed-task",
            original_instruction="Build and test a tool",
            final_outcome=TaskOutcome.FAILED,
            outcome_summary="Task FAILED: live test failed.",
            planned_actions=[
                PlannedAction(
                    step_id="write",
                    description="Write tool",
                    capability_id="fs.write",
                    status=ActionStatus.COMPLETED,
                )
            ],
            relevant_outputs={"write": {"path": "tool.py"}},
        )

        self.agent._populate_assistant_response(task)

        self.assertIn("FAILED", task.assistant_response)
        self.assertIn("unverified", task.assistant_response)
        self.assertNotIn("put it together", task.assistant_response)
        self.assertNotIn("Created **", task.assistant_response)

    def test_inflight_experience_cannot_claim_verified_success(self) -> None:
        result = RecordExperienceCapability().execute(
            {
                "task_id": self.context.task_id,
                "objective": "Build a working tool",
                "plan_summary": "Everything worked.",
                "outcome": "SUCCESS",
                "verification_summary": {"passed": 2, "failed": 0},
                "live_test_summary": {"passed": 1, "failed": 0},
            },
            self.context,
        )

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["outcome"], "UNVERIFIED")
        self.assertEqual(result.data["lesson_confidence"], "UNVERIFIED_CLAIM")

    def test_oversized_execution_logs_remain_valid_json_and_inspectable(self) -> None:
        self.agent.memory_store.record_execution_log(
            task_id="large-log-task",
            operation="large output",
            success=True,
            output_data={"text": "x" * 10000},
        )

        logs = self.agent.memory_store.get_execution_logs("large-log-task")

        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0]["output"]["_truncated"])
        self.assertGreater(logs[0]["output"]["original_characters"], 4000)

    def test_polite_formal_build_request_is_not_misclassified_as_messy(self) -> None:
        spec = InstructionDistiller.distill(
            "Please build a tax calculator that calculates tax and applies discounts."
        )

        self.assertTrue(spec.is_build_intent)
        self.assertFalse(spec.is_messy_input)

    def test_complex_build_after_model_failure_cannot_be_reported_as_verified(self) -> None:
        task = TaskState(
            task_id="fallback-build",
            original_instruction=(
                "Build a tax calculator that calculates tax, applies discounts, "
                "and validates inputs."
            ),
        )
        planner = self.agent.planner
        planner._should_try_model = lambda _instruction: True

        def fail_model(_task, _context):
            raise ModelProviderError("provider offline", error_type="http_error")

        planner._plan_via_model = fail_model
        planner.understand_and_plan(task, {})

        review_requirement = next(
            req for req in task.requirements if req.category == "ai_assertion"
        )
        verification = self.agent.verifier.verify_requirement(task, review_requirement)

        self.assertEqual(verification.status, VerificationStatus.INCONCLUSIVE)
        self.assertIn("model planning was unavailable", review_requirement.description)


if __name__ == "__main__":
    unittest.main()
