# 🧬 NEXUS — Self-Evolving Digital Organism Agent

NEXUS is a self-evolving AI agent built on Claude that grows, mutates, and
evolves its own architecture, memory, and personality over time — like a
digital life form.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              NEXUS ARCHITECTURE                  │
│                                                  │
│  🧠 Cognitive Genome  ─── Evolvable prompts     │
│  🌳 Memory Ecology    ─── Living knowledge graph │
│  🎭 Persona Drift     ─── Personality evolution  │
│  🔀 Task Mitosis      ─── Self-splitting tasks   │
│  💀 Apoptosis Engine  ─── Self-pruning bad paths  │
│  🌐 Dream State       ─── Offline synthesis       │
│  🦠 Idea Contagion    ─── Meme-based learning     │
└─────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set your Anthropic API key
export ANTHROPIC_API_KEY=your-key-here

# Run NEXUS
cd src
python consciousness_loop.py
```

---

## REPL Commands

| Command | Description |
|---|---|
| `build <description>` | Build a full app from plain English |
| `status` | Show internal state (genome, mood, memory) |
| `dream` | Trigger a manual dream / memory consolidation cycle |
| `evolve` | Trigger a manual genome evolution step |
| `memories` | Show the living memory ecology |
| `drift` | Show personality & cognitive drift report |
| `memes` | Show active meme pool |
| `save [path]` | Persist state to disk |
| `load [path]` | Restore state from disk |
| `quit` | Hibernate and exit |

---

## Project Structure

```
nexus-agent/
├── src/
│   ├── genome/
│   │   ├── cognitive_dna.py        # Evolvable "genetic code"
│   │   ├── mutation_engine.py      # Controlled mutation of strategies
│   │   └── fitness_evaluator.py    # Natural selection for approaches
│   ├── memory/
│   │   ├── memory_ecology.py       # Living, decaying, growing memory
│   │   ├── dream_synthesizer.py    # Offline memory consolidation
│   │   └── memory_organisms.py     # Memories that compete & merge
│   ├── persona/
│   │   ├── personality_genome.py   # Evolving personality traits
│   │   ├── mood_dynamics.py        # Emotional state machine
│   │   └── drift_tracker.py        # Track personality evolution
│   ├── tasks/
│   │   ├── mitosis_engine.py       # Tasks that split into subtasks
│   │   ├── apoptosis.py            # Self-destruction of bad paths
│   │   └── task_ecosystem.py       # Tasks compete for resources
│   ├── contagion/
│   │   ├── idea_virus.py           # Ideas that spread & mutate
│   │   ├── meme_pool.py            # Shared idea marketplace
│   │   └── cultural_evolution.py   # Group learning dynamics
│   ├── builder/
│   ├── tools/
│   │   ├── file_system.py
│   │   ├── terminal.py
│   │   ├── git_manager.py
│   │   └── package_manager.py
│   ├── pipeline/
│   │   └── build_orchestrator.py   # 11-phase app builder
│   ├── nexus_core.py               # Central orchestrator
│   └── consciousness_loop.py       # Main life loop + REPL
├── configs/
│   ├── initial_genome.yaml
│   └── environment.yaml
├── logs/evolution_journal/
├── workspace/                      # Where built apps live
├── requirements.txt
└── README.md
```

---

## What Makes NEXUS Unique

| Feature | Traditional Agents | NEXUS |
|---|---|---|
| Memory | Static vector DB | **Living ecology** with birth, death, reproduction |
| Personality | Fixed prompt | **Evolving genome** that mutates over time |
| Learning | Fine-tuning / RAG | **Darwinian selection** of cognitive strategies |
| Offline processing | None | **Dream states** that synthesise new insights |
| Self-awareness | None | **Tracks its own evolution** and genome changes |
| Bad strategies | Accumulate | **Apoptosis** — self-prunes failed approaches |
| Ideas | Static | **Meme viruses** that compete for cognitive space |

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (required) |

---

## Licence

MIT
