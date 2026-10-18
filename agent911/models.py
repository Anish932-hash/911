"""Core data structures, state representations, and enums for Agent 911."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "id") -> str:
    """Generate a compact, unique identifier with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class InvalidTaskStateTransitionError(RuntimeError):
    """Raised when an invalid or premature task lifecycle transition is attempted."""


class VerificationStatus(str, Enum):
    """Formal status for Verification checks (Mechanism 1)."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNAVAILABLE = "UNAVAILABLE"


class LiveTestStatus(str, Enum):
    """Formal status for Live Run Testing executions (Mechanism 2)."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"
    TIMED_OUT = "TIMED_OUT"


class TaskOutcome(str, Enum):
    """Structured task outcome classification."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class TaskLifecycleStage(str, Enum):
    """Current lifecycle stage of a task."""

    CREATED = "CREATED"
    UNDERSTANDING = "UNDERSTANDING"
    RETRIEVING_CONTEXT = "RETRIEVING_CONTEXT"
    PLANNING = "PLANNING"
    SELECTING_CAPABILITIES = "SELECTING_CAPABILITIES"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    LIVE_TESTING = "LIVE_TESTING"
    RECOVERING = "RECOVERING"
    CLASSIFYING = "CLASSIFYING"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"


_ALLOWED_STAGE_TRANSITIONS: dict[TaskLifecycleStage, set[TaskLifecycleStage]] = {
    TaskLifecycleStage.CREATED: {
        TaskLifecycleStage.UNDERSTANDING,
        TaskLifecycleStage.RETRIEVING_CONTEXT,
        TaskLifecycleStage.PLANNING,
        TaskLifecycleStage.EXECUTING,
    },
    TaskLifecycleStage.UNDERSTANDING: {
        TaskLifecycleStage.RETRIEVING_CONTEXT,
        TaskLifecycleStage.PLANNING,
    },
    TaskLifecycleStage.RETRIEVING_CONTEXT: {
        TaskLifecycleStage.PLANNING,
        TaskLifecycleStage.SELECTING_CAPABILITIES,
    },
    TaskLifecycleStage.PLANNING: {
        TaskLifecycleStage.SELECTING_CAPABILITIES,
        TaskLifecycleStage.EXECUTING,
    },
    TaskLifecycleStage.SELECTING_CAPABILITIES: {
        TaskLifecycleStage.EXECUTING,
        TaskLifecycleStage.VERIFYING,
    },
    TaskLifecycleStage.EXECUTING: {
        TaskLifecycleStage.RECOVERING,
        TaskLifecycleStage.VERIFYING,
        TaskLifecycleStage.INTERRUPTED,
    },
    TaskLifecycleStage.RECOVERING: {
        TaskLifecycleStage.EXECUTING,
        TaskLifecycleStage.VERIFYING,
        TaskLifecycleStage.INTERRUPTED,
    },
    TaskLifecycleStage.VERIFYING: {
        TaskLifecycleStage.LIVE_TESTING,
        TaskLifecycleStage.CLASSIFYING,
    },
    TaskLifecycleStage.LIVE_TESTING: {
        TaskLifecycleStage.CLASSIFYING,
        TaskLifecycleStage.RECOVERING,
    },
    TaskLifecycleStage.CLASSIFYING: {
        TaskLifecycleStage.COMPLETED,
    },
    TaskLifecycleStage.INTERRUPTED: {
        TaskLifecycleStage.EXECUTING,
        TaskLifecycleStage.PLANNING,
    },
    TaskLifecycleStage.COMPLETED: {
        TaskLifecycleStage.EXECUTING,
        TaskLifecycleStage.VERIFYING,
    },
}


class ActionStatus(str, Enum):
    """Execution status of an individual planned action."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class CapabilityAvailability(str, Enum):
    """Availability state of a capability."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUIRES_CONFIG = "REQUIRES_CONFIG"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    MISCONFIGURED = "MISCONFIGURED"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class MemoryCategory(str, Enum):
    """Supported categories of persistent memory."""

    FACTUAL = "FACTUAL"
    INSTRUCTION = "INSTRUCTION"
    EPISODIC = "EPISODIC"
    EXPERIENCE = "EXPERIENCE"
    WORKING_STATE = "WORKING_STATE"


class MemoryConfidence(str, Enum):
    """Confidence/verification level of a memory record."""

    VERIFIED = "VERIFIED"
    OBSERVED = "OBSERVED"
    ASSUMPTION = "ASSUMPTION"
    UNVERIFIED = "UNVERIFIED"


class ProblemSolvingStrategy(str, Enum):
    """Distinct problem-solving strategies selectable by Agent 911."""

    DIRECT_EXECUTION = "DIRECT_EXECUTION"
    INSPECT_BEFORE_ACT = "INSPECT_BEFORE_ACT"
    STEP_BY_STEP_PLANNING = "STEP_BY_STEP_PLANNING"
    REUSE_PROVEN_PROCEDURE = "REUSE_PROVEN_PROCEDURE"
    CAPABILITY_DELEGATION_OR_GROWTH = "CAPABILITY_DELEGATION_OR_GROWTH"
    CONTROLLED_EXPERIMENTATION = "CONTROLLED_EXPERIMENTATION"
    FAILURE_DIAGNOSIS_AND_ALTERNATIVE = "FAILURE_DIAGNOSIS_AND_ALTERNATIVE"
    INTERRUPTED_TASK_RECOVERY = "INTERRUPTED_TASK_RECOVERY"


class FailureRootCauseCategory(str, Enum):
    """Evidence-based classification of why an approach or step failed."""

    INCORRECT_ASSUMPTION = "INCORRECT_ASSUMPTION"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    UNAVAILABLE_CAPABILITY = "UNAVAILABLE_CAPABILITY"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    CONFIGURATION_PROBLEM = "CONFIGURATION_PROBLEM"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
    PERMISSION_BOUNDARY = "PERMISSION_BOUNDARY"
    MODEL_LIMITATION = "MODEL_LIMITATION"
    IMPLEMENTATION_DEFECT = "IMPLEMENTATION_DEFECT"
    EXTERNAL_SERVICE_FAILURE = "EXTERNAL_SERVICE_FAILURE"
    INVALID_STRATEGY = "INVALID_STRATEGY"
    UNKNOWN_CAUSE = "UNKNOWN_CAUSE"


class ImprovementStatus(str, Enum):
    """Explicit lifecycle status keeping proposed changes distinct from validated ones."""

    PROPOSED = "PROPOSED"
    IMPLEMENTED_PENDING_EVAL = "IMPLEMENTED_PENDING_EVAL"
    VALIDATED_SUCCESS = "VALIDATED_SUCCESS"
    ROLLED_BACK_FAILED = "ROLLED_BACK_FAILED"
    REJECTED = "REJECTED"


@dataclass
class DistilledBuildSpec:
    """
    Concrete specification distilled from potentially messy, informal, or unstructured
    user writings so the agent can identify and execute what the user wants to build.
    """

    raw_input: str
    is_messy_input: bool = False
    is_build_intent: bool = False
    what_user_wants_to_build: str = ""
    concrete_instruction: str = ""
    concrete_steps: list[str] = field(default_factory=list)
    target_artifacts: list[dict[str, Any]] = field(default_factory=list)
    extracted_functions: list[str] = field(default_factory=list)
    extracted_features: list[str] = field(default_factory=list)
    ambiguities_resolved: list[str] = field(default_factory=list)
    noise_filtered: list[str] = field(default_factory=list)
    distilled_by: str = "heuristic_distiller"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DistilledBuildSpec:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class InstructionIntent:
    """Structured representation of a user's instruction distinguishing explicit vs inferred."""

    original_instruction: str
    main_goal: str
    explicit_requirements: list[str] = field(default_factory=list)
    inferred_requirements: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    relevant_context: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)
    available_resources: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    completion_conditions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    target_artifacts: list[str] = field(default_factory=list)
    complexity_level: str = "simple_direct"  # simple_direct, moderate_inspect_act, complex_multi_stage
    clarification_needed: bool = False
    clarification_question: str | None = None
    interpreted_by: str = "heuristic"  # "model" or "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstructionIntent:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class TaskRequirement:
    """Explicit requirement to be satisfied and verified for a task."""

    requirement_id: str
    description: str
    category: str
    target: str | None = None
    expected: Any = None
    required: bool = True
    satisfied: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRequirement:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PlannedAction:
    """Single actionable step in a task plan with dependency, evidence, and retry tracking."""

    step_id: str
    description: str
    capability_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    status: ActionStatus = ActionStatus.PENDING
    required: bool = True
    is_capability_growth: bool = False
    output_summary: str | None = None
    completion_evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retry_status: str = "none"  # none, retried_recovered, retried_failed

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlannedAction:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        copied = {k: v for k, v in data.items() if k in known}
        copied["status"] = ActionStatus(copied.get("status", ActionStatus.PENDING.value))
        return cls(**copied)


