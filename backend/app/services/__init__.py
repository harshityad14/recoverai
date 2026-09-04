"""Application Services Package."""

from typing import Any

__all__ = [
    "ActionExecutor",
    "AnalysisService",
    "DecisionEngine",
    "FailureClassifier",
    "RazorpayClient",
    "RecoveryMetricsService",
    "SafetyGuard",
]


def __getattr__(name: str) -> Any:
    """Lazy module-level attribute loader to prevent circular imports."""
    if name == "ActionExecutor":
        from app.services.action_executor import ActionExecutor
        return ActionExecutor
    elif name == "RazorpayClient":
        from app.services.razorpay_client import RazorpayClient
        return RazorpayClient
    elif name == "SafetyGuard":
        from app.services.safety_guard import SafetyGuard
        return SafetyGuard
    elif name == "AnalysisService":
        from app.services.analysis_service import AnalysisService
        return AnalysisService
    elif name == "FailureClassifier":
        from app.services.failure_classifier import FailureClassifier
        return FailureClassifier
    elif name == "DecisionEngine":
        from app.services.llm.decision_engine import DecisionEngine
        return DecisionEngine
    elif name == "RecoveryMetricsService":
        from app.services.metrics_service import RecoveryMetricsService
        return RecoveryMetricsService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
