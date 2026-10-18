"""Workspace code/AST search, snapshot/diff/restore, and safe file deletion capabilities."""

from __future__ import annotations

import ast
import difflib
import fnmatch
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from agent911.capabilities.base import Capability, CapabilityContext
from agent911.capabilities.filesystem import WorkspaceBoundaryError, resolve_in_workspace
from agent911.models import CapabilityResult, new_id, utc_now_iso

_IGNORED_DIRS = {
    ".git",
    ".agent911",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _iter_workspace_files(root: Path, file_glob: str = "*") -> list[Path]:
    """Return sorted workspace files matching file_glob, skipping ignored/internal directories."""
    results: list[Path] = []
    for item in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not item.is_file():
            continue
        rel = item.relative_to(root)
        if any(part in _IGNORED_DIRS for part in rel.parts):
            continue
        if file_glob and file_glob != "*":
            if not (
                fnmatch.fnmatch(item.name, file_glob)
                or fnmatch.fnmatch(rel.as_posix(), file_glob)
            ):
                continue
        results.append(item)
    return results


class SearchWorkspaceCapability(Capability):
    identifier = "code.search"
    name = "Search Workspace Code & Symbols"
    purpose = (
        "Search workspace files by text/regex pattern or Python AST symbol (functions, classes, methods) "
        "with line numbers and surrounding context."
    )
    input_schema = {
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "Search pattern or AST symbol name to locate in workspace.",
            },
            "path": {
                "type": "string",
                "description": "Relative directory or file path inside workspace (default '.').",
            },
            "mode": {
                "type": "string",
                "description": "Search mode: 'pattern' (text/regex) or 'symbol' (Python AST defs). Default 'pattern'.",
            },
            "file_glob": {
                "type": "string",
                "description": "Optional filename glob filter such as '*.py' or '*.json' (default '*').",
            },
            "is_regex": {
                "type": "boolean",
                "description": "Interpret query as a regular expression in 'pattern' mode (default False).",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Perform case-sensitive matching (default False).",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of surrounding context lines to include (0-5, default 1).",
            },
            "max_matches": {
                "type": "integer",
                "description": "Maximum number of matches to return (1-200, default 50).",
            },
        },
    }

    def execute(
        self, params: dict[str, Any], context: CapabilityContext
    ) -> CapabilityResult:
        query = str(params.get("query", "")).strip()
        if not query:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error="Parameter 'query' must be a non-empty string.",
                error_type="ValueError",
            )

        rel_path = str(params.get("path", ".")).strip() or "."
        mode = str(params.get("mode", "pattern")).strip().lower() or "pattern"
        file_glob = str(params.get("file_glob", "*")).strip() or "*"
        is_regex = bool(params.get("is_regex", False))
        case_sensitive = bool(params.get("case_sensitive", False))
        context_lines = max(0, min(5, int(params.get("context_lines", 1))))
        max_matches = max(1, min(200, int(params.get("max_matches", 50))))

        if mode not in ("pattern", "symbol"):
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Unsupported search mode '{mode}'. Expected 'pattern' or 'symbol'.",
                error_type="ValueError",
            )

        try:
            target = resolve_in_workspace(context.workspace_path, rel_path)
        except (WorkspaceBoundaryError, ValueError) as exc:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        if not target.exists():
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Search path '{rel_path}' does not exist in workspace.",
                error_type="FileNotFoundError",
            )

        ws = context.workspace_path.resolve()
        candidate_files = (
            [target]
            if target.is_file()
            else _iter_workspace_files(target, file_glob=file_glob)
        )

        if mode == "symbol":
            return self._search_ast_symbols(
                ws=ws,
                files=candidate_files,
                query=query,
                case_sensitive=case_sensitive,
                max_matches=max_matches,
            )

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(query if is_regex else re.escape(query), flags)
        except re.error as exc:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Invalid regular expression '{query}': {exc}",
                error_type="RegexError",
            )

        matches: list[dict[str, Any]] = []
        files_searched = 0
        files_with_matches = 0

        for fpath in candidate_files:
            try:
                if fpath.stat().st_size > 1_000_000:
                    continue
                raw_bytes = fpath.read_bytes()
                if b"\x00" in raw_bytes[:1024]:
                    continue
                text = raw_bytes.decode("utf-8", errors="replace")
            except OSError:
                continue

            files_searched += 1
            lines = text.splitlines()
            file_matched = False
            rel_posix = fpath.relative_to(ws).as_posix()

            for idx, line in enumerate(lines):
                if pattern.search(line):
                    file_matched = True
                    start_ctx = max(0, idx - context_lines)
                    end_ctx = min(len(lines), idx + context_lines + 1)
                    snippet = [
                        {"line_number": i + 1, "text": lines[i]}
                        for i in range(start_ctx, end_ctx)
                    ]
                    matches.append(
                        {
                            "file": rel_posix,
                            "line_number": idx + 1,
                            "line": line.strip(),
                            "context": snippet,
                        }
                    )
                    if len(matches) >= max_matches:
                        break

            if file_matched:
                files_with_matches += 1
            if len(matches) >= max_matches:
                break

        return CapabilityResult(
            capability_id=self.identifier,
            success=True,
            data={
                "query": query,
                "mode": mode,
                "file_glob": file_glob,
                "files_searched": files_searched,
                "files_with_matches": files_with_matches,
                "match_count": len(matches),
                "matches": matches,
            },
        )

    def _search_ast_symbols(
        self,
        ws: Path,
        files: list[Path],
        query: str,
        case_sensitive: bool,
        max_matches: int,
    ) -> CapabilityResult:
        q_norm = query if case_sensitive else query.lower()
        matches: list[dict[str, Any]] = []
        files_searched = 0

        for fpath in files:
            if fpath.suffix.lower() != ".py":
                continue
            try:
                src = fpath.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(src, filename=fpath.name)
            except Exception:
                continue

            files_searched += 1
            rel_posix = fpath.relative_to(ws).as_posix()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name_cmp = node.name if case_sensitive else node.name.lower()
                    if q_norm in name_cmp:
                        kind = (
                            "class"
                            if isinstance(node, ast.ClassDef)
                            else (
                                "async_function"
                                if isinstance(node, ast.AsyncFunctionDef)
                                else "function"
                            )
                        )
                        args_list: list[str] = []
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            args_list = [a.arg for a in node.args.args]
                        doc = ast.get_docstring(node) or ""
                        matches.append(
                            {
                                "file": rel_posix,
                                "symbol": node.name,
                                "kind": kind,
                                "line_number": getattr(node, "lineno", 1),
                                "end_line_number": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                                "parameters": args_list,
                                "docstring_summary": doc.splitlines()[0].strip() if doc else "",
                            }
                        )
                        if len(matches) >= max_matches:
                            break
            if len(matches) >= max_matches:
                break

        return CapabilityResult(
            capability_id=self.identifier,
            success=True,
            data={
                "query": query,
                "mode": "symbol",
                "files_searched": files_searched,
                "match_count": len(matches),
                "matches": matches,
            },
        )