@dataclass
class CapabilityResult:
    """Structured output returned by any invoked capability."""

    capability_id: str
    success: bool
    data: Any = None
    error: str | None = None
    error_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityResult:
        return cls(**data)


@dataclass
class CapabilityCallRecord:
    """Execution record of a capability invocation during a task."""

    call_id: str
    task_id: str
    step_id: str
    capability_id: str
    parameters: dict[str, Any]
    success: bool
    output_data: Any = None
    error: str | None = None
    error_type: str | None = None
    duration_ms: float = 0.0
    intended_action: str = ""
    retry_occurred: bool = False
    attempt_number: int = 1
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityCallRecord:
        return cls(**data)


@dataclass
class VerificationCheckResult:
    """Structured result for a single Verification check (Formal Evaluation Mechanism 1)."""

    check_id: str
    task_id: str
    requirement: str
    method: str
    observed_result: str
    status: VerificationStatus
    evidence: dict[str, Any] = field(default_factory=dict)
    failure_explanation: str | None = None
    remaining_uncertainty: str | None = None
    required: bool = True
    is_ai_assertion_only: bool = False
    timestamp: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if self.is_ai_assertion_only and self.status == VerificationStatus.PASSED:
            self.status = VerificationStatus.INCONCLUSIVE
            if not self.failure_explanation:
                self.failure_explanation = (
                    "Model assertion alone is not treated as objective verification evidence."
                )
            if not self.remaining_uncertainty:
                self.remaining_uncertainty = (
                    "Requires direct operational or filesystem evidence."
                )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationCheckResult:
        copied = dict(data)
        copied["status"] = VerificationStatus(copied["status"])
        return cls(**copied)


