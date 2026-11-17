"""Versioned, strict data contracts shared by every interface.

All models forbid unknown fields so malformed payloads fail loudly instead of
being silently repaired into confident answers.
"""

from humour_engine.contracts.analysis import (  # noqa: F401
    SCHEMA_VERSION,
    AnalysisMode,
    AnalysisRequest,
    AnalysisResult,
    AudienceAssessment,
    Budget,
    ComicReading,
    ContextBlock,
    ContextDependency,
    Counterfactual,
    EngineError,
    Evidence,
    HumourAttempt,
    Interpretation,
    ProviderPolicy,
    ReportedIntent,
    ResultStatus,
    Segment,
    TaskName,
    TaskResult,
    TaskStatus,
    Truncation,
    Uncertainty,
    Usage,
    Versions,
)
from humour_engine.contracts.compare import CompareRequest, CompareResult  # noqa: F401
