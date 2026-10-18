# Agent 911 — Windows Readiness & Cross-Platform CLI Architecture Report

## 1. Executive Summary
Agent 911 is a native, pure-Python instruction-driven AI agent designed for **Windows** (`cmd.exe`, PowerShell, Windows Terminal) and cross-platform CLI environments. It operates entirely without a browser or Node.js web server, providing both a structured command-line interface (`python -m agent911` / `python main.py`) and an interactive terminal console (`python -m agent911 console`).

## 2. Verified Windows Compatibility & Engineering Hardening

### 2.1 SQLite Connection Lifecycle & File Locking
- On Windows NTFS, open SQLite file handles block temporary directory cleanup (`PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`).
- `PersistentMemoryStore._connect()` wraps every SQLite transaction in a `@contextmanager` that explicitly calls `conn.close()` in a `finally` block, ensuring zero leaked database handles on Windows.

### 2.2 Private Credential Vault ACLs (`icacls` & `whoami`)
- Because `os.chmod(..., 0o600)` on Windows only toggles the read-only attribute rather than restricting multi-user access, `config._restrict_file_to_current_windows_user()` uses Windows ACLs (`icacls <path> /inheritance:r /grant:r *<SID>:F /q`) with `whoami /user /fo csv /nh` SID resolution and a fallback to `USERDOMAIN\USERNAME`.
- Subprocess calls set `creationflags=subprocess.CREATE_NO_WINDOW` on Windows so background ACL or command invocations never flash console windows.

### 2.3 Windows Path Normalization & Backslash Handling
- **Workspace Confinement**: `resolve_in_workspace()` resolves both Windows backslash paths (`subdir\module.py`) and POSIX paths (`subdir/module.py`) via `Path.resolve()` and enforces `candidate.is_relative_to(ws)`.
- **Normalized Relative Output**: All filesystem (`fs.list`, `fs.read`, `fs.write`, `fs.update`, `fs.mkdir`, `fs.stat`), project inspection (`project.inspect`), and instruction distillation (`intent.distill`) capabilities normalize workspace-relative output paths using `.as_posix()`.
- **Planner & Recovery Path Handling**: `TaskPlanner` and `RecoveryEngine` normalize `\` to `/` when inferring `fs.mkdir` step dependencies and recovering from `ParentDirectoryNotFoundError`.

### 2.4 Windows Command Execution & Executable Shim Resolution
- `RunCommandCapability` (`cmd.run`) uses `_split_command_args()` with `shlex.split(..., posix=False)` on Windows (`os.name == "nt"`) so backslashes in Windows file paths (`C:\Users\...` or `subdir\script.py`) are preserved instead of stripped as POSIX escape characters.
- `_resolve_executable_args()` maps `python`/`python3` to `sys.executable` on Windows (preventing Microsoft Store alias traps) and resolves `.cmd`, `.bat`, and `.exe` shims via `shutil.which()` while keeping `shell=False` for injection safety.

## 3. Verification & Test Suite Status
- All unit, integration, and end-to-end tests in `tests/` execute via `python -m unittest discover -s tests -v` with zero external web or Node.js dependencies.
