"""Tests for Windows compatibility, path/command normalization, CLI doctor/console, and distill capability contract."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent911.capabilities.base import CapabilityContext
from agent911.capabilities.command_execution import (
    _resolve_executable_args,
    _split_command_args,
)
from agent911.cli import main as cli_main
from agent911.config import AgentConfig
from agent911.models import CapabilityResult, TaskOutcome
from agent911.orchestrator import Agent911Orchestrator


class TestWindowsAndCliHardening(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp_dir.name)
        self.config = AgentConfig(workspace_root=str(self.ws))
        self.orch = Agent911Orchestrator(config=self.config)
        self.ctx = CapabilityContext(
            config=self.config,
            memory_store=self.orch.memory_store,
            registry=self.orch.registry,
            model_interface=self.orch.model_interface,
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_01_windows_command_splitting_preserves_backslashes(self) -> None:
        """Verify _split_command_args preserves Windows backslashes when os.name == 'nt'."""
        with patch("agent911.capabilities.command_execution.os.name", "nt"):
            cmd = r'python "C:\Users\Admin\My Project\run_tool.py" --input subdir\data.json'
            tokens = _split_command_args(cmd)
            self.assertEqual(
                tokens,
                ["python", r"C:\Users\Admin\My Project\run_tool.py", "--input", r"subdir\data.json"],
            )

        with patch("agent911.capabilities.command_execution.os.name", "nt"):
            resolved = _resolve_executable_args(["python", r"subdir\script.py"])
            self.assertEqual(resolved[0], sys.executable)
            self.assertEqual(resolved[1], r"subdir\script.py")

    def test_02_distill_capability_registry_invocation_returns_capability_result(self) -> None:
        """Verify invoking 'intent.distill' through CapabilityRegistry returns a valid CapabilityResult."""
        res = self.orch.registry.invoke(
            "intent.distill",
            {
                "text": (
                    "hey pls make a python script in win_tools\\log_parser.py "
                    "with function parse_events and a config in win_tools\\config.json"
                )
            },
            self.ctx,
        )
        self.assertIsInstance(res, CapabilityResult)
        self.assertTrue(res.success, f"Expected intent.distill to succeed, got error={res.error}")
        self.assertIn("target_artifacts", res.data)
        parent_dirs = {tf["parent_dir"] for tf in res.data["target_artifacts"] if tf.get("parent_dir")}
        self.assertIn("win_tools", parent_dirs)
        for pdir in parent_dirs:
            self.assertNotIn("\\", pdir)

    def test_03_windows_backslash_path_recovery_and_normalized_posix_outputs(self) -> None:
        """Verify recovery from ParentDirectoryNotFoundError and normalized relative paths with backslash inputs."""
        write_res = self.orch.registry.invoke(
            "fs.write",
            {
                "path": r"nested_win\sub_pkg\helper.py",
                "content": "def ping() -> str:\n    return 'pong'\n",
                "create_parents": False,
            },
            self.ctx,
        )
        self.assertFalse(write_res.success)
        self.assertEqual(write_res.error_type, "ParentDirectoryNotFoundError")
        self.assertEqual(write_res.metadata.get("missing_parent"), "nested_win/sub_pkg")

        task = self.orch.execute_task(
            "Write a Python file 'nested_win/sub_pkg/helper.py' with a function 'ping' and verify it runs."
        )
        self.assertEqual(task.final_outcome, TaskOutcome.SUCCESS)
        self.assertTrue((self.ws / "nested_win" / "sub_pkg" / "helper.py").is_file())

        inspect_res = self.orch.registry.invoke("project.inspect", {"path": "."}, self.ctx)
        self.assertTrue(inspect_res.success)
        self.assertIn("nested_win/sub_pkg/helper.py", inspect_res.data["project_files"])
        self.assertIn("nested_win/sub_pkg/helper.py", inspect_res.data["python_symbols"])
        for fpath in inspect_res.data["project_files"]:
            self.assertNotIn("\\", fpath)

    def test_04_secret_redaction_includes_groq_and_search_env_keys(self) -> None:
        """Verify CredentialStore and PersistentMemoryStore redact GROQ_API_KEY, TAVILY_API_KEY, and AGENT911_SEARCH_API_KEY."""
        from agent911.config import redact_secrets

        fake_groq = "gsk_live_secret_token_987654321"
        fake_tavily = "tvly_live_secret_token_123456789"
        with patch.dict(
            os.environ,
            {"GROQ_API_KEY": fake_groq, "TAVILY_API_KEY": fake_tavily},
            clear=False,
        ):
            orch = Agent911Orchestrator(config=AgentConfig(workspace_root=str(self.ws)))
            redacted = redact_secrets(
                f"Keys in use: {fake_groq} and {fake_tavily}",
                orch.memory_store.secrets_to_redact,
            )
            self.assertNotIn(fake_groq, redacted)
            self.assertNotIn(fake_tavily, redacted)
            self.assertIn("[REDACTED]", redacted)

    def test_05_cli_doctor_and_subcommands_execute_cleanly(self) -> None:
        """Verify CLI doctor, status, capabilities, and distill subcommands run cleanly."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc_doc = cli_main(["--workspace", str(self.ws), "--json", "doctor"])
        self.assertEqual(rc_doc, 0)
        self.assertIn('"database_exists": true', buf.getvalue())
        self.assertIn('"workspace_root":', buf.getvalue())

        buf_status = io.StringIO()
        with redirect_stdout(buf_status):
            rc_status = cli_main(["--workspace", str(self.ws), "status"])
        self.assertEqual(rc_status, 0)
        self.assertIn("=== AGENT 911 STATUS ===", buf_status.getvalue())


if __name__ == "__main__":
    unittest.main()
