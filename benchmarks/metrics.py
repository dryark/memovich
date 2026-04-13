"""Shared retrieval metrics for benchmark scripts (unit-tested)."""

from __future__ import annotations

import math
from typing import List, Set


def dcg(relevances: List[float], k: int) -> float:
    """Discounted Cumulative Gain."""
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        score += rel / math.log2(i + 2)
    return score


def ndcg(rankings: List[int], correct_ids: Set[str], corpus_ids: List[str], k: int) -> float:
    """Normalized DCG."""
    relevances = [1.0 if corpus_ids[idx] in correct_ids else 0.0 for idx in rankings[:k]]
    ideal = sorted(relevances, reverse=True)
    idcg = dcg(ideal, k)
    if idcg == 0:
        return 0.0
    return dcg(relevances, k) / idcg


def evaluate_retrieval(
    rankings: List[int], correct_ids: Set[str], corpus_ids: List[str], k: int
):
    """
    Evaluate retrieval at rank k.
    Returns (recall_any, recall_all, ndcg_score).
    """
    top_k_ids = {corpus_ids[idx] for idx in rankings[:k]}
    recall_any = float(any(cid in top_k_ids for cid in correct_ids))
    recall_all = float(all(cid in top_k_ids for cid in correct_ids))
    ndcg_score = ndcg(rankings, correct_ids, corpus_ids, k)
    return recall_any, recall_all, ndcg_score


def session_id_from_corpus_id(corpus_id: str) -> str:
    """Extract session ID from a corpus ID (session vs turn granularity)."""
    if "_turn_" in corpus_id:
        return corpus_id.rsplit("_turn_", 1)[0]
    return corpus_id


EXPERIMENTAL_MODES = frozenset(
    {
        "hybrid",
        "hybrid_v2",
        "hybrid_v3",
        "hybrid_v4",
        "palace",
        "diary",
        "full",
    }
)


def warn_experimental_mode(mode: str) -> None:
    import sys

    if mode not in EXPERIMENTAL_MODES:
        return
    print(
        "\n".join(
            [
                "=" * 72,
                "WARNING: EXPERIMENTAL / UPPER-BOUND BENCHMARK MODE",
                f"  mode={mode!r} — not comparable to minimal ingest baselines.",
                "  For reportable numbers prefer: --mode raw --granularity turn",
                "  (and avoid synthetic docs, query-conditioned re-index, LLM rerank).",
                "=" * 72,
            ]
        ),
        file=sys.stderr,
    )
