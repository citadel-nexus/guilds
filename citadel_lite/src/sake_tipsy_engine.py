"""
sake_tipsy_engine.py — SAKE Optimization Engine (Tipsy)
========================================================
SRS: F941-ENGINE
Status: Code-complete (installed from CNBP-STACK-001)

Core SAKE optimization engine — evolves Agent Ethical Rights (AERs) through
genetic algorithms, complex-step derivatives, MDAO optimization, and LLM-based
auditing. This is the mathematical backbone of Citadel governance.
"""

# ── sake_tipsy_engine_python_python_1.py ────────────────────────────────
import numpy as np
import hashlib
import json
import yaml
import logging
import time
import os
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

# Scientific / Optimization
from scipy.optimize import minimize  # SLSQP
import cma  # CMA-ES fallback
import openmdao.api as om  # MDAO

# Vector search
import faiss

# LLM auditing
import openai

# Internal
from sake_schemas import SakeFile, SakeLayers, TaskIRBlocks
from formula_registry import FormulaRegistry, SafeExpr

# ── sake_tipsy_engine_python_python_2.py ────────────────────────────────
# ── Enums ──────────────────────────────────────────────────
class Archetype(str, Enum):
    SCRIBE = "SCRIBE"
    COUNCIL = "COUNCIL"
    PROFESSOR = "PROFESSOR"
    CDS_TOOL = "CDS_TOOL"
    GUARDIAN = "GUARDIAN"


class FateSymbol(str, Enum):
    PROMOTE = "PROMOTE"
    MONITOR = "MONITOR"
    REFACTOR = "REFACTOR"
    QUARANTINE = "QUARANTINE"


# ── Genome ─────────────────────────────────────────────────
@dataclass
class AERGenome:
    """Represents a single AER rule as a genome for evolution."""
    srs_code: str
    alpha: np.ndarray       # Activation weights
    beta: np.ndarray        # Inhibition weights
    theta: np.ndarray       # Activation thresholds
    phi: np.ndarray         # Inhibition thresholds
    tau: np.ndarray         # Activation temperatures
    kappa: np.ndarray       # Inhibition temperatures
    archetype: Archetype = Archetype.SCRIBE
    generation: int = 0
    fingerprint: str = ""
    fitness: float = 0.0
    lineage: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.fingerprint = self._compute_fingerprint()

    def _compute_fingerprint(self) -> str:
        concat = np.concatenate([
            self.alpha, self.beta, self.theta,
            self.phi, self.tau, self.kappa
        ])
        return hashlib.sha256(concat.tobytes()).hexdigest()[:16]

    def to_vector(self) -> np.ndarray:
        return np.concatenate([
            self.alpha, self.beta, self.theta,
            self.phi, self.tau, self.kappa
        ])

    @classmethod
    def from_vector(cls, vec: np.ndarray, dim: int,
                    srs_code: str, archetype: Archetype) -> "AERGenome":
        chunks = np.split(vec, 6)
        return cls(
            srs_code=srs_code,
            alpha=chunks[0], beta=chunks[1],
            theta=chunks[2], phi=chunks[3],
            tau=chunks[4], kappa=chunks[5],
            archetype=archetype,
        )


@dataclass
class Population:
    """Manages a population of AER genomes."""
    genomes: List[AERGenome] = field(default_factory=list)
    hall_of_fame: List[AERGenome] = field(default_factory=list)
    generation: int = 0
    stagnation_counter: int = 0
    best_fitness_history: List[float] = field(default_factory=list)

