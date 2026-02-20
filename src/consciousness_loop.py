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
"""

import os
import sys
from typing import Optional

import anthropic

from nexus_core import NexusCore


class ConsciousnessLoop:
    """Interactive life loop that binds NexusCore with the Claude API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        state_file: str = "nexus_state.json",
        workspace_root: str = "./workspace",
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.core = NexusCore()
        self.state_file = state_file
        self.workspace_root = workspace_root

        # Try to restore a previous session
        if os.path.exists(state_file):
            self.core.load(state_file)

    # ------------------------------------------------------------------
    # Main interaction
    # ------------------------------------------------------------------

    def sense_and_think(self, user_input: str) -> str:
        """Full perception-cognition-response cycle."""
        self.core.pre_interaction(user_input)
        system_prompt = self.core.build_system_prompt()

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_input}],
        )
        response_text = response.content[0].text
        self.core.post_interaction(user_input, response_text)
        return response_text

    # ------------------------------------------------------------------
    # Build command
    # ------------------------------------------------------------------

    def _run_build(self, description: str):
        """Delegate to BuildOrchestrator and learn from the experience."""
        from pipeline.build_orchestrator import BuildOrchestrator

        builder = BuildOrchestrator(
            memory=self.core.memory,
            workspace_root=self.workspace_root,
        )
        builder.start_build(description)

        # Evolve from building experience
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
                user_input = input(f"\n🧑 You: ").strip()
                if not user_input:
                    continue

                low = user_input.lower()

                # ---- Built-in commands --------------------------------

                if low == "quit":
                    self.core.save(self.state_file)
                    print("\n🌑 NEXUS entering hibernation…")
                    break

                if low.startswith("build "):
                    description = user_input[6:].strip()
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

                # ---- Normal conversation ------------------------------

                response = self.sense_and_think(user_input)
                gen = self.core.dna.generation
                print(f"\n🌟 NEXUS (gen-{gen}): {response}")

            except KeyboardInterrupt:
                print("\n\n🌑 NEXUS entering emergency hibernation…")
                self.core.save(self.state_file)
                break
            except anthropic.APIError as exc:
                print(f"\n⚠️  API error: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NEXUS — Self-Evolving AI Agent")
    parser.add_argument("--api-key", default=None, help="Anthropic API key")
    parser.add_argument(
        "--state-file",
        default="nexus_state.json",
        help="Path to persistence file",
    )
    parser.add_argument(
        "--workspace",
        default="./workspace",
        help="Root directory for app builds",
    )
    args = parser.parse_args()

    # Fall back to environment variable
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: no API key found. Set ANTHROPIC_API_KEY or pass --api-key.")
        sys.exit(1)

    loop = ConsciousnessLoop(
        api_key=api_key,
        state_file=args.state_file,
        workspace_root=args.workspace,
    )
    loop.run()
