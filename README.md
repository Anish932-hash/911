# Agent 911

**Agent 911** is a complete, from-scratch, instruction-driven, self-expanding AI agent designed around evidence-based task execution, persistent SQLite memory and experience, targeted failure recovery, organic capability growth, and exactly two formal task-evaluation mechanisms:

1. **Verification** (`agent911.evaluation.verification.Verifier`)
2. **Live Run Testing** (`agent911.evaluation.live_testing.LiveRunTester`)

---

## 1. Architectural Overview

Agent 911 executes tasks through a unified, direct lifecycle without any separate Guardian or policy-approval subsystem:

```text
USER INSTRUCTION
  │
  ▼
INTENT UNDERSTANDING & CONTEXT / MEMORY RETRIEVAL
  │
  ▼
TASK REPRESENTATION & EXPERIENCE-INFORMED PLANNING
  │
  ▼
CAPABILITY DISCOVERY & SELECTION (including Capability Gap Detection)
  │
  ▼
ACTUAL EXECUTION (with Error Diagnosis & Targeted Recovery)
  │
  ▼
FORMAL EVALUATION MECHANISM 1: VERIFICATION
  │
  ▼
FORMAL EVALUATION MECHANISM 2: LIVE RUN TESTING
  │
  ▼
RESULT CLASSIFICATION (SUCCESS | PARTIAL_SUCCESS | FAILED | BLOCKED | UNVERIFIED)
  │
  ▼
EXPERIENCE & PERSISTENT MEMORY UPDATE
```

### Principal Modules

- `agent911/models.py`: Structured data models (`TaskState`, `InstructionIntent`, `TaskRequirement`, `PlannedAction`, `CapabilityResult`, `VerificationCheckResult`, `LiveRunTestRecord`, `ExecutionErrorRecord`, `RecoveryAttemptRecord`, `MemoryRecord`, `ExperienceRecord`) and formal status enums.
- `agent911/config.py`: Configuration loader (`AgentConfig`, `ModelConfig`), validator (`ConfigurationError`), and recursive secret redaction (`redact_secrets`).
- `agent911/memory.py`: SQLite-backed `PersistentMemoryStore` managing five logical memory categories (`FACTUAL`, `INSTRUCTION`, `EPISODIC`, `EXPERIENCE`, `WORKING_STATE`), experience records, persisted task states, redacted execution logs, and custom capability metadata.
- `agent911/context.py`: `ContextManager` for selective memory/experience retrieval, context-window enforcement, context compression/summarization (`compress_context`), and interrupted-task resumption validation (`prepare_task_for_resumption`).
- `agent911/model_provider.py`: `ModelInterface` supporting OpenAI-compatible (`/v1/chat/completions`), Anthropic (`/v1/messages`), Ollama (`/api/chat`), and deterministic test doubles (`deterministic`), with honest connectivity reporting (`check_connectivity`).
- `agent911/capabilities/`:
  - `base.py` & `registry.py`: `Capability` contract, `CapabilityContext`, and `CapabilityRegistry` (rejecting empty/stub classes, validating inputs, checking availability, and dynamically loading custom capabilities).
  - `filesystem.py`: `fs.list`, `fs.read`, `fs.write`, `fs.update`, `fs.mkdir`, `fs.stat` with strict workspace boundary enforcement (`resolve_in_workspace`).
  - `project_inspection.py`: `project.inspect` discovering project files, source directories, configuration files, documentation, tests, package manifests, entry points, dependencies, and Python AST symbols.
  - `command_execution.py`: `cmd.run` executing development commands with timeout, workspace `cwd`, exit code, `stdout`, and `stderr` capture.
  - `test_execution.py`: `test.run` executing `unittest` or `pytest` test suites and parsing actual test counts and outcomes.
  - `memory_ops.py` & `experience_ops.py`: `memory.store`, `memory.retrieve`, `memory.update`, `experience.record`, `experience.retrieve`.
  - `model_ops.py`: `capability.discover`, `model.connectivity`, `model.query`.
  - `web_research.py`: `research.web_search` uses Tavily or Brave Search to return source titles, URLs, and snippets. Model-authored capabilities and skills automatically include relevant search results when configured; the planner can also schedule research before implementation.
  - `growth.py`: `capability.develop` for staged capability synthesis, AST/interface verification, live runtime testing, post-test promotion, and SQLite persistence; `skill.develop` for staged SKILL.md package validation.
  - Capability implementations may declare `supported_platforms` as `all`, `windows`, `linux`, and/or `macos`. The registry reports `UNSUPPORTED_PLATFORM` before invocation when the current OS is outside that list, and exposes the declared platforms during capability discovery.
