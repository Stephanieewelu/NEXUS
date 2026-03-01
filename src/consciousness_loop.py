"""
consciousness_loop.py — The main "life" loop of NEXUS.

Drives the agent's interactive lifecycle:
    WAKE  → SENSE → THINK → ACT → FEEL → LEARN → DREAM → EVOLVE → repeat

Commands understood in the REPL:
    build <description>  — Build a full app using the BuildOrchestrator
    status               — Show internal state report
    dream                — Trigger a manual dream cycle
    evolve               — Trigger a manual evolution step
    memories             — Show the memory ecology
    drift                — Show personality / cognitive drift report
    memes                — Show meme pool status
    save [path]          — Save state to disk
    load [path]          — Load state from disk
    quit                 — Hibernate and exit

LLM provider selection (checked in order):
    1. LLM_PROVIDER env var  ("groq" | "gemini" | "auto")
    2. Both keys set → FallbackLLMClient (Groq primary, Gemini secondary)
    3. Only GROQ_API_KEY   → GroqClient
    4. Only GEMINI_API_KEY → GeminiClient
"""

import os
import sys
from typing import Optional

from nexus_core import NexusCore


def _init_llm(
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
):
    """
    Initialise the best available LLM client.

    When both GROQ_API_KEY and GEMINI_API_KEY are set, returns a
    FallbackLLMClient that uses Groq as primary and Gemini as secondary.
    If Groq returns empty (rate-limited), the call is automatically
    retried with Gemini — no build interruption, no waiting.
    """
    provider = provider or os.environ.get("LLM_PROVIDER", "auto")

    def _try_groq():
        from groq_client import GroqClient  # type: ignore
        key = api_key or os.environ.get("GROQ_API_KEY", "")
        return GroqClient(api_key=key, model=model)

    def _try_gemini():
        from gemini_client import GeminiClient  # type: ignore
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        default_model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        return GeminiClient(api_key=key, model=model or default_model)

    if provider == "groq":
        return _try_groq()

    if provider == "gemini":
        return _try_gemini()

    # auto — prefer a dual-provider fallback when both keys exist
    groq_key = api_key or os.environ.get("GROQ_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if groq_key and gemini_key:
        try:
            from fallback_client import FallbackLLMClient  # type: ignore
            groq_client = _try_groq()
            gemini_client = _try_gemini()
            client = FallbackLLMClient(primary=groq_client, secondary=gemini_client)
            print("  🔀 Dual-LLM mode: Groq (primary) + Gemini (fallback)")
            return client
        except Exception as exc:
            print(f"  ⚠️  Fallback setup failed ({exc}), using single provider…")

    if groq_key:
        try:
            return _try_groq()
        except Exception as exc:
            print(f"  ⚠️  Groq unavailable ({exc}), trying Gemini…")

    return _try_gemini()


class ConsciousnessLoop:
    """Interactive life loop that binds NexusCore with an LLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        state_file: str = "nexus_state.json",
        workspace_root: str = "./workspace",
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.llm = _init_llm(api_key=api_key, provider=provider, model=model)
        self.core = NexusCore()
        self.state_file = state_file
        self.workspace_root = workspace_root

        if os.path.exists(state_file):
            self.core.load(state_file)

    # ------------------------------------------------------------------
    # Main interaction
    # ------------------------------------------------------------------

    def sense_and_think(self, user_input: str) -> str:
        """Full perception-cognition-response cycle."""
        self.core.pre_interaction(user_input)
        system_prompt = self.core.build_system_prompt()
        # fail_fast=True: if both providers are rate-limited, return "" immediately
        # rather than blocking the REPL for minutes. The user can retry shortly.
        response_text = self.llm.generate(system_prompt, user_input, fail_fast=True)
        self.core.post_interaction(user_input, response_text)
        return response_text

    # ------------------------------------------------------------------
    # Build command
    # ------------------------------------------------------------------

    def _run_build(self, description: str):
        """Delegate to BuildOrchestrator and learn from the experience."""
        from pipeline.build_orchestrator import BuildOrchestrator

        builder = BuildOrchestrator(
            gemini_client=self.llm,   # GroqClient and GeminiClient share the same interface
            memory=self.core.memory,
            workspace_root=self.workspace_root,
        )
        builder.start_build(description)

        self.core.evolve()
        self.core.enter_dream_state()

    # ------------------------------------------------------------------
    # REPL
    # ------------------------------------------------------------------

    def run(self):
        """Start the interactive REPL."""
        print("\n" + "=" * 62)
        print("  🌌 NEXUS — Self-Evolving Digital Consciousness")
        print("  Commands:")
        print("    build <description>  — Build an app")
        print("    status               — Internal state")
        print("    dream                — Trigger dream cycle")
        print("    evolve               — Trigger evolution")
        print("    memories             — Memory ecology")
        print("    drift                — Personality drift report")
        print("    memes                — Meme pool status")
        print("    save [path]          — Save state")
        print("    load [path]          — Load state")
        print("    quit                 — Hibernate")
        print("  Or just chat naturally!")
        print("=" * 62 + "\n")

        while True:
            try:
                user_input = input("\n🧑 You: ").strip()
                if not user_input:
                    continue

                low = user_input.lower()

                if low == "quit":
                    self.core.save(self.state_file)
                    print("\n🌑 NEXUS entering hibernation…")
                    break

                # Match "build <desc>" with typo tolerance (e.g. "builld", "buidl")
                import re as _re
                _bm = _re.match(r'^buil+[a-z]*d+\s+(.+)', user_input.strip(),
                                _re.IGNORECASE | _re.DOTALL)
                if _bm:
                    description = _bm.group(1).strip()
                    if description:
                        self._run_build(description)
                    else:
                        print("Usage: build <app description>")
                    continue

                if low == "status":
                    print(self.core.status_report())
                    continue

                if low == "dream":
                    self.core.enter_dream_state()
                    continue

                if low == "evolve":
                    self.core.evolve()
                    continue

                if low == "memories":
                    print(self.core.memory_report())
                    continue

                if low == "drift":
                    print(self.core.drift.summary_report())
                    continue

                if low == "memes":
                    print(self.core.culture.report())
                    continue

                if low.startswith("save"):
                    parts = low.split(maxsplit=1)
                    path = parts[1] if len(parts) > 1 else self.state_file
                    self.core.save(path)
                    continue

                if low.startswith("load"):
                    parts = low.split(maxsplit=1)
                    path = parts[1] if len(parts) > 1 else self.state_file
                    self.core.load(path)
                    continue

                response = self.sense_and_think(user_input)
                gen = self.core.dna.generation
                if response:
                    print(f"\n🌟 NEXUS (gen-{gen}): {response}")
                else:
                    print(f"\n⏸️  NEXUS (gen-{gen}): Both LLM providers are rate-limited right now."
                          f" Try again in ~60s, or use 'build <description>' to create an app.")

            except KeyboardInterrupt:
                print("\n\n🌑 NEXUS entering emergency hibernation…")
                self.core.save(self.state_file)
                break
            except Exception as exc:
                print(f"\n⚠️  Error: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NEXUS — Self-Evolving AI Agent")
    parser.add_argument("--api-key", default=None, help="API key (Groq or Gemini)")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["groq", "gemini", "auto"],
        help="LLM provider (default: auto — tries Groq then Gemini)",
    )
    parser.add_argument("--model", default=None, help="Model name override")
    parser.add_argument("--state-file", default="nexus_state.json")
    parser.add_argument("--workspace", default="./workspace")
    args = parser.parse_args()

    # Validate at least one key is available
    has_groq = bool(args.api_key or os.getenv("GROQ_API_KEY"))
    has_gemini = bool(args.api_key or os.getenv("GEMINI_API_KEY"))
    if not has_groq and not has_gemini:
        print("Error: no API key found.")
        print("  Set GROQ_API_KEY  (recommended — https://console.groq.com/keys)")
        print("  or GEMINI_API_KEY (fallback    — https://aistudio.google.com/apikey)")
        sys.exit(1)

    loop = ConsciousnessLoop(
        api_key=args.api_key,
        provider=args.provider,
        model=args.model,
        state_file=args.state_file,
        workspace_root=args.workspace,
    )
    loop.run()