@dataclass
class LiveRunTestRecord:
    """Structured record for a Live Run Test execution (Formal Evaluation Mechanism 2)."""

    test_id: str
    task_id: str
    executed_operation: str
    target_component: str
    environment: dict[str, Any]
    exit_code: int | None
    stdout: str
    stderr: str
    expected_behavior_occurred: bool
    status: LiveTestStatus
    limitations: str | None = None
    reproduction_command: str | None = None
    is_mocked: bool = False
    required: bool = True
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if self.is_mocked and not self.limitations:
            self.limitations = (
                "Executed against a mock or deterministic double; does not establish live external service connectivity."
            )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LiveRunTestRecord:
        copied = dict(data)
        copied["status"] = LiveTestStatus(copied["status"])
        return cls(**copied)


@dataclass
class ExecutionErrorRecord:
    """Detailed record of an error encountered during task execution."""

    error_id: str
    task_id: str
    step_id: str | None
    capability_id: str | None
    error_type: str
    message: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    recovered: bool = False
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionErrorRecord:
        return cls(**data)


@dataclass
class RecoveryAttemptRecord:
    """Record of a targeted diagnosis and recovery attempt."""

    attempt_id: str
    task_id: str
    step_id: str
    failed_operation: str
    probable_cause: str
    selected_correction: str
    correction_parameters: dict[str, Any] = field(default_factory=dict)
    succeeded: bool = False
    notes: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoveryAttemptRecord:
        return cls(**data)


