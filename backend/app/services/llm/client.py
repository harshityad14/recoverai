"""LLM Client Protocol and Google Gemini Adapter.

Provides a protocol-based abstraction over LLM providers so the Decision Engine
does not directly depend on any specific SDK. The GeminiLLMClient is the
production adapter; unit tests inject a MockLLMClient implementing the same protocol.

The client is responsible only for sending prompts and returning raw text responses.
It has no knowledge of payment semantics, recovery actions, or transaction states.
"""

import logging
from typing import Protocol, runtime_checkable

from app.core.config import settings

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for provider-agnostic LLM interaction.

    Any implementation must accept a system prompt and user content string,
    and return the raw text response from the LLM provider.
    """

    def generate_decision(self, system_prompt: str, user_content: str) -> str:
        """Send a decision prompt to the LLM and return the raw text response.

        Args:
            system_prompt: The system-level instruction prompt.
            user_content: The user-level context (sanitized payment analysis).

        Returns:
            Raw text response from the LLM provider.

        Raises:
            TimeoutError: If the LLM provider does not respond in time.
            Exception: For any provider-level error (network, API, auth, etc.).
        """
        ...  # pragma: no cover


class GeminiLLMClient:
    """Production Google Gemini adapter implementing LLMClient protocol.

    Wraps the Google GenAI SDK to send structured prompts and extract text
    responses. Configures model, timeout, and temperature from application
    settings. API key is read from settings (environment variable), never
    hard-coded.

    This client is NEVER instantiated during tests — tests inject a
    MockLLMClient via dependency injection instead.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        temperature: float | None = None,
    ):
        """Initialize the Gemini client.

        Args:
            api_key: Gemini API key. Defaults to settings.GEMINI_API_KEY.
            model: Model identifier. Defaults to settings.LLM_MODEL.
            timeout: Request timeout in seconds. Defaults to settings.LLM_TIMEOUT_SECONDS.
            temperature: Sampling temperature. Defaults to settings.LLM_TEMPERATURE.

        Raises:
            ValueError: If no API key is available (prevents accidental
                        instantiation without credentials).
        """
        resolved_key = api_key or settings.GEMINI_API_KEY
        if not resolved_key:
            raise ValueError(
                "GeminiLLMClient requires an API key. "
                "Set GEMINI_API_KEY in environment or pass api_key= explicitly. "
                "For tests, use MockLLMClient instead."
            )

        self._model = model or settings.LLM_MODEL
        self._timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS
        self._temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE

        # Defer import so the google-genai SDK is only loaded when this adapter
        # is actually instantiated (never during tests).
        from google import genai
        from google.genai import types
        self._genai = genai
        self._types = types

        # Configure HTTP request timeout in milliseconds for google-genai SDK
        timeout_ms = int(self._timeout * 1000)
        self._http_options = types.HttpOptions(timeout=timeout_ms)

        self._client = genai.Client(
            api_key=resolved_key,
            http_options=self._http_options,
        )

    def generate_decision(self, system_prompt: str, user_content: str) -> str:
        """Send a decision prompt to Gemini and return the raw text response.

        Args:
            system_prompt: The system-level instruction prompt.
            user_content: The user-level context (sanitized payment analysis).

        Returns:
            Raw text response from Gemini.

        Raises:
            TimeoutError: If the request times out.
            ConnectionError: If the provider cannot be reached.
            RuntimeError: For any Gemini API-level error.
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_content,
                config=self._types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self._temperature,
                    max_output_tokens=512,
                    http_options=self._http_options,
                ),
            )

            # Extract text content from the response
            if response.text:
                return response.text
            return ""

        except TimeoutError as e:
            logger.warning("Gemini API timeout: %s", str(e))
            raise TimeoutError(f"LLM provider timeout: {e}") from e
        except ConnectionError as e:
            logger.warning("Gemini API connection error: %s", str(e))
            raise ConnectionError(f"LLM provider connection error: {e}") from e
        except Exception as e:
            error_msg = str(e)
            logger.warning("Gemini API error: %s", error_msg)
            # Check for HTTP status errors in the exception message
            if "timeout" in error_msg.lower():
                raise TimeoutError(f"LLM provider timeout: {e}") from e
            raise RuntimeError(f"LLM provider error: {e}") from e
