"""
fallback_client.py — Transparent dual-LLM client with automatic failover.

Wraps two LLM clients (primary + secondary) behind a single interface.
When the primary returns empty (rate-limited, exhausted, or errored),
the secondary is tried automatically with no build interruption.

Typical usage: Groq as primary (fast, free, TPM-limited),
               Gemini as secondary (slower pacing, independent quota).

Both clients must implement:
    .generate(system_prompt, user_message, max_tokens=...) -> str
    .extract_json(text) -> dict
"""

import time
from typing import Optional


class FallbackLLMClient:
    """
    Dual-LLM client that falls back from primary to secondary on failure.

    Failure is defined as the primary returning an empty string — which
    happens when Groq's generate() exhausts all retries after 429s.
    """

    def __init__(self, primary, secondary, cooldown: int = 120):
        """
        Args:
            primary:   First-choice LLM client (e.g. GroqClient).
            secondary: Fallback LLM client    (e.g. GeminiClient).
            cooldown:  Seconds to wait before retrying primary after it failed.
        """
        self.primary = primary
        self.secondary = secondary
        self._cooldown = cooldown

        # Track which provider was used last (for extract_json routing)
        self._last_used = "primary"

        # When the primary last failed (for cooldown tracking)
        self._primary_failed_at: Optional[float] = None

        # Cumulative failure counts
        self._primary_failures = 0
        self._secondary_failures = 0

    # ------------------------------------------------------------------
    # Core interface (mirrors GeminiClient / GroqClient)
    # ------------------------------------------------------------------

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 6000,
        **kwargs,
    ) -> str:
        """
        Try primary first; fall back to secondary if primary returns empty.
        After cooldown, primary is retried automatically.
        """
        use_primary = self._should_use_primary()

        if use_primary:
            result = self._call_primary(system_prompt, user_message, max_tokens, **kwargs)
            if result:
                self._last_used = "primary"
                return result
            # Primary failed — record failure and try secondary
            self._primary_failures += 1
            self._primary_failed_at = time.time()
            name_p = _client_name(self.primary)
            name_s = _client_name(self.secondary)
            print(f"  🔄 {name_p} returned empty — switching to {name_s} fallback…")

        # Try secondary
        result = self._call_secondary(system_prompt, user_message, max_tokens, **kwargs)
        if result:
            self._last_used = "secondary"
            return result

        self._secondary_failures += 1
        print(f"  ❌ Both LLM providers returned empty for this call")
        return ""

    def extract_json(self, text: str) -> dict:
        """Route JSON extraction to whichever client responded last."""
        if self._last_used == "secondary":
            return self.secondary.extract_json(text)
        return self.primary.extract_json(text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_use_primary(self) -> bool:
        """Return True if the primary should be attempted."""
        if self._primary_failed_at is None:
            return True
        elapsed = time.time() - self._primary_failed_at
        if elapsed >= self._cooldown:
            # Cooldown expired — try primary again
            self._primary_failed_at = None
            return True
        return False

    def _call_primary(self, system_prompt, user_message, max_tokens, **kwargs):
        try:
            # Pass fail_fast=True so primary returns immediately on rate-limit
            # instead of sleeping — we'll use secondary instead.
            return self.primary.generate(
                system_prompt, user_message,
                max_tokens=max_tokens, fail_fast=True, **kwargs,
            )
        except TypeError:
            # Primary doesn't support fail_fast (older client); call without it.
            try:
                return self.primary.generate(system_prompt, user_message,
                                             max_tokens=max_tokens, **kwargs)
            except Exception as exc:
                print(f"  ⚠️  Primary LLM exception: {exc}")
                return ""
        except Exception as exc:
            print(f"  ⚠️  Primary LLM exception: {exc}")
            return ""

    def _call_secondary(self, system_prompt, user_message, max_tokens, **kwargs):
        try:
            # Always fail_fast on secondary: primary already failed, so if secondary
            # is also rate-limited we want an instant empty return, not more sleeping.
            kwargs.setdefault("fail_fast", True)
            return self.secondary.generate(system_prompt, user_message,
                                           max_tokens=min(max_tokens, 8192), **kwargs)
        except TypeError:
            # Secondary doesn't support fail_fast — call without it.
            try:
                kwargs.pop("fail_fast", None)
                return self.secondary.generate(system_prompt, user_message,
                                               max_tokens=min(max_tokens, 8192), **kwargs)
            except Exception as exc:
                print(f"  ⚠️  Secondary LLM exception: {exc}")
                return ""
        except Exception as exc:
            print(f"  ⚠️  Secondary LLM exception: {exc}")
            return ""

    # ------------------------------------------------------------------
    # Stats / diagnostics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        stats: dict = {
            "mode": "fallback",
            "primary": _client_name(self.primary),
            "secondary": _client_name(self.secondary),
            "last_used": self._last_used,
            "primary_failures": self._primary_failures,
            "secondary_failures": self._secondary_failures,
        }
        # Merge provider stats if available
        if hasattr(self.primary, "get_stats"):
            stats["primary_stats"] = self.primary.get_stats()
        if hasattr(self.secondary, "get_stats"):
            stats["secondary_stats"] = self.secondary.get_stats()
        return stats


def _client_name(client) -> str:
    """Return a short human-readable name for a client."""
    name = type(client).__name__
    if hasattr(client, "model_name"):
        return f"{name}({client.model_name})"
    return name