@dataclass
class MemoryRecord:
    """Persistent memory entry stored in SQLite with provenance and lifecycle status."""

    memory_id: str
    category: MemoryCategory
    key: str
    content: str
    task_id: str | None = None
    source: str = "agent"
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: MemoryConfidence = MemoryConfidence.OBSERVED
    status: str = "ACTIVE"  # ACTIVE, SUPERSEDED, OBSOLETE
    superseded_by: str | None = None
    provenance_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["confidence"] = self.confidence.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        copied = dict(data)
        copied["category"] = MemoryCategory(copied["category"])
        copied["confidence"] = MemoryConfidence(
            copied.get("confidence", MemoryConfidence.OBSERVED.value)
        )
        return cls(**copied)


@dataclass
class ExperienceRecord:
    """
    Persistent experience entry capturing evidence-backed lessons from task execution.
    Distinguishes verified operational evidence from unverified model claims, and
    tracks practical usefulness when retrieved for future tasks.
    """

    experience_id: str
    task_id: str
    objective: str
    plan_summary: str
    capabilities_used: list[str] = field(default_factory=list)
    operations_performed: list[str] = field(default_factory=list)
    actual_results: dict[str, Any] = field(default_factory=dict)
    verification_summary: dict[str, Any] = field(default_factory=dict)
    live_test_summary: dict[str, Any] = field(default_factory=dict)
    unexpected_failures: list[str] = field(default_factory=list)
    identified_causes: list[str] = field(default_factory=list)
    confirmed_causes: list[str] = field(default_factory=list)
    hypothesized_causes: list[str] = field(default_factory=list)
    corrections_attempted: list[str] = field(default_factory=list)
    successful_remedies: list[str] = field(default_factory=list)
    remaining_limitations: list[str] = field(default_factory=list)
    reusable_procedures: list[str] = field(default_factory=list)
    outcome: TaskOutcome = TaskOutcome.UNVERIFIED
    tags: list[str] = field(default_factory=list)
    task_type: str = "general"
    evidence_supporting_outcome: dict[str, Any] = field(default_factory=dict)
    applicable_conditions: list[str] = field(default_factory=list)
    lesson_confidence: str = "OBSERVED"  # VERIFIED_EXECUTION, OBSERVED, UNVERIFIED_CLAIM, HYPOTHESIS
    superseded: bool = False
    times_retrieved: int = 0
    times_helpful: int = 0
    times_prevented_failure: int = 0
    times_irrelevant: int = 0
    times_caused_problem: int = 0
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        # Guard against promoting an unverified claim into VERIFIED_EXECUTION experience
        if (
            self.lesson_confidence == "VERIFIED_EXECUTION"
            and self.outcome == TaskOutcome.UNVERIFIED
        ):
            self.lesson_confidence = "UNVERIFIED_CLAIM"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperienceRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        copied = {k: v for k, v in data.items() if k in known}
        copied["outcome"] = TaskOutcome(copied.get("outcome", TaskOutcome.UNVERIFIED.value))
        return cls(**copied)