- `agent911/planner.py`: `TaskPlanner` combining AI-model planning (when connected) with a local natural-language instruction parser, capability gap detection, and automatic application of remedies from past experiences.
- `agent911/recovery.py`: `RecoveryEngine` diagnosing step failures, selecting targeted corrections (e.g., creating missing parent directories, developing missing capabilities, initializing missing files), re-executing only the affected step, and preventing retry loops via retry caps and failure-signature tracking.
- `agent911/evaluation/`:
  - `verification.py`: `Verifier` (`PASSED`, `FAILED`, `INCONCLUSIVE`, `UNAVAILABLE`).
  - `live_testing.py`: `LiveRunTester` (`PASSED`, `FAILED`, `UNAVAILABLE`, `TIMED_OUT`).
  - `classifier.py`: `OutcomeClassifier` (`SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`, `BLOCKED`, `UNVERIFIED`).
- `agent911/orchestrator.py`: `Agent911Orchestrator` coordinating the end-to-end lifecycle and task resumption.
- `agent911/cli.py` & `agent911/__main__.py`: Command-line interface (`agent911` / `python3 -m agent911`).
- `agent911/bridge.py` & `ui/`: Node.js Chat & Operations Console (`ui/server.js`, `ui/public/index.html`, `ui/public/styles.css`, `ui/public/app.js`, `ui/test_ui.js`) bridged directly to the Python `Agent911Orchestrator`.

---

## 2. Requirements & Installation

### Required Runtime & Dependencies

- **Python:** Python `>= 3.10` (tested on Python `3.11.2`).
- **Runtime Dependencies:** Zero mandatory third-party packages; built on Python's standard library (`sqlite3`, `urllib.request`, `subprocess`, `ast`, `importlib`, `unittest`, `argparse`, `dataclasses`, `json`).
- **Optional Development Dependencies:** `pytest >= 7.0.0` (standard library `unittest` is also fully supported).

### Installation Commands

From the repository root (`/home/user/911`):

```bash
# Editable installation (creates the `agent911` CLI script)
pip install -e .

# Or on Debian/PEP-668 managed environments without a virtualenv:
pip install --break-system-packages --no-build-isolation -e .
```

You can also invoke Agent 911 directly without installing via `python3 -m agent911`.

On Windows, use the Python launcher and PowerShell commands:

```powershell
py -m pip install -e ".[dev]"
py -m agent911 status
py -m unittest discover -s tests -v
npm test
```

The credential vault is restricted to the current Windows user with a file ACL;
on POSIX systems it uses mode `0600`. SQLite connections are closed after each
store operation so temporary workspaces can be removed on Windows.

---

## 3. Multi-Provider & Multi-Model Configuration System

### Configuration Files, Schema v2 & Credential Store

Copy the example configuration file if you want a local configuration file:

```bash
cp agent911.config.example.json agent911.config.local.json
```

