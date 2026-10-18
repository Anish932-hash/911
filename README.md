# Agent 911 — Instruction-Driven, Self-Expanding AI Agent (Windows & Cross-Platform CLI)

Agent 911 is a complete, from-scratch Python AI agent engineered for **Windows** (PowerShell, Command Prompt, Windows Terminal) and POSIX terminals. It understands natural-language instructions (including messy, informal brainstorms), plans and executes real work through registered capabilities, verifies outcomes using **Verification** and **Live Run Testing**, retains persistent SQLite memory and experience across restarts, recovers from step failures, and grows new capabilities organically.

---

## 1. Architecture & Core Principles

Agent 911 operates as a cohesive, zero-web-dependency Python application (`agent911/` and `main.py`) without any Guardian or redundant approval layer:

```
USER INSTRUCTION
       |
       v
INTENT UNDERSTANDING & MESSY-WRITING DISTILLATION (agent911/planner.py, distill_ops.py)
       |
       v
CONTEXT & PERSISTENT MEMORY RETRIEVAL (agent911/context.py, memory.py)
       |
       v
TASK REPRESENTATION & PROPORTIONAL PLANNING (agent911/models.py, planner.py, strategy.py)
       |
       v
CAPABILITY DISCOVERY & INVOCATION (agent911/capabilities/registry.py)
       |
       v
ACTUAL EXECUTION + TARGETED RECOVERY (agent911/orchestrator.py, recovery.py, diagnostics.py)
       |
       v
FORMAL EVALUATION 1: VERIFICATION (agent911/evaluation/verification.py)
       |
       v
FORMAL EVALUATION 2: LIVE RUN TESTING (agent911/evaluation/live_testing.py)
       |
       v
EVIDENCE-BASED OUTCOME CLASSIFICATION (agent911/evaluation/classifier.py)
       |
       v
EXPERIENCE LEARNING & CONTROLLED SELF-IMPROVEMENT (agent911/memory.py, improvement.py)
```

### The Two Formal Evaluation Mechanisms
1. **Verification (`Verifier`)**: Inspects objective execution evidence—file existence, non-empty content, Python AST/bytecode compilation (`py_compile`), required function/class definitions, JSON validity, memory persistence, and capability operational status. Produces `PASSED`, `FAILED`, `INCONCLUSIVE`, or `UNAVAILABLE`. AI assertions alone are never marked `PASSED`.
2. **Live Run Testing (`LiveRunTester`)**: Exercises real runtime target behavior in subprocesses or sandboxed registries—executing newly created Python modules/functions, running `unittest`/`pytest` suites, and testing newly developed capabilities against representative inputs. Produces `PASSED`, `FAILED`, `TIMED_OUT`, or `UNAVAILABLE`.

### Task Outcome Classification (`OutcomeClassifier`)
Every task is classified into one of five structured states based on execution, Verification, and Live Run Testing evidence:
- `SUCCESS`: All required steps and verification checks passed, and all applicable live run tests passed.
- `PARTIAL_SUCCESS`: Some requirements succeeded, or static verification passed while a runtime live test failed.
- `FAILED`: Required steps, verification checks, or live tests failed without recovery.
- `BLOCKED`: Execution could not proceed due to missing credentials, permissions, workspace boundary protection, or unavailable external dependencies.
- `UNVERIFIED`: Evidence is inconclusive or insufficient to establish completion.

---

## 2. Windows Compatibility Highlights

- **Pure Python CLI & Interactive Console**: No Node.js or browser required. Runs natively on Windows 10/11 (`python main.py` or `python -m agent911`).
- **Windows NTFS SQLite Handle Hygiene**: `PersistentMemoryStore` explicitly closes every `sqlite3.Connection` on context exit so WAL/database files never lock temporary or workspace directories on Windows.
- **Windows ACL Credential Protection**: `CredentialStore` secures `.agent911/credentials.json` on Windows using `icacls` (`*<SID>:F` via `whoami /user`) and on POSIX using `0600` permissions, keeping raw API keys out of `agent911.config.local.json` and redacting secrets from all logs.
- **Windows Path & Command Handling**: Preserves backslashes when parsing command strings on Windows (`shlex.split(..., posix=False)`), resolves `python`/`python3` to `sys.executable`, resolves `.cmd`/`.bat`/`.exe` shims via `shutil.which()`, and normalizes workspace-relative paths across all capabilities.

