# Experimental benchmark modes

Modes such as `hybrid_v4`, `palace`, and `diary` in `longmemeval_bench.py` apply query-conditioned pipelines, synthetic index entries, LLM reranking, or other techniques that inflate retrieval scores relative to a minimal fixed-ingest protocol.

Running those modes prints a **stderr warning**. Treat reported numbers as ablations or upper bounds, not as a single headline metric.