Agent 911 uses a versioned configuration schema (`schema_version = 2`, backwards-compatible with v1) supporting:
- **Multiple Providers (`providers` registry):** Configure, edit, enable/disable, and remove multiple providers (`openai_compatible`, `anthropic`, `ollama`, `local_only`, `deterministic`) with dedicated `ProviderAdapter` implementations.
- **Multiple Model Profiles (`models` registry):** Configure multiple models (including multiple models per provider) with human-readable name, provider ID, model ID, optional endpoint override, context window (`null` when unknown), supported inputs, tool-calling/structured-output/streaming support (`true`/`false`/`"unknown"`), temperature, max tokens, timeout, and retry policy.
- **Active, Default, and Fallback Model Selection:** Switch the `active_model` at runtime without restarting, persist `default_model` across restarts, and configure an optional `fallback_model` for automatic recovery when a primary provider fails.
- **Secure Credential Management (`CredentialStore`):** API keys are never written into `agent911.config.local.json` or allowed in endpoint URLs. Secrets are resolved from environment variables (`AGENT911_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or provider-specific `api_key_env`) or stored in `.agent911/credentials.json` with `0600` file permissions and displayed only as masked previews (`sk-...3210`).

### Supported Environment Variables

- `AGENT911_API_KEY` (or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`): API credential for the configured model provider. Never commit API keys to source control.
- `AGENT911_WORKSPACE`: Override `workspace_root`.
- `AGENT911_DB_PATH`: Override SQLite database path.
- `AGENT911_PROVIDER`: Override active provider adapter (`openai_compatible`, `anthropic`, `ollama`, `deterministic`, `local_only`).
- `AGENT911_MODEL_ID`: Override active model identifier.
- `AGENT911_ENDPOINT`: Override active model endpoint.
- `AGENT911_TIMEOUT`: Override active model timeout seconds.
- `TAVILY_API_KEY`: Optional [Tavily Search API](https://help.tavily.com/articles/4840311948-tavily-search-api) key for `research.web_search`. It is sent only to Tavily's fixed search endpoint, never to the LLM provider.
- Install the optional official SDK integrations with `pip install .[providers]`. Groq's official Python SDK is selected automatically for `api.groq.com` chat completion endpoints, and Tavily search uses the official `tavily-python` client. Other generic OpenAI-compatible, Anthropic, Ollama, and Brave integrations retain their current transports.
- `BRAVE_SEARCH_API_KEY`: Alternative [Brave Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get) key for `research.web_search`.
- `AGENT911_SEARCH_PROVIDER`: Optional `tavily` or `brave` selection when the matching key is configured. Without it, Tavily is preferred when both keys are present.

### Persistent Memory & Workspace Locations

- **Workspace Root (`workspace_root`):** All filesystem (`fs.*`), project inspection (`project.inspect`), command (`cmd.run`), and test (`test.run`) operations resolve paths inside `workspace_root` and reject path traversal outside the workspace with `WorkspaceBoundaryError`.
- **SQLite Database (`database_path`):** Defaults to `<workspace_root>/.agent911/agent911.db`. Stores memories (with `status` `ACTIVE`/`SUPERSEDED`/`OBSOLETE` and `provenance_history`), evidence-backed experiences, task states, redacted execution logs, and custom capability metadata.
- **Credential Vault (`credentials.json`):** Defaults to `<workspace_root>/.agent911/credentials.json` (mode `0600`).
- **Custom Grown Capabilities (`custom_capabilities_dir`):** Defaults to `<workspace_root>/.agent911/capabilities/`.

---

## 4. Launch & Usage Commands

```bash
# Check application configuration, model connectivity, and capability availability
python3 -m agent911 status

# List, add, update, enable/disable, or remove providers
python3 -m agent911 providers
python3 -m agent911 providers --upsert-id anthropic_main --name "Anthropic API" \
  --adapter anthropic --endpoint https://api.anthropic.com/v1/messages \
  --api-key-env ANTHROPIC_API_KEY

# List, add, update, enable/disable, or remove model profiles
python3 -m agent911 models
python3 -m agent911 models --upsert-id claude-sonnet --name "Claude 3.5 Sonnet" \
  --provider-id anthropic_main --model-name claude-3-5-sonnet-latest --context-window 200000

# Switch active model at runtime, persist as default, or configure fallback model
python3 -m agent911 model-select claude-sonnet --set-default --fallback local-planner

# Run a genuine connection test against the active or specified model profile
python3 -m agent911 model-test
python3 -m agent911 model-test --profile local-planner

# List all registered capabilities (built-in and custom grown)
python3 -m agent911 capabilities

# Execute a task instruction
python3 -m agent911 run "Write a Python file 'calculator.py' with a function 'add_values'."

# Develop, verify, live-test, and register a new capability
python3 -m agent911 develop-capability text.metrics \
  --name "Text Metrics Analyzer" \
  --purpose "Count words, lines, and characters in text or files"

# Store and query persistent memory
python3 -m agent911 memory --store-key "project.owner" --store-content "Agent 911 Team"
python3 -m agent911 memory --query "owner"

# List recent tasks and inspect detailed execution/evaluation records
python3 -m agent911 tasks
python3 -m agent911 inspect <task_id>

# Resume an interrupted task
python3 -m agent911 resume <task_id>

# Inspect recorded task experiences and remedies
python3 -m agent911 experiences

# Inspect structured self-diagnosis, strategy history, capability gap analysis, and resource metrics
python3 -m agent911 diagnose <task_id>

# Scan execution history for operational weaknesses and list prioritized ImprovementProposals
python3 -m agent911 proposals --detect

# Execute controlled self-improvement for a proposal (with Verification, Live Run Testing, and automatic rollback)
python3 -m agent911 self-improve <proposal_id>

# Launch the Node.js Chat Interface (binds to 127.0.0.1:3000 by default)
npm start
```

To expose the UI beyond the local machine, set `HOST` explicitly. Cross-origin API
access is disabled by default; set `AGENT911_ALLOWED_ORIGINS` to a comma-separated
list of exact origins only when an iframe or separate frontend needs it.

Capability candidates are stored under `.agent911/workbench/<task>/<attempt>/` and are
invoked through a separate candidate registry. Failed candidates remain available for
inspection there and are not loaded into the active registry or persisted as custom
capabilities. A passing candidate is copied into the configured custom-capabilities
directory only after verification and live invocation. The workbench is a dedicated
test workspace, not an operating-system security sandbox. Generated/custom Python modules
are imported and invoked in-process with the Agent 911 process's permissions. Only run
trusted implementations; workspace path checks do not prevent arbitrary Python code from
accessing other files or services.

Offline capability generation is limited to known deterministic templates. For other
capabilities, configure a model provider and supply explicit `test_cases` (each with
`params` and `expected_output`) or `test_params` plus `expected_test_output`. Model-generated
source is repaired with concrete compile/runtime evidence for at most three rounds; every
candidate and test record stays under the workbench. Without a configured model, unknown
requests fail explicitly instead of receiving an identity/echo implementation. Passing
checks is evidence for the supplied cases, not a guarantee that all inputs are bug-free.

The `skill.develop` capability can author a Codex-style `SKILL.md` from `skill_spec` using
the configured model, or accept `skill_markdown` for validation. It uses bounded structural
repair, then publishes under `.agent911/skills/`. Optional `test_cases` are passed to the
model as acceptance criteria, not executed by Agent 911. Results explicitly report
`behavior_tested: false` because this runtime does not execute SKILL.md instructions.

When a search API key is configured, generated capabilities and skills receive relevant web search results as untrusted research context. Source URLs are kept with the results for citations; search content does not override the task specification or acceptance tests. Research is optional, so authoring continues without search using the configured model's knowledge. Search queries and snippets are sent to the selected search provider and configured model provider; do not include secrets or private source code in a query.

Add `--json` before the subcommand (e.g., `python3 -m agent911 --json status`) for machine-readable JSON output, or `--workspace /path/to/workspace` to target an isolated workspace directory.

---

## 5. Running Automated Tests

Both Python (`unittest` and `pytest`) and Node.js (`node --test`) suites are supported:

```bash
# Run Python test suite with unittest
python3 -m unittest discover -s tests -v

# Run Python test suite with pytest
pytest -v

# Run Node.js Chat UI test suite
npm test
```

---

## 6. Troubleshooting

- **`Model Connectivity: MISSING_CREDENTIALS` / `Task BLOCKED` on `model.query`:**
  No API key was found in `AGENT911_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`. Export a valid API key in your environment to enable live external model queries. Local capabilities (`fs.*`, `project.inspect`, `cmd.run`, `test.run`, `memory.*`, `experience.*`, `capability.develop`) continue to operate when `allow_local_fallback` is `true`.
- **`WorkspaceBoundaryError`:**
  A file or directory path resolved outside the configured `workspace_root`. Pass a relative path within the workspace or adjust `--workspace`.
- **`ConfigurationError`:**
  Check that your JSON config file is valid JSON, contains no unknown keys, and uses positive numbers for timeouts.