@dataclass
class DiagnosticReport:
    """
    Evidence-based diagnostic report distinguishing confirmed facts from likely
    hypotheses and eliminated causes.
    """

    diagnostic_id: str
    task_id: str
    step_id: str | None
    observed_failure: str
    root_cause_category: FailureRootCauseCategory
    confirmed_facts: list[str] = field(default_factory=list)
    likely_hypotheses: list[str] = field(default_factory=list)
    eliminated_causes: list[str] = field(default_factory=list)
    remaining_uncertainty: str | None = None
    diagnostic_action_taken: str | None = None
    recommended_correction: str = "none"
    repeated_loop_detected: bool = False
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["report_id"] = self.diagnostic_id
        data["root_cause_category"] = self.root_cause_category.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiagnosticReport:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        copied = {k: v for k, v in data.items() if k in known}
        copied["root_cause_category"] = FailureRootCauseCategory(
            copied.get("root_cause_category", FailureRootCauseCategory.UNKNOWN_CAUSE.value)
        )
        return cls(**copied)


@dataclass
class CapabilityProposal:
    """Concrete specification for a genuinely missing capability (Section 9.2)."""

    capability_id: str
    name: str
    what_it_does: str
    why_needed: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    operational_boundaries: str = "workspace_confined"
    integration_notes: str = "Register in CapabilityRegistry and persist in SQLite custom_capabilities."
    verification_plan: str = "Verify AST/bytecode compilation, contract fields, and registration."
    live_test_plan: str = "Invoke capability with representative inputs in LiveRunTester and check exit/output."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityGapAnalysis:
    """
    Distinguishes missing capabilities from missing dependencies, credentials,
    configuration settings, permissions, model features, or external services (Section 9.1).
    """

    missing_element_type: str  # capability, dependency, configuration_setting, credential, permission, information, model_feature, external_service, none
    missing_identifier: str
    explanation: str
    reusable_existing_capabilities: list[str] = field(default_factory=list)
    capability_proposal: CapabilityProposal | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.capability_proposal is not None:
            data["capability_proposal"] = self.capability_proposal.to_dict()
        return data


@dataclass
class ImprovementProposal:
    """
    Actionable, evidence-backed proposal for improving Agent 911's operation (Section 6).
    Explicitly tracks status so proposed changes are never confused with validated improvements.
    """

    proposal_id: str
    title: str
    category: str  # config_default, retrieval_ranking, capability_growth, recovery_rule, model_routing, test_coverage
    observed_problem: str
    supporting_evidence: dict[str, Any] = field(default_factory=dict)
    likely_cause: str = ""
    proposed_change: str = ""
    expected_benefits: list[str] = field(default_factory=list)
    potential_regressions: list[str] = field(default_factory=list)
    required_dependencies: list[str] = field(default_factory=list)
    implementation_scope: str = "bounded_config_or_capability"
    test_plan: str = ""
    success_conditions: list[str] = field(default_factory=list)
    priority: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    priority_rationale: str = ""
    status: ImprovementStatus = ImprovementStatus.PROPOSED
    action_payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImprovementProposal:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        copied = {k: v for k, v in data.items() if k in known}
        copied["status"] = ImprovementStatus(
            copied.get("status", ImprovementStatus.PROPOSED.value)
        )
        return cls(**copied)


@dataclass
class SelfImprovementRunRecord:
    """
    Record of applying and evaluating a proposed improvement under controlled conditions
    with automatic rollback on Verification or Live Run Testing failure (Section 7).
    """

    run_id: str
    proposal_id: str
    baseline_behavior: dict[str, Any] = field(default_factory=dict)
    change_applied: dict[str, Any] = field(default_factory=dict)
    expected_result: str = ""
    actual_result: str = ""
    verification_passed: bool = False
    live_test_passed: bool = False
    regressions_observed: list[str] = field(default_factory=list)
    rolled_back: bool = False
    final_disposition: str = "PENDING"  # VALIDATED_SUCCESS, ROLLED_BACK_FAILED, REJECTED_SECURITY_BOUNDARY
    remaining_uncertainty: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verification_status"] = "PASSED" if self.verification_passed else "FAILED"
        d["live_test_status"] = "PASSED" if self.live_test_passed else "FAILED"
        d["notes"] = self.actual_result
        return d


