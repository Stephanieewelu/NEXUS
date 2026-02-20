"""
dream_synthesizer.py — Offline memory consolidation ("dreaming").

During a dream cycle the agent replays recent memories, strengthens
associations, extracts patterns, generates novel combinations, and
prunes weak/isolated memories — mirroring mammalian sleep consolidation.
"""

import random
from typing import List, Dict, Optional

from memory.memory_ecology import MemoryEcology
from memory.memory_organisms import MemoryOrganism


class DreamSynthesizer:
    """
    Simulates 'dreaming': offline memory consolidation where the agent
    processes, connects, abstracts, and sometimes creates novel combinations.
    """

    def __init__(self, ecology: MemoryEcology):
        self.ecology = ecology
        self.dream_journal: List[dict] = []
        self.insights_generated: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dream(self, duration: int = 5) -> dict:
        """
        Run a full dream cycle.

        Steps per iteration:
        1. Random memory activation (biased toward emotional memories)
        2. Free association between activated memories
        3. Pattern extraction
        4. Novel combination (creative spark)
        5. Consolidation (prune weak, isolated memories)
        """
        dream_record: dict = {
            "cycle": len(self.dream_journal) + 1,
            "activated_memories": [],
            "associations_formed": [],
            "patterns_found": [],
            "novel_ideas": [],
            "memories_pruned": [],
        }

        all_memories = list(self.ecology.organisms.values())
        if len(all_memories) < 3:
            self.dream_journal.append(dream_record)
            return dream_record

        for _ in range(duration):
            activated = self._random_activation(all_memories, k=5)
            dream_record["activated_memories"].extend(m.id for m in activated)

            associations = self._free_associate(activated)
            dream_record["associations_formed"].extend(associations)

            patterns = self._extract_patterns(activated)
            dream_record["patterns_found"].extend(patterns)

            novel = self._novel_combination(activated)
            if novel:
                dream_record["novel_ideas"].append(novel)
                self.insights_generated.append(novel)

            pruned = self._consolidate(all_memories)
            dream_record["memories_pruned"].extend(pruned)

        self.dream_journal.append(dream_record)
        return dream_record

    def lucid_dream(self, focus_tags: List[str]) -> dict:
        """
        A directed dream focused on specific topics.
        Like lucid dreaming — conscious influence on dream content.
        """
        relevant = self.ecology.recall(query_tags=focus_tags, top_k=10)
        dream_record: dict = {
            "type": "lucid",
            "focus": focus_tags,
            "insights": [],
        }

        for _ in range(3):
            patterns = self._extract_patterns(relevant)
            novel = self._novel_combination(relevant)

            if patterns:
                dream_record["insights"].extend(patterns)
            if novel:
                dream_record["insights"].append(novel)

        self.dream_journal.append(dream_record)
        return dream_record

    # ------------------------------------------------------------------
    # Internal dream mechanics
    # ------------------------------------------------------------------

    def _random_activation(
        self, memories: List[MemoryOrganism], k: int = 5
    ) -> List[MemoryOrganism]:
        """Activate random memories, biased toward emotional & vital ones."""
        weights = [
            abs(m.emotional_charge) + 0.1 + (m.vitality * 0.5)
            for m in memories
        ]
        total = sum(weights)
        weights = [w / total for w in weights]
        k = min(k, len(memories))
        return random.choices(memories, weights=weights, k=k)

    def _free_associate(
        self, activated: List[MemoryOrganism]
    ) -> List[dict]:
        """Form loose associations between activated memories."""
        associations: List[dict] = []

        for i, mem1 in enumerate(activated):
            for mem2 in activated[i + 1 :]:
                # Tag-based association
                shared = set(mem1.tags) & set(mem2.tags)
                if shared:
                    associations.append({
                        "from": mem1.id,
                        "to": mem2.id,
                        "bridge": list(shared),
                        "type": "tag_association",
                    })
                    # Strengthen link in ecology
                    if mem2.id not in mem1.connections:
                        mem1.connections.append(mem2.id)
                        mem2.connections.append(mem1.id)

                # Emotional resonance
                if abs(mem1.emotional_charge - mem2.emotional_charge) < 0.2:
                    associations.append({
                        "from": mem1.id,
                        "to": mem2.id,
                        "type": "emotional_resonance",
                        "charge": (mem1.emotional_charge + mem2.emotional_charge) / 2,
                    })

        return associations

    def _extract_patterns(
        self, activated: List[MemoryOrganism]
    ) -> List[str]:
        """Extract recurring themes and emotional clusters."""
        patterns: List[str] = []

        # Tag frequency analysis
        tag_freq: Dict[str, int] = {}
        for mem in activated:
            for tag in mem.tags:
                tag_freq[tag] = tag_freq.get(tag, 0) + 1

        recurring = {t: c for t, c in tag_freq.items() if c > 1}
        if recurring:
            patterns.append(f"Recurring themes: {recurring}")

        # Emotional cluster
        emotions = [m.emotional_charge for m in activated]
        avg_emotion = sum(emotions) / max(len(emotions), 1)
        if abs(avg_emotion) > 0.3:
            valence = "positive" if avg_emotion > 0 else "negative"
            patterns.append(
                f"Emotional cluster detected: {valence} "
                f"(avg charge: {avg_emotion:.2f})"
            )

        return patterns

    def _novel_combination(
        self, activated: List[MemoryOrganism]
    ) -> Optional[str]:
        """
        Create a novel idea by bridging two minimally-connected memories.
        40% chance of a creative spark per invocation.
        """
        if len(activated) < 2:
            return None

        # Find the pair with the least direct tag overlap (most "surprising")
        best_pair: Optional[tuple] = None
        min_connection = float("inf")

        for i, m1 in enumerate(activated):
            for m2 in activated[i + 1 :]:
                shared = len(set(m1.tags) & set(m2.tags))
                if shared < min_connection:
                    min_connection = shared
                    best_pair = (m1, m2)

        if best_pair and random.random() < 0.4:
            m1, m2 = best_pair
            idea = (
                f"[DREAM INSIGHT] What if '{m1.content[:30]}' "
                f"connects to '{m2.content[:30]}'? "
                f"Bridge: {list(set(m1.tags) | set(m2.tags))[:5]}"
            )

            # Materialise the insight as a new memory
            self.ecology.birth(
                content=idea,
                memory_type="semantic",
                tags=list(set(m1.tags + m2.tags)),
                emotional_charge=0.3,  # Insights feel rewarding
                context={"source": "dream", "parents": [m1.id, m2.id]},
            )

            return idea

        return None

    def _consolidate(self, all_memories: List[MemoryOrganism]) -> List[str]:
        """
        Prune weak, isolated, emotionally neutral memories during dreaming
        (30% chance per qualifying memory).
        """
        pruned: List[str] = []

        for mem in all_memories:
            if (
                mem.vitality < 0.15
                and len(mem.connections) < 2
                and abs(mem.emotional_charge) < 0.1
            ):
                if random.random() < 0.3:
                    pruned.append(mem.id)
                    self.ecology.organisms.pop(mem.id, None)

        return pruned
