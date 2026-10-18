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

    def test_06_code_search_pattern_and_ast_symbol_modes(self) -> None:
        """Verify code.search finds text/regex matches and Python AST symbols with line numbers."""
        src_dir = self.ws / "services"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "invoice.py").write_text(
            '"""Invoice calculation module."""\n\n'
            "class InvoiceEngine:\n"
            "    pass\n\n"
            "def compute_invoice_tax(amount: float, rate: float = 0.18) -> float:\n"
            '    """Calculate tax for an invoice."""\n'
            "    return round(amount * rate, 2)\n",
            encoding="utf-8",
        )

        # 1. Pattern search
        pat_res = self.orch.registry.invoke(
            "code.search",
            {"query": "round(amount * rate", "mode": "pattern", "file_glob": "*.py"},
            self.ctx,
        )
        self.assertTrue(pat_res.success)
        self.assertEqual(pat_res.data["match_count"], 1)
        self.assertEqual(pat_res.data["matches"][0]["file"], "services/invoice.py")
        self.assertEqual(pat_res.data["matches"][0]["line_number"], 8)

        # 2. AST symbol search
        sym_res = self.orch.registry.invoke(
            "code.search",
            {"query": "compute_invoice_tax", "mode": "symbol"},
            self.ctx,
        )
        self.assertTrue(sym_res.success)
        self.assertEqual(sym_res.data["match_count"], 1)
        match = sym_res.data["matches"][0]
        self.assertEqual(match["file"], "services/invoice.py")
        self.assertEqual(match["symbol"], "compute_invoice_tax")
        self.assertEqual(match["kind"], "function")
        self.assertEqual(match["parameters"], ["amount", "rate"])

        # 3. Natural language task execution via TaskPlanner
        task = self.orch.execute_task("Find symbol 'InvoiceEngine'")
        self.assertEqual(task.final_outcome, TaskOutcome.SUCCESS)

    def test_07_workspace_snapshot_create_diff_and_restore(self) -> None:
        """Verify workspace.snapshot creates checkpoints, computes unified diffs, and restores files."""
        app_file = self.ws / "config_state.py"
        app_file.write_text("VERSION = 1\nMODE = 'stable'\n", encoding="utf-8")

        # 1. Create snapshot
        create_res = self.orch.registry.invoke(
            "workspace.snapshot",
            {"action": "create", "snapshot_id": "snap-v1", "label": "Version 1"},
            self.ctx,
        )
        self.assertTrue(create_res.success)
        self.assertEqual(create_res.data["snapshot_id"], "snap-v1")
        self.assertIn("config_state.py", create_res.data["files"])

        # 2. Modify file and add an untracked file
        app_file.write_text("VERSION = 2\nMODE = 'experimental'\n", encoding="utf-8")
        extra_file = self.ws / "temp_scratch.txt"
        extra_file.write_text("temporary data\n", encoding="utf-8")

        # 3. Diff against snapshot
        diff_res = self.orch.registry.invoke(
            "workspace.snapshot",
            {"action": "diff", "snapshot_id": "snap-v1"},
            self.ctx,
        )
        self.assertTrue(diff_res.success)
        self.assertTrue(diff_res.data["has_changes"])
        self.assertIn("config_state.py", diff_res.data["modified"])
        self.assertIn("temp_scratch.txt", diff_res.data["added"])
        self.assertIn("-VERSION = 1", diff_res.data["unified_diffs"]["config_state.py"])
        self.assertIn("+VERSION = 2", diff_res.data["unified_diffs"]["config_state.py"])

        # 4. Restore snapshot with clean_untracked=True
        restore_res = self.orch.registry.invoke(
            "workspace.snapshot",
            {"action": "restore", "snapshot_id": "snap-v1", "clean_untracked": True},
            self.ctx,
        )
        self.assertTrue(restore_res.success)
        self.assertEqual(app_file.read_text(encoding="utf-8"), "VERSION = 1\nMODE = 'stable'\n")
        self.assertFalse(extra_file.exists())

    def test_08_safe_file_deletion_and_boundary_protection(self) -> None:
        """Verify fs.delete removes target workspace files and blocks deleting .agent911 or outside workspace."""
        target = self.ws / "obsolete.txt"
        target.write_text("remove me", encoding="utf-8")

        del_res = self.orch.registry.invoke("fs.delete", {"path": "obsolete.txt"}, self.ctx)
        self.assertTrue(del_res.success)
        self.assertFalse(target.exists())
        self.assertEqual(del_res.data["deleted_path"], "obsolete.txt")

        # Refuse deleting internal .agent911 state
        internal_res = self.orch.registry.invoke(
            "fs.delete", {"path": ".agent911/agent911.db"}, self.ctx
        )
        self.assertFalse(internal_res.success)
        self.assertEqual(internal_res.error_type, "PermissionError")


if __name__ == "__main__":
    unittest.main()