class WorkspaceSnapshotCapability(Capability):
    identifier = "workspace.snapshot"
    name = "Workspace Snapshot, Diff & Restore"
    purpose = (
        "Create lightweight workspace checkpoints, inspect unified diffs between a snapshot and current files, "
        "list saved snapshots, or restore workspace files to a checkpoint."
    )
    input_schema = {
        "required": ["action"],
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform: 'create', 'list', 'diff', or 'restore'.",
            },
            "snapshot_id": {
                "type": "string",
                "description": "Snapshot identifier (required for 'diff' and 'restore'; optional for 'create').",
            },
            "label": {
                "type": "string",
                "description": "Optional human-readable label when creating a snapshot.",
            },
            "clean_untracked": {
                "type": "boolean",
                "description": "When restoring, remove workspace files created after the snapshot (default False).",
            },
        },
    }

    def _snapshots_root(self, context: CapabilityContext) -> Path:
        root = context.config.data_path / "snapshots"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def execute(
        self, params: dict[str, Any], context: CapabilityContext
    ) -> CapabilityResult:
        action = str(params.get("action", "")).strip().lower()
        if action not in ("create", "list", "diff", "restore"):
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Unsupported snapshot action '{action}'. Expected 'create', 'list', 'diff', or 'restore'.",
                error_type="ValueError",
            )

        ws = context.workspace_path.resolve()
        snapshots_root = self._snapshots_root(context)

        if action == "create":
            snap_id = str(params.get("snapshot_id", "")).strip() or new_id("snap")
            snap_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", snap_id)
            label = str(params.get("label", "")).strip() or "Workspace checkpoint"
            snap_dir = snapshots_root / snap_id
            files_dir = snap_dir / "files"
            if snap_dir.exists():
                shutil.rmtree(snap_dir)
            files_dir.mkdir(parents=True, exist_ok=True)

            tracked: dict[str, dict[str, Any]] = {}
            for fpath in _iter_workspace_files(ws):
                try:
                    if fpath.stat().st_size > 2_000_000:
                        continue
                    rel_posix = fpath.relative_to(ws).as_posix()
                    data = fpath.read_bytes()
                    dest = files_dir / rel_posix
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                    tracked[rel_posix] = {
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size_bytes": len(data),
                    }
                except OSError:
                    continue

            manifest = {
                "snapshot_id": snap_id,
                "label": label,
                "created_at": utc_now_iso(),
                "workspace_root": str(ws),
                "file_count": len(tracked),
                "files": tracked,
            }
            (snap_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            return CapabilityResult(
                capability_id=self.identifier,
                success=True,
                data={
                    "action": "create",
                    "snapshot_id": snap_id,
                    "label": label,
                    "created_at": manifest["created_at"],
                    "file_count": len(tracked),
                    "files": sorted(tracked.keys()),
                },
            )

        if action == "list":
            snapshots: list[dict[str, Any]] = []
            for mfile in sorted(snapshots_root.glob("*/manifest.json")):
                try:
                    m = json.loads(mfile.read_text(encoding="utf-8"))
                    snapshots.append(
                        {
                            "snapshot_id": m.get("snapshot_id", mfile.parent.name),
                            "label": m.get("label", ""),
                            "created_at": m.get("created_at", ""),
                            "file_count": m.get("file_count", 0),
                        }
                    )
                except Exception:
                    continue
            return CapabilityResult(
                capability_id=self.identifier,
                success=True,
                data={
                    "action": "list",
                    "snapshot_count": len(snapshots),
                    "snapshots": snapshots,
                },
            )

        snap_id = str(params.get("snapshot_id", "")).strip()
        if not snap_id:
            # Default to most recent snapshot if not explicitly provided
            manifests = sorted(snapshots_root.glob("*/manifest.json"))
            if not manifests:
                return CapabilityResult(
                    capability_id=self.identifier,
                    success=False,
                    error="No snapshot_id provided and no saved snapshots exist.",
                    error_type="FileNotFoundError",
                )
            snap_id = manifests[-1].parent.name

        snap_dir = snapshots_root / snap_id
        manifest_file = snap_dir / "manifest.json"
        if not manifest_file.is_file():
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Snapshot '{snap_id}' does not exist.",
                error_type="FileNotFoundError",
            )

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        snap_files: dict[str, dict[str, Any]] = manifest.get("files", {})
        files_dir = snap_dir / "files"

        if action == "diff":
            current_files = {
                p.relative_to(ws).as_posix(): p for p in _iter_workspace_files(ws)
            }
            added = sorted(set(current_files.keys()) - set(snap_files.keys()))
            deleted = sorted(set(snap_files.keys()) - set(current_files.keys()))
            modified: list[str] = []
            unchanged: list[str] = []
            unified_diffs: dict[str, str] = {}

            for rel_posix, meta in sorted(snap_files.items()):
                if rel_posix not in current_files:
                    continue
                cur_path = current_files[rel_posix]
                cur_bytes = cur_path.read_bytes()
                cur_sha = hashlib.sha256(cur_bytes).hexdigest()
                if cur_sha == meta.get("sha256"):
                    unchanged.append(rel_posix)
                else:
                    modified.append(rel_posix)
                    old_path = files_dir / rel_posix
                    if old_path.is_file():
                        old_lines = old_path.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines(keepends=True)
                        new_lines = cur_bytes.decode(
                            "utf-8", errors="replace"
                        ).splitlines(keepends=True)
                        diff_text = "".join(
                            difflib.unified_diff(
                                old_lines,
                                new_lines,
                                fromfile=f"snapshot:{snap_id}/{rel_posix}",
                                tofile=f"workspace/{rel_posix}",
                            )
                        )
                        unified_diffs[rel_posix] = diff_text

            return CapabilityResult(
                capability_id=self.identifier,
                success=True,
                data={
                    "action": "diff",
                    "snapshot_id": snap_id,
                    "modified": modified,
                    "added": added,
                    "deleted": deleted,
                    "unchanged_count": len(unchanged),
                    "has_changes": bool(modified or added or deleted),
                    "unified_diffs": unified_diffs,
                },
            )

        # action == "restore"
        clean_untracked = bool(params.get("clean_untracked", False))
        restored_files: list[str] = []
        removed_files: list[str] = []

        for rel_posix in sorted(snap_files.keys()):
            src = files_dir / rel_posix
            if not src.is_file():
                continue
            dest = resolve_in_workspace(ws, rel_posix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            restored_files.append(rel_posix)

        if clean_untracked:
            for cur_path in _iter_workspace_files(ws):
                rel_posix = cur_path.relative_to(ws).as_posix()
                if rel_posix not in snap_files:
                    try:
                        cur_path.unlink()
                        removed_files.append(rel_posix)
                    except OSError:
                        pass

        return CapabilityResult(
            capability_id=self.identifier,
            success=True,
            data={
                "action": "restore",
                "snapshot_id": snap_id,
                "restored_count": len(restored_files),
                "restored_files": restored_files,
                "removed_untracked_files": removed_files,
            },
        )


class DeleteFileCapability(Capability):
    identifier = "fs.delete"
    name = "Delete Workspace File"
    purpose = "Safely delete a file or empty directory within the configured workspace boundary."
    input_schema = {
        "required": ["path"],
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path of the file or empty directory to delete inside workspace.",
            },
        },
    }

    def execute(
        self, params: dict[str, Any], context: CapabilityContext
    ) -> CapabilityResult:
        req_path = str(params.get("path", "")).strip()
        try:
            target = resolve_in_workspace(context.workspace_path, req_path)
        except (WorkspaceBoundaryError, ValueError) as exc:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        ws = context.workspace_path.resolve()
        if target == ws:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error="Refusing to delete the workspace root directory.",
                error_type="PermissionError",
            )

        rel_posix = target.relative_to(ws).as_posix()
        if rel_posix.startswith(".agent911"):
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error="Refusing to delete internal '.agent911' state via fs.delete.",
                error_type="PermissionError",
            )

        if not target.exists():
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"File or directory '{req_path}' does not exist in workspace.",
                error_type="FileNotFoundError",
            )

        try:
            if target.is_dir():
                target.rmdir()
                return CapabilityResult(
                    capability_id=self.identifier,
                    success=True,
                    data={"deleted_path": rel_posix, "type": "directory"},
                )
            data = target.read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            size = len(data)
            target.unlink()
            return CapabilityResult(
                capability_id=self.identifier,
                success=True,
                data={
                    "deleted_path": rel_posix,
                    "type": "file",
                    "size_bytes": size,
                    "sha256": sha,
                },
            )
        except OSError as exc:
            return CapabilityResult(
                capability_id=self.identifier,
                success=False,
                error=f"Failed to delete '{req_path}': {exc}",
                error_type=type(exc).__name__,
            )
