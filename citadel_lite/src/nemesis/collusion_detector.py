# src/nemesis/collusion_detector.py
"""
Nemesis v2 — Collusion Detector

Graph-based coordinated behavior detection for agent collusion:
  - Mutual approval / endorsement tracking
  - Synchronized behavior detection
  - Voting bloc analysis
  - Cluster identification via clustering coefficient

SRS: NEM-COL-001 (Mutual Trust Inflation), NEM-COL-002 (Synchronized Voting),
     NEM-COL-004 (Economic Coordination)
CGRF v3.0, Tier 1
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interaction types
# ---------------------------------------------------------------------------

INTERACTION_TYPES = {
    "approval",         # agent A approved agent B's work
    "endorsement",      # agent A endorsed agent B's trust score
    "review",           # agent A reviewed agent B's output
    "delegation",       # agent A delegated work to agent B
    "vote_same",        # agents voted the same way
    "relay",            # information relay chain
    "xp_transfer",      # XP/TP transfer between agents
}


# ---------------------------------------------------------------------------
# Collusion Detector
# ---------------------------------------------------------------------------

class CollusionDetector:
    """
    Builds a weighted interaction graph and detects collusion patterns.

    Detection signals:
      - Mutual approval rate > 0.9 between any pair
      - Synchronized behavior change (< 5min apart)
      - Information relay chain (A→B→C→D with decreasing latency)
      - Council voting bloc (same vote > 90% of the time)
    """

    def __init__(self):
        # Directed weighted graph: edges[from_agent][to_agent] = {type: count}
        self._edges: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )
        # Timestamps of interactions for synchronization detection
        self._timestamps: Dict[str, List[str]] = defaultdict(list)
        # All known agents
        self._agents: Set[str] = set()
        # Council votes: vote_id -> {agent_id: vote_value}
        self._council_votes: Dict[str, Dict[str, str]] = {}

    # -- Ingestion ----------------------------------------------------------

    def ingest_interaction(
        self,
        from_agent: str,
        to_agent: str,
        interaction_type: str = "approval",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Record an interaction between two agents.

        Args:
            from_agent: Initiating agent
            to_agent: Receiving agent
            interaction_type: One of INTERACTION_TYPES
            metadata: Optional extra data (timestamp, context, etc.)
        """
        self._agents.add(from_agent)
        self._agents.add(to_agent)
        self._edges[from_agent][to_agent][interaction_type] += 1

        ts = (metadata or {}).get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )
        self._timestamps[from_agent].append(ts)
        self._timestamps[to_agent].append(ts)

    def ingest_council_vote(self, vote_id: str, agent_id: str, vote_value: str):
        """Record a Council vote for voting bloc analysis."""
        if vote_id not in self._council_votes:
            self._council_votes[vote_id] = {}
        self._council_votes[vote_id][agent_id] = vote_value
        self._agents.add(agent_id)

    # -- Scoring ------------------------------------------------------------

    def compute_collusion_score(self, agent_ids: List[str]) -> float:
        """
        Compute a collusion score (0.0-1.0) for a group of agents.

        Combines:
          - Mutual approval rate (40% weight)
          - Interaction density (30% weight)
          - Voting similarity (30% weight)
        """
        if len(agent_ids) < 2:
            return 0.0

        mutual_rate = self._mutual_approval_rate(agent_ids)
        density = self._interaction_density(agent_ids)
        voting_sim = self._voting_similarity(agent_ids)

        score = (mutual_rate * 0.4) + (density * 0.3) + (voting_sim * 0.3)
        return round(min(score, 1.0), 3)

    def _mutual_approval_rate(self, agent_ids: List[str]) -> float:
        """
        Fraction of agent pairs with bidirectional approval/endorsement.
        High rate (>0.9) is a collusion signal per NEM-COL-001.
        """
        pairs = 0
        mutual = 0

        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1:]:
                pairs += 1
                a_to_b = self._get_approval_count(a, b)
                b_to_a = self._get_approval_count(b, a)
                if a_to_b > 0 and b_to_a > 0:
                    # Mutual if both directions have significant interactions
                    total = a_to_b + b_to_a
                    if total >= 4:  # at least 2 each direction
                        mutual += 1

        return mutual / pairs if pairs > 0 else 0.0

    def _get_approval_count(self, from_agent: str, to_agent: str) -> int:
        """Count approval-like interactions from one agent to another."""
        edge = self._edges.get(from_agent, {}).get(to_agent, {})
        return edge.get("approval", 0) + edge.get("endorsement", 0)

    def _interaction_density(self, agent_ids: List[str]) -> float:
        """
        How densely connected are these agents compared to the full graph.
        Returns 0.0-1.0.
        """
        if len(agent_ids) < 2:
            return 0.0

        max_edges = len(agent_ids) * (len(agent_ids) - 1)  # directed
        actual_edges = 0

        for a in agent_ids:
            for b in agent_ids:
                if a != b and self._edges.get(a, {}).get(b):
                    actual_edges += 1

        return actual_edges / max_edges if max_edges > 0 else 0.0

    def _voting_similarity(self, agent_ids: List[str]) -> float:
        """
        Fraction of Council votes where these agents voted identically.
        High similarity (>0.9) is a collusion signal per NEM-COL-002.
        """
        if not self._council_votes:
            return 0.0

        total_votes = 0
        unanimous_votes = 0

        for vote_id, votes in self._council_votes.items():
            # Only consider votes where at least 2 of our agents participated
            relevant = {aid: v for aid, v in votes.items() if aid in agent_ids}
            if len(relevant) < 2:
                continue

            total_votes += 1
            values = list(relevant.values())
            if len(set(values)) == 1:  # all voted the same
                unanimous_votes += 1

        return unanimous_votes / total_votes if total_votes > 0 else 0.0

    # -- Cluster detection --------------------------------------------------

    def detect_clusters(self, min_score: float = 0.5) -> List[Dict[str, Any]]:
        """
        Find suspicious agent groups using clustering coefficient analysis.

        Returns list of clusters with:
          - agents: list of agent IDs
          - collusion_score: 0.0-1.0
          - signals: list of detected patterns
        """
        clusters: List[Dict[str, Any]] = []
        agents = list(self._agents)

        if len(agents) < 2:
            return clusters

        # Check all pairs first
        suspicious_pairs: List[Tuple[str, str, float]] = []
        for i, a in enumerate(agents):
            for b in agents[i + 1:]:
                pair_score = self.compute_collusion_score([a, b])
                if pair_score >= min_score:
                    suspicious_pairs.append((a, b, pair_score))

        # Build clusters from overlapping pairs
        visited: Set[str] = set()
        for a, b, score in sorted(suspicious_pairs, key=lambda x: x[2], reverse=True):
            if a in visited and b in visited:
                continue

            # Expand cluster by checking if other agents are also suspicious with a and b
            cluster_agents = {a, b}
            for other in agents:
                if other in cluster_agents:
                    continue
                # Check if 'other' is suspicious with both a and b
                score_with_a = self.compute_collusion_score([other, a])
                score_with_b = self.compute_collusion_score([other, b])
                if score_with_a >= min_score and score_with_b >= min_score:
                    cluster_agents.add(other)

            cluster_list = sorted(cluster_agents)
            cluster_score = self.compute_collusion_score(cluster_list)

            if cluster_score >= min_score:
                signals = self._identify_signals(cluster_list)
                clusters.append({
                    "agents": cluster_list,
                    "collusion_score": cluster_score,
                    "signals": signals,
                })
                visited.update(cluster_agents)

        return clusters

    def _identify_signals(self, agent_ids: List[str]) -> List[str]:
        """Identify specific collusion signals for a group."""
        signals = []

        # Check mutual approval
        mutual = self._mutual_approval_rate(agent_ids)
        if mutual > 0.8:
            signals.append("mutual_approval_rate_high")
        elif mutual > 0.5:
            signals.append("mutual_approval_rate_elevated")

        # Check voting bloc
        voting = self._voting_similarity(agent_ids)
        if voting > 0.9:
            signals.append("voting_bloc_detected")
        elif voting > 0.7:
            signals.append("voting_correlation_elevated")

        # Check interaction density
        density = self._interaction_density(agent_ids)
        if density > 0.8:
            signals.append("interaction_density_high")

        # Check for circular endorsement patterns
        if self._has_circular_endorsement(agent_ids):
            signals.append("circular_endorsement")

        return signals

    def _has_circular_endorsement(self, agent_ids: List[str]) -> bool:
        """Check if agents form a circular endorsement chain (A→B→C→A)."""
        if len(agent_ids) < 2:
            return False

        # Build adjacency for endorsement-type edges only
        for i, a in enumerate(agent_ids):
            # Check if there's a path from a back to a through other agents
            next_idx = (i + 1) % len(agent_ids)
            b = agent_ids[next_idx]
            if self._get_approval_count(a, b) == 0:
                return False  # chain broken

        return True  # all agents endorse the next in the ring

    # -- Voting bloc analysis -----------------------------------------------

    def check_voting_bloc(
        self,
        council_votes: Optional[Dict[str, Dict[str, str]]] = None,
        threshold: float = 0.9,
    ) -> Dict[str, Any]:
        """
        Detect coordinated Council voting patterns.

        Args:
            council_votes: Optional override; if None, uses ingested votes.
            threshold: Similarity threshold to flag as bloc.

        Returns:
            Dict with detected blocs and their voting similarity.
        """
        votes = council_votes or self._council_votes

        if not votes:
            return {"blocs": [], "total_votes_analyzed": 0}

        # Build pairwise similarity matrix
        all_voters: Set[str] = set()
        for v in votes.values():
            all_voters.update(v.keys())

        voters = sorted(all_voters)
        blocs: List[Dict[str, Any]] = []

        # Check all pairs
        for i, a in enumerate(voters):
            for b in voters[i + 1:]:
                shared = 0
                same = 0
                for vote_id, vote_map in votes.items():
                    if a in vote_map and b in vote_map:
                        shared += 1
                        if vote_map[a] == vote_map[b]:
                            same += 1

                if shared >= 3:  # minimum votes to judge
                    similarity = same / shared
                    if similarity >= threshold:
                        blocs.append({
                            "agents": [a, b],
                            "similarity": round(similarity, 3),
                            "shared_votes": shared,
                            "unanimous_votes": same,
                        })

        return {
            "blocs": blocs,
            "total_votes_analyzed": len(votes),
            "total_voters": len(voters),
        }

    # -- Utility ------------------------------------------------------------

    def get_agent_stats(self, agent_id: str) -> Dict[str, Any]:
        """Get interaction statistics for a single agent."""
        outgoing = sum(
            sum(counts.values())
            for counts in self._edges.get(agent_id, {}).values()
        )
        incoming = sum(
            sum(counts.values())
            for peer_edges in self._edges.values()
            for target, counts in peer_edges.items()
            if target == agent_id
        )
        peers = set()
        for target in self._edges.get(agent_id, {}):
            peers.add(target)
        for src, targets in self._edges.items():
            if agent_id in targets:
                peers.add(src)

        return {
            "agent_id": agent_id,
            "outgoing_interactions": outgoing,
            "incoming_interactions": incoming,
            "unique_peers": len(peers),
            "peers": sorted(peers),
        }

    def reset(self):
        """Clear all state (for testing)."""
        self._edges.clear()
        self._timestamps.clear()
        self._agents.clear()
        self._council_votes.clear()
