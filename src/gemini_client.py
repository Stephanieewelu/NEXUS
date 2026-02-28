"""
gemini_client.py — Gemini client with SMART rate limiting for free tier.

Free tier limits (as of 2025):
  gemini-2.0-flash:  15 RPM, 1500 RPD, 1M TPM
  gemini-2.5-flash:  ~10 RPM (stricter)
  gemini-1.5-flash:  15 RPM

Strategy: PREVENT 429s with proactive pacing instead of
          retrying after they happen.
"""

import json
import os
import re
import time
from collections import deque
from typing import Optional


class GeminiClient:
    """Gemini client that carefully manages free-tier rate limits."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. "
                "Set GEMINI_API_KEY or pass api_key=.\n"
                "Get a free key at https://aistudio.google.com/apikey"
            )

        self.model_name = model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

        # ── Smart rate limiting state ──
        self._request_timestamps: deque = deque(maxlen=20)
        self._rpm_limit = 10          # stay under the real limit
        self._min_delay = 7.0         # minimum seconds between requests
        self._daily_count = 0
        self._daily_limit = 1400      # stay under 1500 RPD
        self._day_start = time.time()

        self._init_sdk()

    # ------------------------------------------------------------------
    # SDK initialisation
    # ------------------------------------------------------------------

    def _init_sdk(self):
        """Try new google-genai SDK first; fall back to google-generativeai."""
        try:
            from google import genai  # type: ignore
            self._client = genai.Client(api_key=self.api_key)
            self._sdk = "new"
            print(f"  ✅ Gemini ready (google-genai SDK) — {self.model_name}")
        except (ImportError, Exception):
            try:
                import google.generativeai as _legacy  # type: ignore
                _legacy.configure(api_key=self.api_key)
                self._legacy = _legacy
                self._sdk = "legacy"
                print(f"  ⚠️  Gemini ready (legacy SDK) — {self.model_name}")
                print("      Upgrade: pip install google-genai")
            except ImportError:
                raise ImportError(
                    "No Gemini SDK found.\n"
                    "  pip install google-genai          (recommended)\n"
                    "  pip install google-generativeai   (legacy)"
                )

    # ------------------------------------------------------------------
    # Smart rate limiting
    # ------------------------------------------------------------------

    def _smart_rate_limit(self):
        """
        Proactively pace requests to prevent 429 errors before they occur.
        """
        now = time.time()

        # Reset daily counter after 24 h
        if now - self._day_start > 86400:
            self._daily_count = 0
            self._day_start = now

        # Hard daily limit
        if self._daily_count >= self._daily_limit:
            print("  🛑 Daily limit approaching — waiting 5 min…")
            time.sleep(300)
            self._daily_count = 0
            self._day_start = time.time()

        # Enforce minimum gap between requests
        if self._request_timestamps:
            elapsed = now - self._request_timestamps[-1]
            if elapsed < self._min_delay:
                wait = self._min_delay - elapsed
                print(f"  ⏳ Pacing: {wait:.0f}s until next request…")
                time.sleep(wait)

        # Check RPM window
        one_min_ago = time.time() - 60
        recent = [t for t in self._request_timestamps if t > one_min_ago]

        if len(recent) >= self._rpm_limit:
            oldest = min(recent)
            wait = 61 - (time.time() - oldest)
            if wait > 0:
                print(
                    f"  ⏳ RPM limit ({len(recent)}/{self._rpm_limit}): "
                    f"waiting {wait:.0f}s…"
                )
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
        retries: int = 2,
    ) -> str:
        """
        Generate text with smart proactive rate limiting.

        Args:
            system_prompt: Instruction / persona for the model.
            user_message:  The actual user turn content.
            max_tokens:    Upper limit on output tokens.
            retries:       Max attempts on transient errors (default 2 to cap waits).

        Returns:
            Model response as a plain string (empty on failure).
        """
        self._smart_rate_limit()

        full_prompt = f"{system_prompt}\n\n---\n\n{user_message}"

        for attempt in range(retries):
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

                if "429" in err or "quota" in err or "rate" in err:
                    # Use API-suggested wait if available; otherwise use RPM-based wait.
                    # Gemini's RPM window is 60s, so 30s*(attempt+1) is enough.
                    retry_after = self._parse_retry_after(str(exc))
                    if retry_after:
                        wait = retry_after + 3
                        print(
                            f"  ⏳ Rate limited - Gemini says wait {retry_after}s "
                            f"(attempt {attempt + 1}/{retries})"
                        )
                    else:
                        wait = 30 * (attempt + 1)   # 30s, 60s — much less than Groq's 65/130s
                        print(
                            f"  ⏳ Rate limited (attempt {attempt + 1}/{retries}) — "
                            f"waiting {wait}s…"
                        )
                    time.sleep(wait)
                    # Increase future pacing slightly but cap it
                    self._min_delay = min(12.0, self._min_delay + 1.0)
                    print(f"  📊 Adjusted pacing to {self._min_delay:.0f}s/request")
                    continue

                if "block" in err or "safety" in err:
                    print("  ⚠️  Content filtered — retrying with shorter prompt…")
                    full_prompt = full_prompt[:2000]
                    continue

                print(f"  ❌ Gemini error: {exc}")
                if attempt < retries - 1:
                    time.sleep(10)
                    continue
                return ""

        print(f"  ❌ Failed after {retries} attempts")
        return ""

    @staticmethod
    def _parse_retry_after(error_text: str) -> Optional[int]:
        """Extract retry-after seconds from a Gemini 429 error message."""
        for pattern in [
            r"retry.{0,10}after\s+(\d+)",
            r"retryDelay[\"']?\s*:\s*[\"']?(\d+)",
            r"try again in\s+(\d+(?:\.\d+)?)\s*s",
            r"wait\s+(\d+)\s*second",
            r'"retry_after"\s*:\s*(\d+)',
        ]:
            m = re.search(pattern, error_text, re.IGNORECASE)
            if m:
                return max(1, int(float(m.group(1))))
        return None

    # ------------------------------------------------------------------
    # JSON extraction
    # ------------------------------------------------------------------

    def extract_json(self, text: str) -> dict:
        """Robustly extract a JSON object from a Gemini response."""
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
                candidate = self._clean_json(match.group(1).strip())
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
            try:
                return json.loads(self._clean_json(best))
            except json.JSONDecodeError:
                pass

        # 4. Ask Gemini to repair (1 retry only — don't burn rate limit on repair)
        if len(text) > 50:
            print("  ⚠️  Repairing JSON…")
            try:
                fixed = self.generate(
                    "Return ONLY valid JSON. No markdown. No explanation. Fix the JSON below.",
                    text[:3000],
                    max_tokens=4096,
                    retries=1,
                )
                fixed = fixed.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
                return json.loads(fixed)
            except Exception:
                pass

        return {}

    @staticmethod
    def _clean_json(text: str) -> str:
        """Fix common JSON issues: trailing commas, JS comments."""
        text = re.sub(r",\s*([}\]])", r"\1", text)          # trailing commas
        text = re.sub(r"//[^\n]*", "", text)                 # line comments
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)  # block comments
        return text.strip()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        now = time.time()
        recent = sum(1 for t in self._request_timestamps if t > now - 60)
        return {
            "model": self.model_name,
            "sdk": self._sdk,
            "requests_last_minute": recent,
            "rpm_limit": self._rpm_limit,
            "daily_count": self._daily_count,
            "daily_limit": self._daily_limit,
            "pacing": f"{self._min_delay:.0f}s between requests",
        }
