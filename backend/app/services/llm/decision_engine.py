"""LLM Decision Engine.

Advisory recommendation layer that consumes a normalized PaymentAnalysis
from Phase 3 and produces a RecoveryDecision recommendation.

This engine is a RECOMMENDER ONLY. It:
- Does NOT execute recovery actions.
- Does NOT call Razorpay APIs.
- Does NOT modify Transaction.status.
- Does NOT authorize action execution.
- Does NOT replace the Phase 5 Deterministic Safety Guard.

"LLM recommends. Deterministic safety guard decides."
"""

import json
import logging
import re
from typing import Optional

from app.schemas.analysis import PaymentAnalysis
from app.services.llm.client import LLMClient
from app.services.llm.prompts import SYSTEM_PROMPT, format_analysis_context
from app.services.llm.schemas import RecoveryDecision, create_fallback_decision

logger = logging.getLogger(__name__)


class DecisionEngine:
    """Orchestrates LLM-based recovery action recommendations.

    Accepts a PaymentAnalysis, sanitizes the input, calls the LLM via the
    injected LLMClient, and validates the response into a RecoveryDecision.

    The output is an advisory RECOMMENDATION — not a permission, authorization,
    or execution command. Phase 5 (Deterministic Safety Guard) independently
    validates, overrides, or blocks the recommendation.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """Initialize the Decision Engine.

        Args:
            llm_client: An LLMClient implementation for generating decisions.
                        In production, use GeminiLLMClient.
                        In tests, inject a MockLLMClient.
                        If None, all calls return a safe STOP fallback.
        """
        self._llm_client = llm_client

    def recommend_action(self, analysis: PaymentAnalysis) -> RecoveryDecision:
        """Produce a recovery action recommendation from a PaymentAnalysis.

        This method:
        1. Checks if recovery analysis is eligible (cost optimization to
           avoid a wasteful LLM call — NOT safety enforcement).
        2. Sanitizes the analysis into an LLM-safe context.
        3. Calls the LLM client to generate a recommendation.
        4. Parses and validates the response via Pydantic.
        5. Returns a deterministic STOP fallback on any error.

        The returned RecoveryDecision is an advisory recommendation.
        Phase 5 independently enforces deterministic safety rules.

        Args:
            analysis: Normalized payment failure analysis from Phase 3.

        Returns:
            RecoveryDecision: Validated advisory recommendation.
                              Never raises — always returns a valid decision.
        """
        payment_ref = analysis.razorpay_payment_id

        # --- Early exit: no LLM client configured ---
        if self._llm_client is None:
            logger.warning(
                "No LLM client configured for payment %s; returning safe fallback recommendation",
                payment_ref,
            )
            return create_fallback_decision(
                "No LLM client configured; returning safe fallback recommendation."
            )

        # --- Early exit: ineligible for analysis (cost optimization) ---
        # This avoids a wasteful LLM call when the analysis service has
        # already determined the transaction is ineligible. This is NOT
        # safety enforcement — Phase 5 will independently verify eligibility.
        if not analysis.recovery_context.get("eligible_for_analysis", False):
            logger.info(
                "Payment %s ineligible for analysis; returning STOP recommendation "
                "(cost optimization, not safety enforcement)",
                payment_ref,
            )
            return create_fallback_decision(
                "Payment ineligible for recovery analysis; "
                "recommending STOP (Phase 5 will independently verify)."
            )

        # --- Build sanitized context ---
        try:
            user_context = format_analysis_context(analysis)
        except Exception as e:
            logger.error(
                "Failed to format analysis context for payment %s: %s",
                payment_ref,
                str(e),
            )
            return create_fallback_decision(
                f"Failed to format analysis context: {e}"
            )

        # --- Call LLM ---
        try:
            raw_response = self._llm_client.generate_decision(
                system_prompt=SYSTEM_PROMPT,
                user_content=user_context,
            )
        except TimeoutError as e:
            logger.warning(
                "LLM timeout for payment %s: %s",
                payment_ref,
                str(e),
            )
            return create_fallback_decision(
                f"LLM provider timeout: {e}"
            )
        except ConnectionError as e:
            logger.warning(
                "LLM connection error for payment %s: %s",
                payment_ref,
                str(e),
            )
            return create_fallback_decision(
                f"LLM provider connection error: {e}"
            )
        except Exception as e:
            logger.warning(
                "LLM provider error for payment %s: %s",
                payment_ref,
                str(e),
            )
            return create_fallback_decision(
                f"LLM provider error: {e}"
            )

        # --- Parse and validate response ---
        try:
            decision = self._parse_response(raw_response)
        except Exception as e:
            logger.warning(
                "Failed to parse LLM response for payment %s: %s",
                payment_ref,
                str(e),
            )
            return create_fallback_decision(
                f"Failed to parse LLM response: {e}"
            )

        logger.info(
            "LLM recommendation for payment %s: action=%s, confidence=%.2f",
            payment_ref,
            decision.action.value,
            decision.confidence,
        )
        return decision

    @staticmethod
    def _parse_response(raw_response: str) -> RecoveryDecision:
        """Parse and validate a raw LLM text response into a RecoveryDecision.

        Handles:
        - Plain JSON strings.
        - Markdown code fences (```json ... ``` or ``` ... ```).
        - Harmless surrounding whitespace.
        - Controlled leading/trailing explanatory text around a JSON block.

        Args:
            raw_response: Raw text response from the LLM.

        Returns:
            Validated RecoveryDecision.

        Raises:
            ValueError: If the response is empty, does not contain a JSON object,
                        or extracted content is not a dictionary.
            json.JSONDecodeError: If candidate JSON cannot be decoded.
            pydantic.ValidationError: If the JSON does not conform to RecoveryDecision.
        """
        if not raw_response or not raw_response.strip():
            raise ValueError("Empty LLM response")

        text = raw_response.strip()
        candidate: Optional[str] = None

        # 1. Check for markdown code fences (```json ... ``` or ``` ... ```)
        # Allows optional leading/trailing conversational text around the code fence.
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1).strip()
        elif text.startswith("{") and text.endswith("}"):
            # 2. Pure JSON object
            candidate = text
        elif text.startswith("[") and text.endswith("]"):
            raise ValueError("Response is a JSON array, expected a single JSON object")
        else:
            # 3. Controlled extraction: locate the outermost JSON object bounds
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                prefix = text[:first_brace].strip()
                suffix = text[last_brace + 1:].strip()
                if prefix.endswith("[") and suffix.startswith("]"):
                    raise ValueError("JSON object is enclosed in an array, expected a single object")
                candidate = text[first_brace : last_brace + 1].strip()
            else:
                raise ValueError("No JSON object found in response")

        if not candidate:
            raise ValueError("Could not extract candidate JSON from response")

        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Extracted JSON is not a JSON object/dictionary")

        return RecoveryDecision.model_validate(parsed)
