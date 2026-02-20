"""
gemini_client.py — Unified Gemini LLM client for NEXUS.

Tries the new google-genai SDK first; falls back to google-generativeai.
Handles rate-limiting, JSON extraction, and retry logic.
"""

import json
import os
import re
import time
from typing import Optional


class GeminiClient:
    """Google Gemini client with automatic SDK detection and rate-limit handling."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. "
                "Set GEMINI_API_KEY or pass api_key=. "
                "Get a free key at https://aistudio.google.com/apikey"
            )

        self.model_name = model
        self.request_count = 0
        self._last_request_time = 0.0

        # Try new SDK (google-genai) first, fall back to legacy (google-generativeai)
        try:
            from google import genai  # type: ignore
            self._client = genai.Client(api_key=self.api_key)
            self._sdk = "new"
            print(f"  ✅ Gemini ready (google-genai SDK) — {model}")
        except (ImportError, Exception):
            try:
                import google.generativeai as _legacy_genai  # type: ignore
                _legacy_genai.configure(api_key=self.api_key)
                self._legacy = _legacy_genai
                self._sdk = "legacy"
                print(f"  ⚠️  Gemini ready (legacy SDK) — {model}")
                print("      Upgrade for best results: pip install google-genai")
            except ImportError:
                raise ImportError(
                    "No Gemini SDK found. Install one:\n"
                    "  pip install google-genai          (recommended)\n"
                    "  pip install google-generativeai   (legacy)"
                )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _rate_limit(self):
        """Enforce ~13 requests/min to stay within free tier limits."""
        now = time.time()
        elapsed = now - self._last_request_time
        min_gap = 4.5  # seconds between requests
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        self._last_request_time = time.time()
        self.request_count += 1

    # ------------------------------------------------------------------
    # Core generate
    # ------------------------------------------------------------------

    def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8192,
    ) -> str:
        """
        Generate text from Gemini.

        Args:
            system_prompt: Instruction / persona for the model.
            user_message:  The actual user turn content.
            max_tokens:    Upper limit on output tokens.

        Returns:
            Model response as a plain string (empty string on failure).
        """
        self._rate_limit()

        # Combine system + user into a single prompt (works with both SDKs)
        full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"

        for attempt in range(3):
            try:
                if self._sdk == "new":
                    response = self._client.models.generate_content(
                        model=self.model_name,
                        contents=full_prompt,
                        config={
                            "max_output_tokens": max_tokens,
                            "temperature": 0.7,
                        },
                    )
                    return response.text or ""
                else:
                    model = self._legacy.GenerativeModel(self.model_name)
                    response = model.generate_content(
                        full_prompt,
                        generation_config=self._legacy.GenerationConfig(
                            max_output_tokens=max_tokens,
                            temperature=0.7,
                        ),
                    )
                    return response.text or ""

            except Exception as exc:
                err = str(exc).lower()

                # Rate limit / quota — back off and retry
                if "429" in err or "quota" in err or "rate" in err:
                    wait = 60 * (attempt + 1)
                    print(f"  ⏳ Rate limited — waiting {wait}s (attempt {attempt + 1}/3)…")
                    time.sleep(wait)
                    self._last_request_time = time.time()
                    continue

                print(f"  ❌ Gemini error: {exc}")
                return ""

        print("  ❌ Gemini: max retries exceeded")
        return ""

    # ------------------------------------------------------------------
    # JSON extraction
    # ------------------------------------------------------------------

    def extract_json(self, text: str) -> dict:
        """
        Robustly extract a JSON object from a Gemini response.

        Tries direct parse → markdown code block → largest brace block →
        asks Gemini to repair it.
        """
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
                candidate = match.group(1).strip()
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)  # trailing commas
                try:
                    return json.loads(candidate)
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
            best = re.sub(r",\s*([}\]])", r"\1", best)
            try:
                return json.loads(best)
            except json.JSONDecodeError:
                pass

        # 4. Ask Gemini to fix it
        try:
            fixed = self.generate(
                "Return ONLY valid JSON. No markdown. No explanation. Fix the JSON below.",
                text[:3000],
                max_tokens=4096,
            )
            return json.loads(fixed.strip().lstrip("```json").lstrip("```").rstrip("```"))
        except Exception:
            pass

        return {}