---

## 3. Installation & Configuration

### Requirements
- **Python**: 3.11 or newer (core agent uses only the Python standard library).
- **Optional Provider SDKs**: `pip install -r requirements.txt` (or `pip install -e .[providers]`) if using the official Groq SDK client.

### Configuration & Credentials
Copy `agent911.config.example.json` to `agent911.config.local.json` (or manage providers/models directly via the CLI):

```powershell
# Windows PowerShell — Set API key via environment variable or CredentialStore:
$env:AGENT911_API_KEY = "sk-..."

# Or store securely in Agent 911's ACL-protected CredentialStore:
python -m agent911 providers --upsert-id default --api-key "sk-..."
```

---

## 4. Usage Guide (Windows PowerShell / CMD & POSIX)

### Launch Interactive Terminal Console
```powershell
python main.py console
# Or:
python -m agent911 chat
```
Inside the interactive console, enter any natural-language task or chat message, or use slash commands:
- `/status` — Show workspace, model connectivity, capability counts, and SQLite statistics
- `/caps` — List all registered capabilities and their operational availability
- `/tasks` — List recent tasks stored in SQLite
- `/inspect <task_id>` — View full execution report, Verification checks, and Live Run Tests
- `/memory [query]` — Search or list persistent memories
- `/experiences [query]` — Search or list recorded task experiences
- `/models` / `/providers` — Inspect configured model profiles and providers
- `/distill <text>` — Preview concrete build specification from messy writing
- `/proposals` / `/improve <id>` — Detect and apply controlled self-improvements
- `/exit` — Exit console

### Direct CLI Commands
```powershell
# 1. Run Windows & system readiness diagnostics
python -m agent911 doctor

# 2. Check agent status and model connectivity
python -m agent911 status

# 3. Execute a task through the full lifecycle (Planning -> Execution -> Verification -> Live Run Testing)
python -m agent911 run "Write a Python file 'billing/tax_calc.py' with a function 'calculate_tax' and verify it runs."

# 4. Distill messy, informal writing into concrete software and execute it
python -m agent911 distill --execute "uhh hey can u make a python script maybe call it price_calc in billing/ folder that needs to calculate tax and apply discount, oh and make a config json in billing/rates.json!!"

# 5. Grow a new capability organically, verify its AST/contract, and live-test it
python -m agent911 develop-capability text.metrics --name "Text Metrics" --purpose "Count words, lines, and characters in text or workspace files"

# 6. Query or store persistent memory across restarts
python -m agent911 memory --store-key "project.target_os" --store-content "Windows 11" --category FACTUAL
python -m agent911 memory --query "Windows"

# 7. Search workspace code (regex/literal) or Python AST symbols (functions/classes)
python -m agent911 search "calculate_tax" --mode symbol
python -m agent911 search "def " --glob "*.py"

# 8. Create, diff, and restore workspace snapshots (.agent911/snapshots)
python -m agent911 snapshot create --id snap-v1 --label "Before refactor"
python -m agent911 snapshot diff --id snap-v1
python -m agent911 snapshot restore --id snap-v1 --clean

# 9. Detect operational weaknesses and run controlled self-improvement with automatic rollback
python -m agent911 proposals --detect
python -m agent911 self-improve <proposal_id>
```

---

## 5. Running the Automated Test Suite

Run the complete automated test suite (79 unit, integration, recovery, capability-growth, verification, live-testing, Windows compatibility, and end-to-end tests):

```powershell
python -m unittest discover -s tests -v
```

