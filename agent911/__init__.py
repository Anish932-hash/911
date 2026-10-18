"""Agent 911: Instruction-Driven, Self-Expanding AI Agent."""

from agent911.config import AgentConfig, ConfigurationError, ModelConfig, redact_secrets
from agent911.context import ContextManager
from agent911.diagnostics import CapabilityGapAnalyzer, SelfDiagnosticEngine
from agent911.evaluation import LiveRunTester, OutcomeClassifier, Verifier
from agent911.improvement import ImprovementEngine
from agent911.memory import PersistentMemoryStore
from agent911.model_provider import (
    ConnectivityReport,
    MalformedModelOutputError,
    ModelInterface,
    ModelProviderError,
    ModelResponse,
    ProviderConnectivityStatus,
)
from agent911.models import (
    ActionStatus,
    CapabilityAvailability,
    CapabilityCallRecord,
    CapabilityGapAnalysis,
    CapabilityProposal,
    CapabilityResult,
    DiagnosticReport,
    ExecutionErrorRecord,
    ExperienceRecord,
    FailureRootCauseCategory,
    ImprovementProposal,
    ImprovementStatus,
    InstructionIntent,
    LiveRunTestRecord,
    LiveTestStatus,
    MemoryCategory,
    MemoryConfidence,
    MemoryRecord,
    PlannedAction,
    ProblemSolvingStrategy,
    RecoveryAttemptRecord,
    SelfImprovementRunRecord,
    TaskLifecycleStage,
    TaskOutcome,
    TaskRequirement,
    TaskState,
    VerificationCheckResult,
    VerificationStatus,
)
from agent911.orchestrator import Agent911Orchestrator
from agent911.strategy import STRATEGY_CATALOG, StrategySelector, StrategySpec

__version__ = "0.1.0"

__all__ = [
    "ActionStatus",
    "Agent911Orchestrator",
    "AgentConfig",
    "CapabilityAvailability",
    "CapabilityCallRecord",
    "CapabilityResult",
    "ConfigurationError",
    "ConnectivityReport",
    "ContextManager",
    "ExecutionErrorRecord",
    "ExperienceRecord",
    "InstructionIntent",
    "LiveRunTestRecord",
    "LiveRunTester",
    "LiveTestStatus",
    "MalformedModelOutputError",
    "MemoryCategory",
    "MemoryConfidence",
    "MemoryRecord",
    "ModelConfig",
    "ModelInterface",
    "ModelProviderError",
    "ModelResponse",
    "OutcomeClassifier",
    "PersistentMemoryStore",
    "PlannedAction",
    "ProviderConnectivityStatus",
    "RecoveryAttemptRecord",
    "TaskLifecycleStage",
    "TaskOutcome",
    "TaskRequirement",
    "TaskState",
    "VerificationCheckResult",
    "VerificationStatus",
    "Verifier",
    "__version__",
    "redact_secrets",
]
