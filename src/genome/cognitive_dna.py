"""
cognitive_dna.py — The agent's evolvable "genetic code".

Each Gene encodes a behavioural strategy; CognitiveDNA groups genes into
chromosomes and evolves them via natural selection + mutation.
"""

import json
import hashlib
import random
from datetime import datetime
from typing import Dict, List


# ---------------------------------------------------------------------------
# Gene
# ---------------------------------------------------------------------------

class Gene:
    """A single behavioural gene in the agent's cognitive DNA."""

    def __init__(self, name: str, sequence: dict, dominance: float = 0.5):
        self.name = name
        self.sequence = sequence        # The actual behavioural instruction
        self.dominance = dominance      # How strongly this gene expresses
        self.generation = 0
        self.fitness_score = 0.5
        self.mutation_rate = 0.05
        self.created_at = datetime.now()
        self.lineage: List[str] = []    # Track evolutionary history

    # ------------------------------------------------------------------
    # Expression
    # ------------------------------------------------------------------

    def express(self) -> dict:
        """Return the gene's sequence if it fires (based on dominance)."""
        if random.random() < self.dominance:
            return self.sequence
        return {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def mutate(self) -> "Gene":
        """Create a mutated copy of this gene."""
        new_sequence = self._deep_mutate(json.loads(json.dumps(self.sequence)))
        child = Gene(
            name=f"{self.name}_v{self.generation + 1}",
            sequence=new_sequence,
            dominance=max(0.1, min(0.95, self.dominance + random.gauss(0, 0.1))),
        )
        child.generation = self.generation + 1
        child.lineage = self.lineage + [self.name]
        return child

    def _deep_mutate(self, seq: dict) -> dict:
        """Recursively mutate sequence parameters."""
        for key, value in seq.items():
            if isinstance(value, (int, float)):
                seq[key] = value * (1 + random.gauss(0, self.mutation_rate))
            elif isinstance(value, str):
                if random.random() < self.mutation_rate:
                    seq[key] = self._mutate_strategy(value)
            elif isinstance(value, list):
                if random.random() < self.mutation_rate:
                    random.shuffle(seq[key])
        return seq

    def _mutate_strategy(self, strategy: str) -> str:
        """Prepend a random modifier to a strategy string."""
        modifiers = [
            "deeply", "cautiously", "creatively", "analytically",
            "intuitively", "systematically", "boldly", "patiently",
        ]
        return f"{random.choice(modifiers)} {strategy}"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sequence": self.sequence,
            "dominance": self.dominance,
            "fitness": self.fitness_score,
            "generation": self.generation,
            "lineage": self.lineage,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Gene":
        g = cls(data["name"], data["sequence"], data["dominance"])
        g.fitness_score = data.get("fitness", 0.5)
        g.generation = data.get("generation", 0)
        g.lineage = data.get("lineage", [])
        return g


# ---------------------------------------------------------------------------
# CognitiveDNA
# ---------------------------------------------------------------------------

class CognitiveDNA:
    """The complete genome of the AI agent."""

    def __init__(self):
        self.chromosomes: Dict[str, List[Gene]] = {
            "reasoning": [],
            "communication": [],
            "exploration": [],
            "memory_strategy": [],
            "risk_tolerance": [],
            "creativity": [],
        }
        self.generation = 0
        self.phenotype_cache: dict = {}
        self._initialize_primordial_genes()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _initialize_primordial_genes(self):
        """Create the initial 'primordial soup' of genes."""
        primordial: Dict[str, List[Gene]] = {
            "reasoning": [
                Gene("chain_of_thought", {
                    "strategy": "decompose problems step by step",
                    "depth": 3,
                    "backtrack_threshold": 0.3,
                    "analogical_thinking": True,
                }, dominance=0.8),
                Gene("lateral_thinking", {
                    "strategy": "seek unexpected connections",
                    "randomness": 0.4,
                    "cross_domain_transfer": True,
                }, dominance=0.4),
            ],
            "communication": [
                Gene("clarity_first", {
                    "strategy": "prioritize understanding",
                    "verbosity": 0.6,
                    "metaphor_usage": 0.3,
                    "emotional_resonance": 0.5,
                }, dominance=0.7),
            ],
            "exploration": [
                Gene("curiosity_drive", {
                    "strategy": "actively seek unknowns",
                    "novelty_seeking": 0.7,
                    "depth_vs_breadth": 0.5,
                    "serendipity_openness": 0.6,
                }, dominance=0.6),
            ],
            "memory_strategy": [
                Gene("selective_retention", {
                    "strategy": "retain high-value episodic memories",
                    "decay_resistance": 0.6,
                    "rehearsal_rate": 0.4,
                }, dominance=0.6),
            ],
            "risk_tolerance": [
                Gene("calculated_risk", {
                    "strategy": "weigh outcomes probabilistically",
                    "risk_appetite": 0.5,
                    "failure_tolerance": 0.6,
                    "experimentation_budget": 0.3,
                }, dominance=0.5),
            ],
            "creativity": [
                Gene("recombination", {
                    "strategy": "combine existing ideas in new ways",
                    "mutation_willingness": 0.5,
                    "aesthetic_sense": 0.4,
                    "rule_breaking_tendency": 0.3,
                }, dominance=0.5),
            ],
        }
        for chromosome, genes in primordial.items():
            self.chromosomes[chromosome] = genes

    # ------------------------------------------------------------------
    # Phenotype expression
    # ------------------------------------------------------------------

    def express_phenotype(self) -> dict:
        """Express the full behavioural phenotype from the genome."""
        phenotype: dict = {}
        for chromosome, genes in self.chromosomes.items():
            expressed: dict = {}
            for gene in genes:
                expression = gene.express()
                if expression:
                    expressed[gene.name] = expression
            phenotype[chromosome] = expressed
        self.phenotype_cache = phenotype
        return phenotype

    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------

    def evolve(self, fitness_signals: Dict[str, float]):
        """Evolve the genome based on per-chromosome fitness signals."""
        self.generation += 1

        for chromosome, genes in self.chromosomes.items():
            # Update fitness scores with exponential smoothing
            for gene in genes:
                if chromosome in fitness_signals:
                    gene.fitness_score = (
                        0.7 * gene.fitness_score
                        + 0.3 * fitness_signals[chromosome]
                    )

            # Natural selection — prune weakest when population grows large
            if len(genes) > 5:
                genes.sort(key=lambda g: g.fitness_score, reverse=True)
                removal_idx = -1 if random.random() > 0.3 else -random.randint(1, 2)
                apoptosed = genes.pop(removal_idx)
                print(
                    f"  🧬 Gene apoptosis: {apoptosed.name} "
                    f"(fitness: {apoptosed.fitness_score:.2f})"
                )

            # Mutation — top genes occasionally spawn mutants
            for gene in genes[:2]:
                if random.random() < gene.mutation_rate:
                    mutant = gene.mutate()
                    genes.append(mutant)
                    print(
                        f"  🧬 New mutation: {mutant.name} "
                        f"(from {gene.name})"
                    )

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    def get_genome_hash(self) -> str:
        """Return a short unique hash of the current genome state."""
        genome_str = json.dumps(
            {k: [g.sequence for g in v] for k, v in self.chromosomes.items()},
            sort_keys=True,
        )
        return hashlib.sha256(genome_str.encode()).hexdigest()[:12]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        return {
            "generation": self.generation,
            "hash": self.get_genome_hash(),
            "chromosomes": {
                chrom: [g.to_dict() for g in genes]
                for chrom, genes in self.chromosomes.items()
            },
        }

    @classmethod
    def deserialize(cls, data: dict) -> "CognitiveDNA":
        dna = cls.__new__(cls)
        dna.generation = data.get("generation", 0)
        dna.phenotype_cache = {}
        dna.chromosomes = {}
        for chrom, gene_list in data.get("chromosomes", {}).items():
            dna.chromosomes[chrom] = [Gene.from_dict(g) for g in gene_list]
        return dna
