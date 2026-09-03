"""LLM Decision Engine Package.

Advisory recommendation layer for payment recovery decisions.
"LLM recommends. Deterministic safety guard decides."

This package provides:
- RecoveryAction: Enum of allowed recovery action recommendations.
- RecoveryDecision: Pydantic model for validated LLM decision output.
- LLMClient: Protocol for provider-agnostic LLM interaction.
- GeminiLLMClient: Production Google Gemini adapter.
- DecisionEngine: Orchestrates LLM recommendation from PaymentAnalysis.
"""

from app.services.llm.schemas import RecoveryAction, RecoveryDecision, create_fallback_decision
from app.services.llm.client import LLMClient, GeminiLLMClient
from app.services.llm.decision_engine import DecisionEngine

__all__ = [
    "RecoveryAction",
    "RecoveryDecision",
    "create_fallback_decision",
    "LLMClient",
    "GeminiLLMClient",
    "DecisionEngine",
]