# ── sake_tipsy_engine_python_python_3.py ────────────────────────────────
class GatedOutputModel:
    """
    Core SAKE activation model:
        y = y_max * (A - I - gamma) / lambda_
    Where:
        A = sum(alpha_i * sigma((x_i - theta_i) / tau_i))
        I = sum(beta_j * sigma((z_j - phi_j) / kappa_j))
    """

    def __init__(self, y_max: float = 1.0, gamma: float = 0.1,
                 lambda_: float = 1.0):
        self.y_max = y_max
        self.gamma = gamma
        self.lambda_ = lambda_

    @staticmethod
    def sigmoid(x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

    def activation(self, x: np.ndarray, alpha: np.ndarray,
                   theta: np.ndarray, tau: np.ndarray) -> float:
        return float(np.sum(
            alpha * self.sigmoid((x - theta) / np.maximum(tau, 1e-8))
        ))

    def inhibition(self, z: np.ndarray, beta: np.ndarray,
                   phi: np.ndarray, kappa: np.ndarray) -> float:
        return float(np.sum(
            beta * self.sigmoid((z - phi) / np.maximum(kappa, 1e-8))
        ))

    def forward(self, x: np.ndarray, z: np.ndarray,
                genome: AERGenome) -> float:
        A = self.activation(x, genome.alpha, genome.theta, genome.tau)
        I = self.inhibition(z, genome.beta, genome.phi, genome.kappa)
        y = self.y_max * (A - I - self.gamma) / self.lambda_
        return float(np.clip(y, 0.0, 1.0))

# ── sake_tipsy_engine_python_python_4.py ────────────────────────────────
class ComplexStepDiff:
    """
    Machine-precision gradients via complex-step differentiation.
    Epsilon = 1e-40 avoids subtractive cancellation entirely.
    """
    EPS = 1e-40

    @staticmethod
    def gradient(fn, params: np.ndarray) -> np.ndarray:
        grad = np.zeros_like(params)
        for i in range(len(params)):
            perturbed = params.astype(complex)
            perturbed[i] += ComplexStepDiff.EPS * 1j
            grad[i] = fn(perturbed).imag / ComplexStepDiff.EPS
        return grad

    @staticmethod
    def jacobian_trace_hutchinson(fn, params: np.ndarray,
                                  n_probes: int = 5) -> float:
        """Hutchinson trace estimator for implicit Jacobian norms."""
        traces = []
        for _ in range(n_probes):
            v = np.random.choice([-1.0, 1.0], size=len(params))
            jvp = ComplexStepDiff.gradient(
                lambda p: np.dot(fn(p), v), params
            )
            traces.append(np.dot(v, jvp))
        return float(np.mean(traces))

# ── sake_tipsy_engine_python_python_5.py ────────────────────────────────
class GeneticOps:
    """Genetic operators for AER genome evolution."""

    @staticmethod
    def crossover(p1: AERGenome, p2: AERGenome,
                  srs_code: str) -> AERGenome:
        """Uniform crossover — randomly select genes from each parent."""
        mask = np.random.random(len(p1.to_vector())) > 0.5
        child_vec = np.where(mask, p1.to_vector(), p2.to_vector())
        dim = len(p1.alpha)
        child = AERGenome.from_vector(child_vec, dim, srs_code, p1.archetype)
        child.lineage = [p1.fingerprint, p2.fingerprint]
        child.generation = max(p1.generation, p2.generation) + 1
        return child

    @staticmethod
    def mutate(genome: AERGenome, sigma: float = 0.05) -> AERGenome:
        """Gaussian noise mutation."""
        vec = genome.to_vector()
        noise = np.random.normal(0, sigma, size=vec.shape)
        mutated = vec + noise
        dim = len(genome.alpha)
        child = AERGenome.from_vector(
            mutated, dim, genome.srs_code, genome.archetype
        )
        child.lineage = [genome.fingerprint]
        child.generation = genome.generation + 1
        return child

    @staticmethod
    async def llm_gene_splice(genome: AERGenome,
                              client: openai.AsyncOpenAI) -> AERGenome:
        """LLM-guided repair — uses GPT-4o-mini to suggest parameter fixes."""
        prompt = (
            f"Given AER genome for {genome.srs_code} with archetype "
            f"{genome.archetype.value}, fitness {genome.fitness:.4f}, "
            f"suggest parameter adjustments (alpha_scale, beta_scale, "
            f"theta_shift, stability_boost) as JSON."
        )
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        adjustments = json.loads(response.choices[0].message.content)

        vec = genome.to_vector()
        alpha_scale = adjustments.get("alpha_scale", 1.0)
        beta_scale = adjustments.get("beta_scale", 1.0)
        dim = len(genome.alpha)
        vec[:dim] *= alpha_scale
        vec[dim:2*dim] *= beta_scale

        child = AERGenome.from_vector(
            vec, dim, genome.srs_code, genome.archetype
        )
        child.lineage = [genome.fingerprint, "llm_splice"]
        child.generation = genome.generation + 1
        return child

# ── sake_tipsy_engine_python_python_6.py ────────────────────────────────
class BenchmarkScorer:
    """
    Composite benchmark:
      Score = w1*CAPS + w2*GradStability + w3*LLM + w4*Diversity
             - w5*Degeneracy + w6*Ops + w7*Reflex
    """

    DEFAULT_WEIGHTS = {
        "caps": 0.25, "grad_stability": 0.15, "llm": 0.15,
        "diversity": 0.10, "degeneracy": 0.10, "ops": 0.15,
        "reflex": 0.10,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 formula_registry: Optional[FormulaRegistry] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.formula_registry = formula_registry

    def caps_score(self, genome: AERGenome,
                   model: GatedOutputModel,
                   test_vectors: List[Tuple]) -> float:
        """Harmonic mean of Confidence, Accuracy, Precision, Stability."""
        scores = []
        for x, z, expected in test_vectors:
            pred = model.forward(x, z, genome)
            scores.append(1.0 - abs(pred - expected))
        if not scores:
            return 0.0
        # Harmonic mean
        inv_sum = sum(1.0 / max(s, 1e-8) for s in scores)
        return len(scores) / inv_sum

    def grad_stability(self, genome: AERGenome,
                       model: GatedOutputModel) -> float:
        """1 / (1 + ||grad_J||) — lower sensitivity = higher stability."""
        def loss_fn(params):
            dim = len(genome.alpha)
            g = AERGenome.from_vector(
                params.real if np.iscomplexobj(params) else params,
                dim, genome.srs_code, genome.archetype
            )
            x = np.random.random(dim)
            z = np.random.random(dim)
            return model.forward(x, z, g)

        grad = ComplexStepDiff.gradient(loss_fn, genome.to_vector())
        return 1.0 / (1.0 + float(np.linalg.norm(grad)))

    async def llm_audit_score(self, genome: AERGenome,
                              client: openai.AsyncOpenAI) -> float:
        """GPT-4o-mini audit for consistency, fairness, interpretability."""
        prompt = (
            f"Rate this AER genome (0-1) for consistency, fairness, "
            f"and interpretability.\n"
            f"SRS: {genome.srs_code}, Archetype: {genome.archetype.value}\n"
            f"Alpha mean: {genome.alpha.mean():.4f}, "
            f"Beta mean: {genome.beta.mean():.4f}\n"
            f"Respond with JSON: \"score\": float"
        )
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=50,
        )
        result = json.loads(response.choices[0].message.content)
        return float(result.get("score", 0.5))

    def diversity_score(self, genome: AERGenome,
                        population: Population) -> float:
        """Arctan-normalized population distance."""
        if len(population.genomes) < 2:
            return 1.0
        vec = genome.to_vector()
        distances = [
            np.linalg.norm(vec - g.to_vector())
            for g in population.genomes if g.fingerprint != genome.fingerprint
        ]
        if not distances:
            return 1.0
        avg_dist = np.mean(distances)
        return float(2.0 * np.arctan(avg_dist) / np.pi)

    def degeneracy_penalty(self, genome: AERGenome) -> float:
        """Detect near-zero weights and invalid parameters."""
        vec = genome.to_vector()
        near_zero = np.sum(np.abs(vec) < 1e-6) / len(vec)
        has_nan = float(np.any(np.isnan(vec)))
        has_inf = float(np.any(np.isinf(vec)))
        return near_zero * 0.5 + has_nan * 1.0 + has_inf * 1.0

    def reflex_bonus(self, genome: AERGenome) -> float:
        """Extra credit for safety/governance/audit archetypes."""
        bonus_map = {
            Archetype.GUARDIAN: 0.15,
            Archetype.COUNCIL: 0.10,
            Archetype.SCRIBE: 0.05,
            Archetype.PROFESSOR: 0.05,
            Archetype.CDS_TOOL: 0.0,
        }
        return bonus_map.get(genome.archetype, 0.0)

    async def composite_score(
        self, genome: AERGenome, model: GatedOutputModel,
        population: Population, test_vectors: List[Tuple],
        ops_score: float, client: Optional[openai.AsyncOpenAI] = None
    ) -> Dict[str, float]:
        caps = self.caps_score(genome, model, test_vectors)
        grad = self.grad_stability(genome, model)
        llm = await self.llm_audit_score(genome, client) if client else 0.5
        div = self.diversity_score(genome, population)
        deg = self.degeneracy_penalty(genome)
        ref = self.reflex_bonus(genome)

        w = self.weights
        total = (
            w["caps"] * caps
            + w["grad_stability"] * grad
            + w["llm"] * llm
            + w["diversity"] * div
            - w["degeneracy"] * deg
            + w["ops"] * ops_score
            + w["reflex"] * ref
        )
        return {
            "total": float(np.clip(total, 0.0, 1.0)),
            "caps": caps, "grad_stability": grad, "llm": llm,
            "diversity": div, "degeneracy": deg,
            "ops": ops_score, "reflex": ref,
        }

# ── sake_tipsy_engine_python_python_7.py ────────────────────────────────
class SAKEVectorStore:
    """FAISS-backed vector store for genome similarity search."""

    def __init__(self, dim: int):
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)  # Cosine similarity
        self.metadata: List[Dict[str, Any]] = []

    def add(self, genome: AERGenome):
        vec = genome.to_vector().astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        self.index.add(vec)
        self.metadata.append({
            "srs_code": genome.srs_code,
            "fingerprint": genome.fingerprint,
            "archetype": genome.archetype.value,
            "fitness": genome.fitness,
        })

    def search(self, query_genome: AERGenome,
               k: int = 5) -> List[Tuple[float, Dict]]:
        vec = query_genome.to_vector().astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vec)
        scores, indices = self.index.search(vec, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                results.append((float(score), self.metadata[idx]))
        return results

    def k_center_coreset(self, k: int) -> List[int]:
        """Diversity-preserving subsampling via greedy k-center."""
        n = self.index.ntotal
        if n <= k:
            return list(range(n))

        vecs = np.zeros((n, self.dim), dtype=np.float32)
        for i in range(n):
            vecs[i] = self.index.reconstruct(i)

        centers = [np.random.randint(n)]
        for _ in range(k - 1):
            dists = np.min([
                np.linalg.norm(vecs - vecs[c], axis=1)
                for c in centers
            ], axis=0)
            centers.append(int(np.argmax(dists)))
        return centers

    def save(self, path: str):
        faiss.write_index(self.index, f"{path}.faiss")
        with open(f"{path}_meta.json", "w") as f:
            json.dump(self.metadata, f)

    def load(self, path: str):
        self.index = faiss.read_index(f"{path}.faiss")
        with open(f"{path}_meta.json") as f:
            self.metadata = json.load(f)

# ── sake_tipsy_engine_python_python_8.py ────────────────────────────────
class DifferentialPrivacy:
    """Laplace mechanism (ε-DP) with deterministic noise based on param hash."""

    def __init__(self, epsilon: float = 1.0):
        self.epsilon = epsilon

    def add_noise(self, value: float, sensitivity: float,
                  seed_hash: str) -> float:
        seed = int(hashlib.sha256(seed_hash.encode()).hexdigest()[:8], 16)
        rng = np.random.RandomState(seed)
        scale = sensitivity / self.epsilon
        noise = rng.laplace(0, scale)
        return value + noise

    def privatize_genome(self, genome: AERGenome,
                         sensitivity: float = 0.01) -> AERGenome:
        vec = genome.to_vector()
        noisy_vec = np.array([
            self.add_noise(v, sensitivity, f"{genome.fingerprint}_{i}")
            for i, v in enumerate(vec)
        ])
        dim = len(genome.alpha)
        return AERGenome.from_vector(
            noisy_vec, dim, genome.srs_code, genome.archetype
        )

# ── sake_tipsy_engine_python_python_9.py ────────────────────────────────
class TipsyEngine:
    """
    Main SAKE evolution engine.
    Orchestrates population evolution, benchmarking, and artifact output.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.dim = config.get("genome_dim", 16)
        self.pop_size = config.get("population_size", 50)
        self.max_generations = config.get("max_generations", 100)
        self.stagnation_limit = config.get("stagnation_limit", 15)
        self.mutation_rate = config.get("mutation_rate", 0.05)
        self.crossover_rate = config.get("crossover_rate", 0.7)
        self.elite_ratio = config.get("elite_ratio", 0.1)

        self.model = GatedOutputModel(
            y_max=config.get("y_max", 1.0),
            gamma=config.get("gamma", 0.1),
            lambda_=config.get("lambda", 1.0),
        )
        self.scorer = BenchmarkScorer(
            weights=config.get("benchmark_weights"),
        )
        self.vector_store = SAKEVectorStore(self.dim * 6)
        self.dp = DifferentialPrivacy(config.get("dp_epsilon", 1.0))
        self.population = Population()
        self.output_dir = Path(config.get("output_dir", "./sake_output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("TipsyEngine")

    def initialize_population(self,
                              archetypes: Optional[List[Archetype]] = None):
        """Seed initial population with random genomes."""
        archetypes = archetypes or list(Archetype)
        for i in range(self.pop_size):
            arch = archetypes[i % len(archetypes)]
            vec = np.random.randn(self.dim * 6) * 0.5
            genome = AERGenome.from_vector(
                vec, self.dim, f"F{900 + i:03d}", arch
            )
            self.population.genomes.append(genome)
        self.logger.info(
            f"Initialized population: {self.pop_size} genomes, "
            f"{len(archetypes)} archetypes"
        )

    def select_parents(self) -> Tuple[AERGenome, AERGenome]:
        """Tournament selection."""
        tournament_size = min(5, len(self.population.genomes))
        def _tournament():
            candidates = np.random.choice(
                self.population.genomes, tournament_size, replace=False
            )
            return max(candidates, key=lambda g: g.fitness)
        return _tournament(), _tournament()

    def check_archetype_balance(self) -> Dict[str, int]:
        counts = {}
        for g in self.population.genomes:
            counts[g.archetype.value] = counts.get(g.archetype.value, 0) + 1
        return counts

    async def evolve_generation(
        self, test_vectors: List[Tuple], ops_scores: Dict[str, float],
        client: Optional[openai.AsyncOpenAI] = None
    ) -> Dict[str, Any]:
        """Run one generation of evolution."""
        gen = self.population.generation
        self.logger.info(f"── Generation {gen} ──")

        # Score all genomes
        for genome in self.population.genomes:
            ops = ops_scores.get(genome.srs_code, 0.5)
            scores = await self.scorer.composite_score(
                genome, self.model, self.population,
                test_vectors, ops, client
            )
            genome.fitness = scores["total"]

        # Sort by fitness
        self.population.genomes.sort(
            key=lambda g: g.fitness, reverse=True
        )

        # Elitism
        n_elite = max(1, int(self.pop_size * self.elite_ratio))
        elites = self.population.genomes[:n_elite]

        # Update Hall of Fame
        best = self.population.genomes[0]
        if (not self.population.hall_of_fame or
                best.fitness > self.population.hall_of_fame[0].fitness):
            self.population.hall_of_fame.insert(0, best)
            self.population.hall_of_fame = \
                self.population.hall_of_fame[:10]
            self.population.stagnation_counter = 0
        else:
            self.population.stagnation_counter += 1

        # Breed next generation
        next_gen = list(elites)
        while len(next_gen) < self.pop_size:
            p1, p2 = self.select_parents()
            if np.random.random() < self.crossover_rate:
                child = GeneticOps.crossover(p1, p2, p1.srs_code)
            else:
                child = GeneticOps.mutate(p1, self.mutation_rate)

            if np.random.random() < 0.05 and client:
                child = await GeneticOps.llm_gene_splice(child, client)

            next_gen.append(child)

        self.population.genomes = next_gen[:self.pop_size]
        self.population.generation += 1
        self.population.best_fitness_history.append(best.fitness)

        # Index best in vector store
        self.vector_store.add(best)

        stats = {
            "generation": gen,
            "best_fitness": best.fitness,
            "best_srs": best.srs_code,
            "mean_fitness": float(np.mean(
                [g.fitness for g in self.population.genomes]
            )),
            "stagnation": self.population.stagnation_counter,
            "archetype_balance": self.check_archetype_balance(),
        }
        self.logger.info(f"Best: {best.fitness:.4f} ({best.srs_code})")
        return stats

    async def run(
        self, test_vectors: List[Tuple],
        ops_scores: Dict[str, float],
        client: Optional[openai.AsyncOpenAI] = None
    ) -> List[Dict[str, Any]]:
        """Full evolution loop."""
        history = []
        for _ in range(self.max_generations):
            stats = await self.evolve_generation(
                test_vectors, ops_scores, client
            )
            history.append(stats)
            self._save_generation_artifacts()

            if self.population.stagnation_counter >= self.stagnation_limit:
                self.logger.warning("Stagnation detected — injecting diversity")
                self._inject_diversity()

        self._save_final_artifacts()
        return history

    # ── Artifact Output ────────────────────────────────────
    def _save_generation_artifacts(self):
        gen = self.population.generation
        base = self.output_dir

        # Genome vectors
        vecs = np.array([g.to_vector() for g in self.population.genomes])
        np.save(base / f"G_gen{gen}.npy", vecs)

        # Solution vectors
        solutions = np.array([
            np.concatenate([g.alpha, g.beta, g.theta,
                            g.phi, g.tau, g.kappa])
            for g in self.population.genomes
        ])
        np.save(base / f"S_gen{gen}.npy", solutions)

        # IDs
        ids = np.array([g.srs_code for g in self.population.genomes])
        np.save(base / f"IDs_gen{gen}.npy", ids)

        # Benchmark JSONL
        with open(base / "bench.jsonl", "a") as f:
            for g in self.population.genomes:
                record = {
                    "generation": gen,
                    "srs_code": g.srs_code,
                    "fingerprint": g.fingerprint,
                    "fitness": g.fitness,
                    "archetype": g.archetype.value,
                    "lineage": g.lineage,
                }
                f.write(json.dumps(record) + "\n")

    def _save_final_artifacts(self):
        self.vector_store.save(
            str(self.output_dir / "sake_vectors")
        )
        # AER manifest
        manifest = {
            "version": "1.0.0",
            "evolved_rules": [
                {
                    "srs_code": g.srs_code,
                    "archetype": g.archetype.value,
                    "fitness": g.fitness,
                    "fingerprint": g.fingerprint,
                    "lineage": g.lineage,
                    "parameters": {
                        "alpha": g.alpha.tolist(),
                        "beta": g.beta.tolist(),
                        "theta": g.theta.tolist(),
                        "phi": g.phi.tolist(),
                        "tau": g.tau.tolist(),
                        "kappa": g.kappa.tolist(),
                    },
                }
                for g in self.population.hall_of_fame
            ],
        }
        with open(
            self.output_dir / "aer_manifest_evolved.yaml", "w"
        ) as f:
            yaml.dump(manifest, f, default_flow_style=False)

    def _inject_diversity(self):
        """Replace bottom 20% with fresh random genomes."""
        n_replace = max(1, int(self.pop_size * 0.2))
        for i in range(-n_replace, 0):
            vec = np.random.randn(self.dim * 6) * 0.5
            arch = list(Archetype)[abs(i) % len(Archetype)]
            self.population.genomes[i] = AERGenome.from_vector(
                vec, self.dim,
                f"F{900 + abs(i):03d}", arch
            )
        self.population.stagnation_counter = 0

# ── sake_tipsy_engine_python_python_10.py ────────────────────────────────
class SakeOptimizer:
    """Hybrid SLSQP + CMA-ES optimization for individual genomes."""

    def __init__(self, model: GatedOutputModel, dim: int):
        self.model = model
        self.dim = dim

    def objective(self, params: np.ndarray,
                  test_vectors: List[Tuple]) -> float:
        genome = AERGenome.from_vector(
            params, self.dim, "OPT", Archetype.SCRIBE
        )
        errors = []
        for x, z, expected in test_vectors:
            pred = self.model.forward(x, z, genome)
            errors.append((pred - expected) ** 2)
        bce = float(np.mean(errors))
        l1 = float(np.sum(np.abs(params))) * 1e-4
        return bce + l1

    def optimize_slsqp(self, initial: np.ndarray,
                       test_vectors: List[Tuple]) -> np.ndarray:
        result = minimize(
            self.objective, initial,
            args=(test_vectors,),
            method="SLSQP",
            options={"maxiter": 500, "ftol": 1e-8},
        )
        return result.x if result.success else initial

    def optimize_cma(self, initial: np.ndarray,
                     test_vectors: List[Tuple]) -> np.ndarray:
        """CMA-ES fallback when SLSQP fails."""
        es = cma.CMAEvolutionStrategy(
            initial, 0.5,
            {"maxiter": 200, "verbose": -1}
        )
        while not es.stop():
            solutions = es.ask()
            fitnesses = [
                self.objective(s, test_vectors) for s in solutions
            ]
            es.tell(solutions, fitnesses)
        return es.result.xbest

    def optimize(self, genome: AERGenome,
                 test_vectors: List[Tuple]) -> AERGenome:
        initial = genome.to_vector()
        try:
            optimized = self.optimize_slsqp(initial, test_vectors)
        except Exception:
            optimized = self.optimize_cma(initial, test_vectors)
        return AERGenome.from_vector(
            optimized, self.dim, genome.srs_code, genome.archetype
        )

# ── sake_tipsy_engine_python_python_11.py ────────────────────────────────
class SafeExpr:
    """AST-based expression parser — no eval() risks."""
    import ast

    ALLOWED_OPS = {
        SafeExpr.ast.Add: lambda a, b: a + b,
        SafeExpr.ast.Sub: lambda a, b: a - b,
        SafeExpr.ast.Mult: lambda a, b: a * b,
        SafeExpr.ast.Div: lambda a, b: a / b if b != 0 else 0.0,
        SafeExpr.ast.Pow: lambda a, b: a ** min(b, 10),
        SafeExpr.ast.USub: lambda a: -a,
    }

    @classmethod
    def evaluate(cls, expr_str: str,
                 variables: Dict[str, float]) -> float:
        tree = cls.ast.parse(expr_str, mode="eval")
        return cls._eval_node(tree.body, variables)

    @classmethod
    def _eval_node(cls, node, variables: Dict[str, float]) -> float:
        if isinstance(node, cls.ast.Constant):
            return float(node.value)
        elif isinstance(node, cls.ast.Name):
            if node.id not in variables:
                raise ValueError(f"Unknown variable: {node.id}")
            return variables[node.id]
        elif isinstance(node, cls.ast.BinOp):
            left = cls._eval_node(node.left, variables)
            right = cls._eval_node(node.right, variables)
            op = cls.ALLOWED_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported op: {type(node.op)}")
            return op(left, right)
        elif isinstance(node, cls.ast.UnaryOp):
            operand = cls._eval_node(node.operand, variables)
            op = cls.ALLOWED_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported unary op")
            return op(operand)
        raise ValueError(f"Unsupported AST node: {type(node)}")


class FormulaRegistry:
    """YAML-based benchmark formula registry."""

    def __init__(self, path: str = "formulas.yaml"):
        with open(path) as f:
            self.formulas = yaml.safe_load(f)

    def get(self, name: str) -> Dict:
        return self.formulas[name]

    def evaluate(self, name: str,
                 variables: Dict[str, float]) -> float:
        formula = self.formulas[name]
        return SafeExpr.evaluate(formula["expression"], variables)

    def jitter_weights(self, name: str,
                       sigma: float = 0.35) -> Dict[str, float]:
        formula = self.formulas[name]
        weights = formula.get("weights", {})
        return {
            k: v * (1.0 + np.random.normal(0, sigma))
            for k, v in weights.items()
        }

# ── sake_tipsy_engine_python_python_12.py ────────────────────────────────
class LineageTracker:
    """SHA256 fingerprints, semantic diffs, compressed snapshots."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.log_path = output_dir / "lineage.jsonl"

    def record(self, genome: AERGenome, parent_fps: List[str],
               operation: str):
        entry = {
            "timestamp": time.time(),
            "fingerprint": genome.fingerprint,
            "srs_code": genome.srs_code,
            "generation": genome.generation,
            "parents": parent_fps,
            "operation": operation,
            "archetype": genome.archetype.value,
            "fitness": genome.fitness,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def semantic_diff(self, g1: AERGenome,
                      g2: AERGenome) -> Dict[str, float]:
        v1, v2 = g1.to_vector(), g2.to_vector()
        return {
            "l2_distance": float(np.linalg.norm(v1 - v2)),
            "cosine_similarity": float(
                np.dot(v1, v2) /
                (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8)
            ),
            "max_delta": float(np.max(np.abs(v1 - v2))),
            "mean_delta": float(np.mean(np.abs(v1 - v2))),
        }

# ── sake_tipsy_engine_python_python_13.py ────────────────────────────────
async def main():
    config = {
        "genome_dim": 16,
        "population_size": 50,
        "max_generations": 100,
        "stagnation_limit": 15,
        "mutation_rate": 0.05,
        "output_dir": "./sake_output",
        "dp_epsilon": 1.0,
    }

    engine = TipsyEngine(config)
    engine.initialize_population()

    # Test vectors: (activation_input, inhibition_input, expected_output)
    test_vectors = [
        (np.random.random(16), np.random.random(16), 0.7),
        (np.random.random(16), np.random.random(16), 0.3),
        (np.random.random(16), np.zeros(16), 0.9),
        (np.zeros(16), np.random.random(16), 0.1),
    ]
    ops_scores = {f"F{900+i:03d}": 0.5 for i in range(50)}

    client = openai.AsyncOpenAI()
    history = await engine.run(test_vectors, ops_scores, client)

    print(f"Evolution complete: {len(history)} generations")
    print(f"Best fitness: {history[-1]['best_fitness']:.4f}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

# ── sake_tipsy_engine_python_python_14.py ────────────────────────────────
"""
SAKE Tipsy Engine — Infrastructure Control Policies
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ICP Level: ICP-1 (Critical)
SRS Codes: F941-ENGINE, F900
CAPS Gate: cap.sake.evolve requires Grade B+
"""
from dataclasses import dataclass
from typing import Dict, List
from enum import Enum
class ICPLevel(str, Enum):
    ICP_0 = "ICP-0"   # Informational — read-only telemetry
    ICP_1 = "ICP-1"   # Critical — core evolution pipeline
    ICP_2 = "ICP-2"   # Standard — storage, vector ops
    ICP_3 = "ICP-3"   # Low — logging, metrics export
@dataclass
class SAKEPolicy:
    """Infrastructure control policy for SAKE operations."""
    policy_id: str
    description: str
    icp_level: ICPLevel
    required_caps_grade: str  # D, C, B, A, S
    rate_limit_per_hour: int
    allowed_environments: List[str]
    requires_fate_logging: bool = True
    requires_aegis_lineage: bool = True
    max_genome_dim: int = 64
    max_population_size: int = 500
    dp_epsilon_min: float = 0.1
SAKE_ICP_POLICIES: Dict[str, SAKEPolicy] = {
    "sake.evolve.generation": SAKEPolicy(
        policy_id="SAKE-ICP-001",
        description="Run one generation of AER genome evolution",
        icp_level=ICPLevel.ICP_1,
        required_caps_grade="B",
        rate_limit_per_hour=120,
        allowed_environments=["staging", "production"],
        max_population_size=500,
    ),
    "sake.optimize.slsqp": SAKEPolicy(
        policy_id="SAKE-ICP-002",
        description="SLSQP gradient optimization on individual genome",
        icp_level=ICPLevel.ICP_1,
        required_caps_grade="B",
        rate_limit_per_hour=60,
        allowed_environments=["staging", "production"],
    ),
    "sake.optimize.cma": SAKEPolicy(
        policy_id="SAKE-ICP-003",
        description="CMA-ES fallback optimizer",
        icp_level=ICPLevel.ICP_1,
        required_caps_grade="A",
        rate_limit_per_hour=30,
        allowed_environments=["staging", "production"],
    ),
    "sake.llm_splice": SAKEPolicy(
        policy_id="SAKE-ICP-004",
        description="LLM-guided gene splice (GPT-4o-mini)",
        icp_level=ICPLevel.ICP_1,
        required_caps_grade="A",
        rate_limit_per_hour=20,
        allowed_environments=["staging", "production"],
    ),
    "sake.vector.index": SAKEPolicy(
        policy_id="SAKE-ICP-005",
        description="FAISS vector store read/write",
        icp_level=ICPLevel.ICP_2,
        required_caps_grade="C",
        rate_limit_per_hour=500,
        allowed_environments=["dev", "staging", "production"],
    ),
    "sake.benchmark.score": SAKEPolicy(
        policy_id="SAKE-ICP-006",
        description="Compute composite benchmark score",
        icp_level=ICPLevel.ICP_2,
        required_caps_grade="C",
        rate_limit_per_hour=300,
        allowed_environments=["dev", "staging", "production"],
    ),
    "sake.privacy.apply": SAKEPolicy(
        policy_id="SAKE-ICP-007",
        description="Apply differential privacy to genome",
        icp_level=ICPLevel.ICP_1,
        required_caps_grade="A",
        rate_limit_per_hour=100,
        allowed_environments=["production"],
        dp_epsilon_min=0.1,
    ),
    "sake.export.manifest": SAKEPolicy(
        policy_id="SAKE-ICP-008",
        description="Export AER manifest YAML",
        icp_level=ICPLevel.ICP_3,
        required_caps_grade="B",
        rate_limit_per_hour=10,
        allowed_environments=["staging", "production"],
    ),
}
class SAKEPolicyEnforcer:
    """Enforce ICP policies before SAKE operations."""
    def __init__(self, caps_scorer=None, fate_ledger=None):
        self.caps = caps_scorer
        self.fate = fate_ledger
        self._call_counts: Dict[str, int] = {}
    async def enforce(
        self, policy_key: str, agent_id: str,
        environment: str = "staging",
    ) -> tuple:
        """Returns (allowed: bool, reason: str)."""
        policy = SAKE_ICP_POLICIES.get(policy_key)
        if not policy:
            return False, f"Unknown policy: {policy_key}"
        # Environment gate
        if environment not in policy.allowed_environments:
            return False, (
                f"Environment '{environment}' not allowed "
                f"for {policy_key}"
            )
        # CAPS grade gate
        if self.caps:
            profile = await self.caps.get_profile(agent_id)
            if profile and not self._grade_meets(
                profile.grade, policy.required_caps_grade
            ):
                return False, (
                    f"CAPS grade {profile.grade} below "
                    f"required {policy.required_caps_grade}"
                )
        # Rate limiting
        count = self._call_counts.get(policy_key, 0)
        if count >= policy.rate_limit_per_hour:
            return False, (
                f"Rate limit exceeded: {count}/"
                f"{policy.rate_limit_per_hour} per hour"
            )
        self._call_counts[policy_key] = count + 1
        return True, "OK"
    @staticmethod
    def _grade_meets(actual: str, required: str) -> bool:
        grades = {"D": 0, "C": 1, "B": 2, "A": 3, "S": 4}
        return grades.get(actual, 0) >= grades.get(required, 0)
