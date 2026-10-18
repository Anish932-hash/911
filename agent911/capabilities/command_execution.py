"""Command execution capability with timeout, workspace cwd, and real process output capture."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from agent911.capabilities.base import Capability, CapabilityContext
from agent911.capabilities.filesystem import (
    WorkspaceBoundaryError,
    resolve_in_workspace,
)
from agent911.models import CapabilityResult


def _split_command_args(raw_cmd: str) -> list[str]:
    """Split a command string while preserving Windows backslash paths when running on Windows."""
    if os.name == "nt":
        raw_tokens = shlex.split(raw_cmd, posix=False)
        cleaned: list[str] = []
        for tok in raw_tokens:
            if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
                cleaned.append(tok[1:-1])
            else:
                cleaned.append(tok)
        return cleaned
    return shlex.split(raw_cmd, posix=True)


def _resolve_executable_args(args: list[str]) -> list[str]:
    """Resolve executable shims (.cmd, .bat, .exe) and python3 alias on Windows."""
    if not args:
        return args
    resolved = list(args)
    exe = resolved[0]
    if os.name == "nt":
        if exe.lower() in ("python3", "python", "python.exe", "python3.exe"):
            resolved[0] = sys.executable
            return resolved
        if not Path(exe).is_absolute():
            which_path = shutil.which(exe)
            if which_path:
                resolved[0] = which_path
    return resolved


class RunCommandCapability(Capability):
    identifier = "cmd.run"
    name = "Execute Development Command"
    purpose = (
        "Execute a supported development command in the workspace and capture exit status, "
        "stdout, stderr, and timeout metadata."
    )
    input_schema = {
        "required": ["command"],
        "properties": {
            "command": {
                "description": "Command string or argument list to execute",
            },
            "cwd": {
                "type": "string",
                "description": "Relative working directory inside workspace (default '.')",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Maximum execution time in seconds",
            },
            "expected_exit_code": {
                "type": "integer",
                "description": "Expected exit code for success (default 0)",
            },
        },
    }
    output_format = {
        "command": "list[str] | str",
        "cwd": "str",
        "exit_code": "int | None",
        "stdout": "str",
        "stderr": "str",
        "timed_out": "bool",
        "duration_ms": "float",
    }

    def execute(self, params: dict[str, Any], context: CapabilityContext) -> CapabilityResult:
        raw_cmd = params["command"]
        rel_cwd = params.get("cwd", ".")
        timeout = float(params.get("timeout_seconds", context.config.command_timeout_seconds))
        expected_code = int(params.get("expected_exit_code", 0))

        if timeout <= 0:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error="timeout_seconds must be positive.",
                error_type="InputValidationError",
            )

        try:
            cwd_path = resolve_in_workspace(context.workspace_path, rel_cwd)
        except (WorkspaceBoundaryError, ValueError) as exc:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        if not cwd_path.exists() or not cwd_path.is_dir():
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Working directory does not exist: '{rel_cwd}'",
                error_type="FileNotFoundError",
            )

        if isinstance(raw_cmd, str):
            if not raw_cmd.strip():
                return CapabilityResult(
                    capability_id=self.identifier,
                    success=False,
                    error="Command string cannot be empty.",
                    error_type="InputValidationError",
                )
            try:
                args: list[str] = _split_command_args(raw_cmd)
            except ValueError as exc:
                return CapabilityResult(
                    capability_id=self.identifier,
                    success=False,
                    error=f"Malformed command string: {exc}",
                    error_type="InputValidationError",
                )
        elif isinstance(raw_cmd, list) and all(isinstance(x, str) for x in raw_cmd) and raw_cmd:
            args = list(raw_cmd)
        else:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error="Parameter 'command' must be a non-empty string or list of strings.",
                error_type="InputValidationError",
            )

        exec_args = _resolve_executable_args(args)
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        t0 = time.monotonic()
        try:
            completed = subprocess.run(
                exec_args,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                creationflags=no_window,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            succeeded = exit_code == expected_code

            data = {
                "command": args,
                "cwd": str(cwd_path),
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
                "duration_ms": elapsed_ms,
            }
            if succeeded:
                return CapabilityResult(
                    capability_id=self.identifier,
                    success=True,
                    data=data,
                    metadata={"duration_ms": elapsed_ms, "exit_code": exit_code},
                )
            err_msg = (
                f"Command exited with code {exit_code} (expected {expected_code}). "
                f"stderr: {stderr.strip()[:400] or stdout.strip()[:400]}"
            )
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                data=data,
                error=err_msg,
                error_type="CommandExecutionError",
                metadata={"duration_ms": elapsed_ms, "exit_code": exit_code},
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            stdout_str = (
                exc.stdout.decode("utf-8", errors="replace")
                if isinstance(exc.stdout, bytes)
                else (exc.stdout or "")
            )
            stderr_str = (
                exc.stderr.decode("utf-8", errors="replace")
                if isinstance(exc.stderr, bytes)
                else (exc.stderr or "")
            )
            data = {
                "command": args,
                "cwd": str(cwd_path),
                "exit_code": None,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "timed_out": True,
                "duration_ms": elapsed_ms,
            }
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                data=data,
                error=f"Command timed out after {timeout}s: {' '.join(args)}",
                error_type="TimeoutError",
                metadata={"duration_ms": elapsed_ms, "timed_out": True},
            )
        except FileNotFoundError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                data={
                    "command": args,
                    "cwd": str(cwd_path),
                    "exit_code": None,
                    "stdout": "",
                    "stderr": str(exc),
                    "timed_out": False,
                    "duration_ms": elapsed_ms,
                },
                error=f"Executable not found: '{args[0]}'",
                error_type="ExecutableNotFoundError",
                metadata={"duration_ms": elapsed_ms},
            )
        except OSError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"OS error running command '{args}': {exc}",
                error_type=type(exc).__name__,
                metadata={"duration_ms": elapsed_ms},
            )
