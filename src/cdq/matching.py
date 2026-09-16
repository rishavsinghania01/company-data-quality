"""Entity resolution across source systems.

The approach is blocking followed by scored comparison inside each block, then
union-find to turn accepted pairs into clusters. Blocking is what keeps this
from being O(n^2): without it, 50k records is 1.25 billion comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    record_id: str
    name_canonical: str
    state: str | None
    phone_e164: str | None
    address_line: str | None


@dataclass(frozen=True)
class ScoredPair:
    left_id: str
    right_id: str
    score: float
    reasons: tuple[str, ...]


def blocking_key(name_canonical: str, state: str | None) -> str:
    """Records only get compared when they share a block.

    First four characters of the canonical name plus state is a deliberate
    trade: it misses pairs whose names diverge in the first four characters
    (a real recall cost, see README) but keeps block sizes small enough that
    the pairwise comparison inside a block stays cheap.
    """
    prefix = (name_canonical or "")[:4].ljust(4, "_")
    return f"{prefix}|{(state or '__').upper()}"


def token_set_ratio(left: str, right: str) -> float:
    """Jaccard similarity over token sets.

    Token sets rather than character edit distance because the common failure
    is word order and extra words ("Acme Widgets" vs "Widgets Acme Holdings"),
    not typos.
    """
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union


def score_pair(left: Candidate, right: Candidate) -> ScoredPair:
    """Weighted score in [0, 1] with the reasons that produced it.

    Reasons are carried through to the output table so that a human reviewing
    a questionable merge can see why the pipeline joined two records.
    """
    reasons: list[str] = []
    name_score = token_set_ratio(left.name_canonical, right.name_canonical)
    score = 0.70 * name_score
    if name_score >= 0.99:
        reasons.append("name_exact")
    elif name_score > 0:
        reasons.append(f"name_overlap_{name_score:.2f}")

    if left.phone_e164 and left.phone_e164 == right.phone_e164:
        score += 0.20
        reasons.append("phone_exact")

    if left.address_line and left.address_line == right.address_line:
        score += 0.10
        reasons.append("address_exact")

    # Rounded because the weights are decimal fractions and binary floating
    # point puts 0.70 + 0.10 at 0.7999999999999999, which silently fails a
    # >= 0.80 threshold.
    return ScoredPair(left.record_id, right.record_id, round(min(score, 1.0), 4), tuple(reasons))


class UnionFind:
    """Standard disjoint set with path compression and union by rank."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)
        self._rank.setdefault(item, 0)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self._rank[left_root] < self._rank[right_root]:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        if self._rank[left_root] == self._rank[right_root]:
            self._rank[left_root] += 1


def build_blocks(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    blocks: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        blocks.setdefault(blocking_key(candidate.name_canonical, candidate.state), []).append(candidate)
    return blocks


def compare_within_blocks(candidates: list[Candidate], threshold: float) -> list[ScoredPair]:
    accepted: list[ScoredPair] = []
    for block in build_blocks(candidates).values():
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                pair = score_pair(block[i], block[j])
                if pair.score >= threshold:
                    accepted.append(pair)
    return accepted


def cluster(candidates: list[Candidate], threshold: float = 0.80) -> dict[str, str]:
    """Return record_id -> cluster_id.

    Clustering is transitive by construction: A-B and B-C puts all three in one
    cluster even if A and C never scored above the threshold themselves. That is
    usually what you want for the same company spelled three ways, and it is the
    thing to watch when a threshold is set too low, because one bad link merges
    two real companies.
    """
    union_find = UnionFind()
    for candidate in candidates:
        union_find.add(candidate.record_id)
    for pair in compare_within_blocks(candidates, threshold):
        union_find.union(pair.left_id, pair.right_id)

    roots: dict[str, list[str]] = {}
    for candidate in candidates:
        roots.setdefault(union_find.find(candidate.record_id), []).append(candidate.record_id)

    assignments: dict[str, str] = {}
    for index, (_, members) in enumerate(sorted(roots.items()), start=1):
        cluster_id = f"CL{index:06d}"
        for member in members:
            assignments[member] = cluster_id
    return assignments
