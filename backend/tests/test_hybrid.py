import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bm25 import BM25Index, bm25_tokens
from retrieval import rrf
from schemas import Reference


def ref(chunk_id):
    return Reference(chunk_id=chunk_id, filename="f.md", chunk_index=0, char_start=0, char_end=1, text="x", score=0)


def row(chunk_id, doc_id, text):
    return {"chunk_id": chunk_id, "doc_id": doc_id, "filename": f"{doc_id}.md", "chunk_index": 0,
            "char_start": 0, "char_end": len(text), "text": text}


def test_tokens_keep_identifiers_and_drop_stop_words():
    assert bm25_tokens("What does KST-2044 mean? Add 203.0.113.10") == ["kst-2044", "mean", "add", "203.0.113.10"]


def test_bm25_exact_identifier(tmp_path):
    index = BM25Index(tmp_path / "bm25.sqlite3")
    index.add([row("a#0", "a", "KST-2040 is a timeout."), row("a#1", "a", "KST-2044: the addresses are missing.")])
    assert [r["chunk_id"] for r in index.search("KST-2044", [], 5)] == ["a#1"]


def test_bm25_filters_documents_and_deletes(tmp_path):
    index = BM25Index(tmp_path / "bm25.sqlite3")
    index.add([row("a#0", "a", "docker compose"), row("b#0", "b", "docker swarm")])
    assert [r["chunk_id"] for r in index.search("docker", ["b"], 5)] == ["b#0"]
    index.delete_document("b")
    assert index.count() == 1


def test_bm25_only_stop_words(tmp_path):
    index = BM25Index(tmp_path / "bm25.sqlite3")
    index.add([row("a#0", "a", "what is it")])
    assert index.search("what is it", [], 5) == []


def test_rrf_merges_and_keeps_ranks():
    out = rrf({"dense": [ref("x"), ref("y")], "bm25": [ref("y"), ref("z")]}, top_k=3)
    assert [r.chunk_id for r in out] == ["y", "x", "z"]
    assert [(f.retriever, f.rank) for f in out[0].found_by] == [("dense", 2), ("bm25", 1)]
    assert out[0].rrf_score == round(1 / 62 + 1 / 61, 5)


