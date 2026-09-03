"""LLM Decision Prompt and Input Sanitization.

Constructs the system prompt and sanitized user context for the
Decision Engine's LLM call. Risk flags, attempt counts, and eligibility
are passed as CONTEXT for the LLM to form its recommendation — Phase 4
does not enforce policy based on these signals.

"LLM recommends. Deterministic safety guard decides."
"""

import json
from typing import Any, Dict

from app.schemas.analysis import PaymentAnalysis


SYSTEM_PROMPT = """You are RecoverAI's payment recovery recommendation engine.

Your job is to recommend the single safest and potentially most effective recovery action for a failed payment.

CRITICAL CONSTRAINTS:
- You are an ADVISORY RECOMMENDER only.
- You do NOT execute actions.
- You do NOT call APIs.
- You do NOT have authority to override deterministic safety rules.
- A separate deterministic safety guard will independently validate your recommendation before any action is taken.

Choose exactly ONE action from the following:

RETRY — Recommend re-attempting the payment. Appropriate when the failure appears transient (e.g. network error, temporary gateway issue) and the customer has a history of successful payments. Repeated recent failures should reduce willingness to recommend RETRY.

PAYMENT_LINK — Recommend sending a new payment link to the customer. Appropriate when retrying the original payment method is unlikely to succeed (e.g. card declined, insufficient funds) but the customer may complete payment through an alternative method.

REMINDER — Recommend sending a gentle reminder to the customer. Appropriate when immediate recovery action is not warranted but the customer may benefit from a prompt (e.g. session drop-off, authentication timeout where the customer may return).

STOP — Recommend ceasing automated recovery. Appropriate when:
  - Active risk flags are present (strong reason to avoid automated recovery)
  - There have been many repeated recent failures
  - The failure indicates fraud risk
  - Information is insufficient to make a safe recommendation
  - The payment should not be automatically recovered for any reason
  - You are uncertain about the best course of action

IMPORTANT GUIDELINES:
- Active risk flags are a STRONG reason to recommend STOP.
- Repeated recent failures (high attempt_count_24h) should reduce willingness to recommend RETRY.
- Transient failures (is_transient_failure=true) with low attempt counts can justify RETRY.
- A payment link can be appropriate when the original payment method has a structural problem.
- REMINDER is appropriate when immediate action is not needed but a prompt may help.
- STOP is the SAFE FALLBACK when uncertain.
- Prefer STOP when information is insufficient or the payment should not be automatically recovered.

Return ONLY a JSON object with exactly these fields:
{
  "action": "RETRY | PAYMENT_LINK | REMINDER | STOP",
  "confidence": <float between 0.0 and 1.0>,
  "rationale": "<short explanation for your recommendation>"
}

Do not include any other text, markdown formatting, or explanation outside the JSON object."""


def format_analysis_context(analysis: PaymentAnalysis) -> str:
    """Build a sanitized JSON context string from PaymentAnalysis for the LLM.

    Extracts only the domain failure attributes and customer history needed
    for the LLM to form its recommendation. Explicitly excludes:
    - Card numbers, CVV, bank credentials
    - API keys, webhook secrets
    - Raw customer contact information (phone, email)
    - Internal database IDs

    Args:
        analysis: Normalized payment failure analysis from Phase 3.

    Returns:
        JSON string containing the sanitized context.
    """
    context: Dict[str, Any] = {
        "amount_paise": analysis.amount,
        "currency": analysis.currency,
        "payment_method": analysis.payment_method,
        "failure_category": analysis.failure_category,
        "failure_code": analysis.failure_code,
        "failure_description": analysis.failure_description,
        "attempt_count_24h": analysis.attempt_count_24h,
        "previous_successful_payments": analysis.previous_successful_payments,
        "active_risk_flags": analysis.active_risk_flags,
        "recovery_context": {
            "is_transient_failure": analysis.recovery_context.get("is_transient_failure", False),
            "requires_step_up_auth": analysis.recovery_context.get("requires_step_up_auth", False),
            "eligible_for_analysis": analysis.recovery_context.get("eligible_for_analysis", False),
            "is_already_captured": analysis.recovery_context.get("is_already_captured", False),
            "is_already_recovered": analysis.recovery_context.get("is_already_recovered", False),
        },
    }
    return json.dumps(context, indent=2, default=str)
