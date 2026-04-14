"""Contract tests for vector backends (memory by default in tests)."""

from memovich.backends.memory import MemoryBackend
from memovich.embeddings import embed_texts
from memovich.metadata_keys import NAMESPACE, SEGMENT


def test_memory_collection_roundtrip():
    backend = MemoryBackend(embed_fn=embed_texts)
    col = backend.get_collection("/tmp/mp_contract_palace", "memovich_chunks", create=True)
    col.delete()

    col.add(
        ids=["c1"],
        documents=["hello world semantic test phrase"],
        metadatas=[{NAMESPACE: "ns", SEGMENT: "seg", "source_file": "f.txt"}],
    )
    assert col.count() == 1

    g = col.get(ids=["c1"], include=["documents", "metadatas"])
    assert g["documents"][0].startswith("hello world")

    q = col.query(
        query_texts=["semantic phrase"],
        n_results=3,
        where={NAMESPACE: "ns"},
        include=["documents", "metadatas", "distances"],
    )
    assert q["ids"][0] == ["c1"]
    assert len(q["distances"][0]) == 1

    col.update(ids=["c1"], documents=["updated content here for embedding"])
    g2 = col.get(ids=["c1"], include=["documents"])
    assert "updated" in g2["documents"][0]

    col.delete(ids=["c1"])
    assert col.count() == 0
