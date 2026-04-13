"""Golden / regression tests for benchmarks.metrics (no dataset download)."""

import importlib.util
from pathlib import Path

_metrics_path = Path(__file__).resolve().parents[1] / "benchmarks" / "metrics.py"
_spec = importlib.util.spec_from_file_location("bench_metrics", _metrics_path)
_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_metrics)

dcg = _metrics.dcg
evaluate_retrieval = _metrics.evaluate_retrieval
ndcg = _metrics.ndcg
session_id_from_corpus_id = _metrics.session_id_from_corpus_id


def test_dcg_empty():
    assert dcg([], 5) == 0.0


def test_dcg_single_relevant():
    # one relevant at rank 0 -> 1 / log2(2) = 1.0
    assert abs(dcg([1.0], 5) - 1.0) < 1e-9


def test_ndcg_perfect_ranking():
    corpus = ["a", "b", "c", "d"]
    correct = {"b"}
    rankings = [1, 0, 2, 3]  # b first
    assert ndcg(rankings, correct, corpus, k=3) == 1.0


def test_evaluate_retrieval_recall_any():
    corpus = ["x", "y", "z"]
    correct = {"y"}
    rankings = [0, 1, 2]
    any_r, all_r, n = evaluate_retrieval(rankings, correct, corpus, k=2)
    assert any_r == 1.0
    assert all_r == 1.0
    assert 0.0 <= n <= 1.0


def test_session_id_from_corpus_id_turn():
    cid = "sess_42_turn_3"
    assert session_id_from_corpus_id(cid) == "sess_42"


def test_session_id_from_corpus_id_plain():
    assert session_id_from_corpus_id("sess_only") == "sess_only"
