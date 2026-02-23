"""
groq_client.py — Groq LLM client for NEXUS.

Drop-in replacement for GeminiClient (same .generate() / .extract_json() interface).

Free tier (2025):
  llama-3.3-70b-versatile:  30 RPM, 14,400 RPD, 131K context
  llama-3.1-8b-instant:     30 RPM, 14,400 RPD, 131K context (faster)
  mixtral-8x7b-32768:       30 RPM, 14,400 RPD, 32K context
"""

import json
import os
import re
import time
from collections import deque
from typing import Optional


class GroqClient:
    """Groq client — free, fast, generous limits."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Groq API key not found. "
                "Set GROQ_API_KEY or pass api_key=.\n"
                "Get a free key at https://console.groq.com/keys"
            )

        self.model_name = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        # ── Rate limiting (generous but safe) ──
        self._request_timestamps: deque = deque(maxlen=40)
        self._rpm_limit = 25          # stay under 30 RPM
        self._min_delay = 2.5         # seconds between requests
        self._daily_count = 0
        self._daily_limit = 14000     # stay under 14,400 RPD
        self._day_start = time.time()

        # ── Token tracking ──
        self._tokens_this_minute = 0
        self._token_window_start = time.time()

        try:
            from groq import Groq  # type: ignore
            self._client = Groq(api_key=self.api_key)
            print(f"  ✅ Groq ready — {self.model_name}")
            print(f"     Limits: {self._rpm_limit} RPM, {self._daily_limit} RPD, {self._min_delay}s pacing")
        except ImportError:
            raise ImportError("Groq SDK not found. Run: pip install groq")

    # ------------------------------------------------------------------
    # Smart rate limiting
    # ------------------------------------------------------------------

    def _smart_rate_limit(self):
        """Proactively pace requests to prevent 429s."""
        now = time.time()

        # Daily reset
        if now - self._day_start > 86400:
            self._daily_count = 0
            self._day_start = now

        # Daily cap
        if self._daily_count >= self._daily_limit:
            print("  🛑 Daily limit approaching — waiting 5 min…")
            time.sleep(300)
            self._daily_count = 0
            self._day_start = time.time()

        # Minimum gap
        if self._request_timestamps:
            elapsed = now - self._request_timestamps[-1]
            if elapsed < self._min_delay:
                wait = self._min_delay - elapsed
                if wait > 1:
                    print(f"  ⏳ Pacing: {wait:.0f}s…")
                time.sleep(wait)

        # RPM window
        one_min_ago = time.time() - 60
        recent = [t for t in self._request_timestamps if t > one_min_ago]
        if len(recent) >= self._rpm_limit:
            oldest = min(recent)
            wait = 61 - (time.time() - oldest)
            if wait > 0:
                print(f"  ⏳ RPM limit ({len(recent)}/{self._rpm_limit}): waiting {wait:.0f}s…")
                time.sleep(wait)

        self._request_timestamps.append(time.time())
        self._daily_count += 1

    # ------------------------------------------------------------------
    # Core generate
    # ------------------------------------------------------------------

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8192,
        retries: int = 3,
    ) -> str:
        """
        Generate text using Groq.

        Args:
            system_prompt: System instruction / persona.
            user_message:  User turn content.
            max_tokens:    Max output tokens (capped at 8192 for Groq).
            retries:       Max attempts on transient errors.

        Returns:
            Model response as a plain string (empty on failure).
        """
        self._smart_rate_limit()

        # Truncate input if needed (~131K context, but be safe)
        max_input_chars = 100_000
        if len(system_prompt) + len(user_message) > max_input_chars:
            available = max_input_chars - len(system_prompt)
            user_message = user_message[:max(available, 500)]
            print(f"  ✂️  Truncated input to ~{max_input_chars // 4} tokens")

        for attempt in range(retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    max_tokens=min(max_tokens, 8192),
                    temperature=0.7,
                    top_p=0.95,
                )

                text = response.choices[0].message.content or ""

                if response.usage:
                    self._tokens_this_minute += (
                        response.usage.prompt_tokens + response.usage.completion_tokens
                    )

                return text

            except Exception as exc:
                err = str(exc).lower()

                if "429" in err or "rate" in err or "limit" in err:
                    wait = 30 * (attempt + 1)   # 30s, 60s, 90s
                    print(f"  ⏳ Rate limited (attempt {attempt + 1}/{retries}) — waiting {wait}s…")
                    time.sleep(wait)
                    self._min_delay = min(10.0, self._min_delay + 1.0)
                    continue

                if "context" in err or "token" in err:
                    print("  ✂️  Input too long — halving and retrying…")
                    user_message = user_message[: len(user_message) // 2]
                    continue

                if "invalid" in err and "api" in err:
                    print("  ❌ Invalid API key. Check GROQ_API_KEY.")
                    return ""

                print(f"  ❌ Groq error: {exc}")
                if attempt < retries - 1:
                    time.sleep(5)
                    continue
                return ""

        print(f"  ❌ Failed after {retries} attempts")
        return ""

    # ------------------------------------------------------------------
    # JSON extraction (identical interface to GeminiClient)
    # ------------------------------------------------------------------

    def extract_json(self, text: str) -> dict:
        """Robustly extract a JSON object from an LLM response."""
        if not text:
            return {}

        text = text.strip()

        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Fenced code block
        for pattern in [r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"]:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(self._clean_json(match.group(1)))
                except json.JSONDecodeError:
                    continue

        # 3. Largest braced block
        depth, start, best = 0, -1, ""
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    candidate = text[start : i + 1]
                    if len(candidate) > len(best):
                        best = candidate
        if best:
            try:
                return json.loads(self._clean_json(best))
            except json.JSONDecodeError:
                pass

        # 4. Ask Groq to repair
        if len(text) > 50:
            print("  ⚠️  Repairing malformed JSON…")
            try:
                fixed = self.generate(
                    "You are a JSON repair tool. Return ONLY valid JSON. "
                    "No markdown, no code blocks, no explanation. Fix the JSON below.",
                    text[:4000],
                    max_tokens=4096,
                )
                fixed = fixed.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                return json.loads(fixed)
            except Exception:
                pass

        return {}

    @staticmethod
    def _clean_json(text: str) -> str:
        text = re.sub(r",\s*([}\]])", r"\1", text)             # trailing commas
        text = re.sub(r"//[^\n]*", "", text)                   # line comments
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL) # block comments
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)          # control chars
        return text.strip()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        now = time.time()
        recent = sum(1 for t in self._request_timestamps if t > now - 60)
        return {
            "provider": "groq",
            "model": self.model_name,
            "requests_last_minute": recent,
            "rpm_limit": self._rpm_limit,
            "daily_count": self._daily_count,
            "daily_limit": self._daily_limit,
            "pacing": f"{self._min_delay}s between requests",
            "tokens_this_minute": self._tokens_this_minute,
        }
