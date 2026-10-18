"""Main entry point for Agent 911 CLI & Interactive Terminal Console (Windows & Cross-Platform)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent911.cli import main as cli_main
from agent911.config import AgentConfig
from agent911.orchestrator import Agent911Orchestrator


def _run_headless_diagnostic_showcase() -> int:
    """
    Execute a live non-destructive diagnostic and verification showcase when launched
    without arguments in a non-interactive terminal environment.
    """
    print("================================================================================")
    print("  AGENT 911 — INSTRUCTION-DRIVEN, SELF-EXPANDING AI AGENT (WINDOWS & CLI EDITION)")
    print("================================================================================\n")

    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        rc = cli_main(["--workspace", str(ws), "doctor"])
        print()
        cli_main(["--workspace", str(ws), "capabilities"])

        print("\n=== LIVE SELF-TEST: TASK EXECUTION + VERIFICATION + LIVE RUN TESTING ===")
        cfg = AgentConfig(workspace_root=str(ws))
        orch = Agent911Orchestrator(config=cfg)
        task = orch.execute_task(
            "Write a Python file 'win_diag/check_calc.py' with a function 'calculate_total' and run it."
        )
        print(f"Task ID              : {task.task_id}")
        print(f"Instruction          : {task.original_instruction}")
        print(f"Selected Strategy    : {task.selected_strategy}")
        print(f"Recovery Attempts    : {len(task.recovery_attempts)} (auto-created missing parent dir)")
        print(
            f"Verification Checks  : {sum(1 for v in task.verification_results if v.status.value == 'PASSED')}"
            f"/{len(task.verification_results)} PASSED"
        )
        print(
            f"Live Run Tests       : {sum(1 for l in task.live_run_results if l.status.value == 'PASSED')}"
            f"/{len(task.live_run_results)} PASSED"
        )
        print(f"Final Task Outcome   : {task.final_outcome.value}")

    print("\n=== CLI QUICK REFERENCE (Windows PowerShell / CMD / Terminal) ===")
    print("  python main.py console                           # Launch interactive terminal console")
    print("  python -m agent911 doctor                        # Run Windows & system readiness check")
    print("  python -m agent911 status                        # Show config, model & SQLite status")
    print("  python -m agent911 run \"<instruction>\"           # Execute a task with Verification & Live Testing")
    print("  python -m agent911 distill \"<messy text>\"        # Distill informal writing into concrete build spec")
    print("  python -m agent911 capabilities                  # List registered & custom-grown capabilities")
    print("  python -m agent911 proposals --detect            # Detect self-improvement proposals from history")
    print("  python -m unittest discover -s tests -v          # Run full automated test suite")
    return rc


def main(argv: list[str] | None = None) -> int:
    effective_args = sys.argv[1:] if argv is None else argv
    if not effective_args and not sys.stdin.isatty():
        return _run_headless_diagnostic_showcase()
    return cli_main(effective_args)


if __name__ == "__main__":
    sys.exit(main())
