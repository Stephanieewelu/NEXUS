"""
mutation_engine.py — Controlled mutation of cognitive strategies.

Provides higher-level mutation operators beyond simple parameter perturbation,
including crossover between two genomes and directed (goal-driven) mutation.
"""

import random
import copy
from typing import List, Tuple, Optional

from genome.cognitive_dna import CognitiveDNA, Gene


class MutationEngine:
    """Applies genetic operators to CognitiveDNA instances."""

    def __init__(self, base_rate: float = 0.05, crossover_rate: float = 0.3):
        self.base_rate = base_rate
        self.crossover_rate = crossover_rate
        self._operation_log: List[dict] = []

    # ------------------------------------------------------------------
    # Point mutation
    # ------------------------------------------------------------------

    def point_mutate(self, dna: CognitiveDNA, strength: float = 1.0) -> CognitiveDNA:
        """
        Apply point mutations to a genome.

        strength > 1 amplifies the mutation rate; < 1 dampens it.
        Returns a deep-copy with mutations applied.
        """
        mutated = copy.deepcopy(dna)
        effective_rate = min(0.5, self.base_rate * strength)

        for chromosome, genes in mutated.chromosomes.items():
            for gene in genes:
                if random.random() < effective_rate:
                    old_name = gene.name
                    child = gene.mutate()
                    # Replace in-place
                    idx = genes.index(gene)
                    genes[idx] = child
                    self._log("point_mutate", old_name, child.name, chromosome)

        return mutated

    # ------------------------------------------------------------------
    # Crossover
    # ------------------------------------------------------------------

    def crossover(
        self, parent_a: CognitiveDNA, parent_b: CognitiveDNA
    ) -> Tuple[CognitiveDNA, CognitiveDNA]:
        """
        Uniform chromosome crossover between two genomes.

        Returns two child genomes by randomly swapping chromosomes.
        """
        child_a = copy.deepcopy(parent_a)
        child_b = copy.deepcopy(parent_b)

        for chrom in child_a.chromosomes:
            if chrom in child_b.chromosomes and random.random() < self.crossover_rate:
                # Swap entire chromosomes
                child_a.chromosomes[chrom], child_b.chromosomes[chrom] = (
                    child_b.chromosomes[chrom],
                    child_a.chromosomes[chrom],
                )
                self._log("crossover", chrom, chrom, "both")

        return child_a, child_b

    # ------------------------------------------------------------------
    # Directed mutation
    # ------------------------------------------------------------------

    def directed_mutate(
        self,
        dna: CognitiveDNA,
        target_chromosome: str,
        direction: str = "increase",
        trait: str = "dominance",
    ) -> CognitiveDNA:
        """
        Push a specific chromosome in a desired direction.

        direction: 'increase' | 'decrease'
        trait: 'dominance' | 'mutation_rate' | 'fitness_score'
        """
        mutated = copy.deepcopy(dna)
        genes = mutated.chromosomes.get(target_chromosome, [])
        delta = 0.05 if direction == "increase" else -0.05

        for gene in genes:
            if hasattr(gene, trait):
                current = getattr(gene, trait)
                setattr(gene, trait, max(0.0, min(1.0, current + delta)))
                self._log(
                    "directed_mutate",
                    gene.name,
                    f"{trait}→{direction}",
                    target_chromosome,
                )

        return mutated

    # ------------------------------------------------------------------
    # Gene insertion / deletion
    # ------------------------------------------------------------------

    def insert_gene(
        self, dna: CognitiveDNA, chromosome: str, gene: Gene
    ) -> CognitiveDNA:
        """Add a new gene to an existing chromosome."""
        mutated = copy.deepcopy(dna)
        if chromosome in mutated.chromosomes:
            mutated.chromosomes[chromosome].append(copy.deepcopy(gene))
            self._log("insert_gene", gene.name, chromosome, chromosome)
        return mutated

    def delete_weakest_gene(
        self, dna: CognitiveDNA, chromosome: str
    ) -> Optional[CognitiveDNA]:
        """Remove the gene with the lowest fitness from a chromosome."""
        if chromosome not in dna.chromosomes:
            return None
        if len(dna.chromosomes[chromosome]) <= 1:
            return None  # Never remove the last gene

        mutated = copy.deepcopy(dna)
        genes = mutated.chromosomes[chromosome]
        weakest = min(genes, key=lambda g: g.fitness_score)
        genes.remove(weakest)
        self._log("delete_weakest", weakest.name, chromosome, chromosome)
        return mutated

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _log(self, op: str, source: str, target: str, chromosome: str):
        self._operation_log.append(
            {"op": op, "source": source, "target": target, "chromosome": chromosome}
        )

    def get_log(self) -> List[dict]:
        return list(self._operation_log)