@dataclass
class TaskState:
    """Complete structured representation of a task and its lifecycle state."""

    task_id: str
    original_instruction: str
    interpreted_objective: str = ""
    intent: InstructionIntent | None = None
    distilled_spec: DistilledBuildSpec | None = None
    requirements: list[TaskRequirement] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    selected_strategy: str = ProblemSolvingStrategy.DIRECT_EXECUTION.value
    strategy_rationale: str = ""
    strategy_history: list[dict[str, Any]] = field(default_factory=list)
    planned_actions: list[PlannedAction] = field(default_factory=list)
    completed_actions: list[str] = field(default_factory=list)
    pending_actions: list[str] = field(default_factory=list)
    current_execution_state: TaskLifecycleStage = TaskLifecycleStage.CREATED
    capability_calls: list[CapabilityCallRecord] = field(default_factory=list)
    relevant_outputs: dict[str, Any] = field(default_factory=dict)
    verification_results: list[VerificationCheckResult] = field(default_factory=list)
    live_run_results: list[LiveRunTestRecord] = field(default_factory=list)
    errors: list[ExecutionErrorRecord] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    recovery_attempts: list[RecoveryAttemptRecord] = field(default_factory=list)
    capability_gap_analysis: dict[str, Any] | None = None
    capability_gap_analyses: list[dict[str, Any]] = field(default_factory=list)
    model_routing_decisions: list[dict[str, Any]] = field(default_factory=list)
    resource_metrics: dict[str, Any] = field(default_factory=dict)
    final_outcome: TaskOutcome = TaskOutcome.UNVERIFIED
    outcome_summary: str = ""
    assistant_response: str = ""
    interaction_mode: str = "task_execution"
    associated_experience_ids: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    context_summary: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @property
    def diagnostic_reports(self) -> list[dict[str, Any]]:
        return self.diagnostics

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def transition_to(self, new_stage: TaskLifecycleStage) -> None:
        """
        Validate and execute a task lifecycle transition.
        Prevents impossible transitions (such as marking a task COMPLETED before
        in-progress steps have finished or before classification).
        """
        if new_stage == self.current_execution_state:
            self.touch()
            return

        if new_stage == TaskLifecycleStage.COMPLETED:
            in_prog = [
                a.step_id
                for a in self.planned_actions
                if a.status == ActionStatus.IN_PROGRESS
            ]
            if in_prog:
                raise InvalidTaskStateTransitionError(
                    f"Cannot mark task '{self.task_id}' COMPLETED while steps {in_prog} are IN_PROGRESS."
                )

        allowed = _ALLOWED_STAGE_TRANSITIONS.get(self.current_execution_state, set())
        if new_stage not in allowed:
            raise InvalidTaskStateTransitionError(
                f"Invalid task state transition from '{self.current_execution_state.value}' "
                f"to '{new_stage.value}'."
            )
        self.current_execution_state = new_stage
        self.touch()

    def refresh_action_lists(self) -> None:
        """Synchronize completed_actions and pending_actions from planned_actions."""
        self.completed_actions = [
            a.step_id for a in self.planned_actions if a.status == ActionStatus.COMPLETED
        ]
        self.pending_actions = [
            a.step_id
            for a in self.planned_actions
            if a.status in (ActionStatus.PENDING, ActionStatus.IN_PROGRESS)
        ]
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_instruction": self.original_instruction,
            "interpreted_objective": self.interpreted_objective,
            "intent": self.intent.to_dict() if self.intent else None,
            "distilled_spec": self.distilled_spec.to_dict() if self.distilled_spec else None,
            "requirements": [r.to_dict() for r in self.requirements],
            "assumptions": list(self.assumptions),
            "selected_strategy": self.selected_strategy,
            "strategy_rationale": self.strategy_rationale,
            "strategy_history": list(self.strategy_history),
            "planned_actions": [a.to_dict() for a in self.planned_actions],
            "completed_actions": list(self.completed_actions),
            "pending_actions": list(self.pending_actions),
            "current_execution_state": self.current_execution_state.value,
            "capability_calls": [c.to_dict() for c in self.capability_calls],
            "relevant_outputs": dict(self.relevant_outputs),
            "verification_results": [v.to_dict() for v in self.verification_results],
            "live_run_results": [l.to_dict() for l in self.live_run_results],
            "errors": [e.to_dict() for e in self.errors],
            "diagnostics": list(self.diagnostics),
            "diagnostic_reports": list(self.diagnostics),
            "recovery_attempts": [r.to_dict() for r in self.recovery_attempts],
            "capability_gap_analysis": self.capability_gap_analysis,
            "capability_gap_analyses": list(self.capability_gap_analyses),
            "model_routing_decisions": list(self.model_routing_decisions),
            "resource_metrics": dict(self.resource_metrics),
            "final_outcome": self.final_outcome.value,
            "outcome_summary": self.outcome_summary,
            "assistant_response": self.assistant_response,
            "interaction_mode": self.interaction_mode,
            "associated_experience_ids": list(self.associated_experience_ids),
            "decisions": list(self.decisions),
            "context_summary": self.context_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskState:
        return cls(
            task_id=data["task_id"],
            original_instruction=data["original_instruction"],
            interpreted_objective=data.get("interpreted_objective", ""),
            intent=InstructionIntent.from_dict(data["intent"]) if data.get("intent") else None,
            distilled_spec=DistilledBuildSpec.from_dict(data["distilled_spec"])
            if data.get("distilled_spec")
            else None,
            requirements=[TaskRequirement.from_dict(r) for r in data.get("requirements", [])],
            assumptions=list(data.get("assumptions", [])),
            selected_strategy=data.get(
                "selected_strategy", ProblemSolvingStrategy.DIRECT_EXECUTION.value
            ),
            strategy_rationale=data.get("strategy_rationale", ""),
            strategy_history=list(data.get("strategy_history", [])),
            planned_actions=[PlannedAction.from_dict(a) for a in data.get("planned_actions", [])],
            completed_actions=list(data.get("completed_actions", [])),
            pending_actions=list(data.get("pending_actions", [])),
            current_execution_state=TaskLifecycleStage(
                data.get("current_execution_state", TaskLifecycleStage.CREATED.value)
            ),
            capability_calls=[
                CapabilityCallRecord.from_dict(c) for c in data.get("capability_calls", [])
            ],
            relevant_outputs=dict(data.get("relevant_outputs", {})),
            verification_results=[
                VerificationCheckResult.from_dict(v) for v in data.get("verification_results", [])
            ],
            live_run_results=[
                LiveRunTestRecord.from_dict(l) for l in data.get("live_run_results", [])
            ],
            errors=[ExecutionErrorRecord.from_dict(e) for e in data.get("errors", [])],
            diagnostics=list(
                data.get("diagnostics") or data.get("diagnostic_reports") or []
            ),
            recovery_attempts=[
                RecoveryAttemptRecord.from_dict(r) for r in data.get("recovery_attempts", [])
            ],
            capability_gap_analysis=data.get("capability_gap_analysis"),
            capability_gap_analyses=list(data.get("capability_gap_analyses", [])),
            model_routing_decisions=list(data.get("model_routing_decisions", [])),
            resource_metrics=dict(data.get("resource_metrics", {})),
            final_outcome=TaskOutcome(
                data.get("final_outcome", TaskOutcome.UNVERIFIED.value)
            ),
            outcome_summary=data.get("outcome_summary", ""),
            assistant_response=data.get("assistant_response", ""),
            interaction_mode=data.get("interaction_mode", "task_execution"),
            associated_experience_ids=list(data.get("associated_experience_ids", [])),
            decisions=list(data.get("decisions", [])),
            context_summary=data.get("context_summary"),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
        )
