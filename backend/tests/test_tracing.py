import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from retrieval import hybrid_search
from schemas import QuestionRequest, Reference
from tracing import Tracer


def test_trace_round_trip(tmp_path):
    path = tmp_path / "nested" / "traces.sqlite3"
    tracer = Tracer(path)
    trace = tracer.start("question", {"question": "docker?"})
    with trace.span("dense", candidates=[]) as span:
        span.set("n_chunks", 2)
    with trace.span("rrf", top_k=2):
        pass
    trace.finish("ok", {"tokens": 0})

    saved = Tracer(path).get(trace.id)
    assert saved["id"] == trace.id
    assert len(trace.id) == 32
    assert saved["kind"] == "question"
    assert saved["started_at"].endswith("+00:00")
    assert saved["status"] == "ok"
    assert saved["input"] == {"question": "docker?"}
    assert saved["totals"] == {"tokens": 0}
    assert saved["duration_ms"] >= 0
    assert [s["name"] for s in saved["spans"]] == ["dense", "rrf"]
    assert all(s["duration_ms"] >= 0 for s in saved["spans"])
    assert saved["spans"][0]["attributes"]["n_chunks"] == 2
    assert tracer.get("missing") is None


def test_span_records_and_reraises_exception(tmp_path):
    tracer = Tracer(tmp_path / "traces.sqlite3")
    trace = tracer.start("indexing", {"filename": "notes.md"})
    message = "failure " * 50
    with pytest.raises(ValueError, match="failure"):
        with trace.span("embed"):
            raise ValueError(message)
    trace.finish("error", {"n_chunks": 0})
    span = tracer.get(trace.id)["spans"][0]
    assert span["attributes"]["error"] == f"ValueError: {message}"[:200]
    assert span["duration_ms"] >= 0


def test_retention_and_list_filter(tmp_path):
    tracer = Tracer(tmp_path / "traces.sqlite3", max_traces=3)
    ids = []
    for i in range(5):
        trace = tracer.start("question" if i % 2 == 0 else "indexing", {})
        trace.finish("ok", {})
        ids.append(trace.id)
    rows = tracer.list()
    assert [row["id"] for row in rows] == ids[:1:-1]
    assert all(set(row) == {"id", "kind", "started_at", "duration_ms", "status"} for row in rows)
    assert all(tracer.get(trace_id) is None for trace_id in ids[:2])
    assert [r["id"] for r in tracer.list(kind="indexing")] == [ids[3]]
    assert len(tracer.list(limit=1)) == 1
    assert tracer.list(limit=0) == []


def reference(chunk_id):
    return Reference(chunk_id=chunk_id, filename="notes.md", chunk_index=0,
                     char_start=0, char_end=11, text="secret body", score=0.9)


def assert_no_text(value):
    if isinstance(value, dict):
        assert "text" not in value
        for item in value.values():
            assert_no_text(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_text(item)


def test_hybrid_search_trace_contains_metadata_only(tmp_path):
    tracer = Tracer(tmp_path / "traces.sqlite3")
    trace = tracer.start("question", {})
    store = SimpleNamespace(
        search=lambda *args: [reference("a#0"), reference("a#1")],
        bm25_search=lambda *args: [reference("a#1")],
    )
    req = QuestionRequest(question="docker?", top_k=2)
    chunks, path, cost = hybrid_search(store, req, trace=trace)
    plain, plain_path, plain_cost = hybrid_search(store, req)
    assert chunks == plain
    assert path == plain_path
    assert (cost.llm_calls, cost.tokens) == (plain_cost.llm_calls, plain_cost.tokens)
    trace.finish("ok", {})
    saved = tracer.get(trace.id)
    assert [s["name"] for s in saved["spans"]] == ["dense", "bm25", "rrf"]
    assert saved["spans"][0]["attributes"]["candidates"] == [
        {"chunk_id": "a#0", "rank": 1}, {"chunk_id": "a#1", "rank": 2},
    ]
    assert saved["spans"][2]["attributes"]["results"][0]["chunk_id"] == "a#1"
    assert_no_text(saved)
    assert "secret body" not in json.dumps(saved)


def test_graph_span_records_names_and_edge_count(tmp_path):
    tracer = Tracer(tmp_path / "traces.sqlite3")
    trace = tracer.start("question", {})
    graph = SimpleNamespace(search=lambda *args: {
        "chunks": [reference("a#0")],
        "path": {"entities": ["Docker"], "edges": [{"from": "Docker", "to": "Container"}]},
        "llm_calls": 1, "tokens": 5,
    })
    req = QuestionRequest(question="docker?", top_k=1,
                          retrievers={"dense": False, "bm25": False, "graph": True})
    _, _, cost = hybrid_search(None, req, graph=graph, trace=trace)
    assert (cost.llm_calls, cost.tokens) == (1, 5)
    assert trace.spans[0]["attributes"] == {
        "candidates": [{"chunk_id": "a#0", "rank": 1}],
        "entities": ["Docker"], "edges_count": 1,
    }
    assert_no_text(trace.spans)


@pytest.fixture
def traced_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from store import Store

    # Exercise the real indexing methods with in-memory embedding/BM25 stand-ins.
    store = Store.__new__(Store)
    store.files_dir = tmp_path / "files"
    store.files_dir.mkdir()
    store.docs_path = tmp_path / "documents.json"
    store.settings_path = tmp_path / "settings.json"
    store.collection = SimpleNamespace(add=lambda **kwargs: None)
    store.bm25 = SimpleNamespace(add=lambda rows: None, clear=lambda: None)
    store.client = SimpleNamespace(delete_collection=lambda name: None)
    store.get_collection = lambda: store.collection
    store.search = lambda *args: [reference("a#0")]
    store.bm25_search = lambda *args: [reference("a#0")]
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    monkeypatch.setattr(main, "graph", None)
    return TestClient(main.app, raise_server_exceptions=False), main


def test_question_endpoints_and_llm_totals(traced_client, monkeypatch):
    from schemas import AskResult, Cost

    client, main = traced_client
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setattr(main, "answer_question", lambda *args: AskResult(
        status="answered", answer="ok", references=[], cost=Cost(llm_calls=1, tokens=12),
    ))
    body = {"question": "docker?", "top_k": 1}
    response = client.post("/ask", json=body)
    assert response.status_code == 200
    trace_id = response.json()["trace_id"]
    saved = client.get(f"/traces/{trace_id}").json()
    assert saved["status"] == "answered"
    assert saved["totals"] == {"llm_calls": 1, "tokens": 12}
    assert saved["spans"][-1]["attributes"] == {
        "model": "test-model", "chunks_sent": ["a#0"], "tokens": 12,
        "status": "answered", "error": None,
    }
    assert saved["input"]["question"] == body["question"]
    retrieved = client.post("/retrieve", json=body).json()
    saved = main.tracer.get(retrieved["trace_id"])
    assert [s["name"] for s in saved["spans"]] == ["dense", "bm25", "rrf"]
    rows = client.get("/traces", params={"kind": "question", "limit": 1}).json()
    assert [row["id"] for row in rows] == [retrieved["trace_id"]]
    assert "spans" not in rows[0]
    assert client.get("/traces/missing").status_code == 404
    assert client.get("/traces?kind=invalid").status_code == 422


@pytest.mark.parametrize("endpoint", ["/ask", "/retrieve"])
@pytest.mark.parametrize("error", [ValueError("invalid retrieval"), RuntimeError("failed retrieval")])
def test_retrieval_failure_finishes_trace(traced_client, endpoint, error):
    client, main = traced_client

    def broken(*args):
        raise error

    main.store.search = broken
    response = client.post(endpoint, json={"question": "docker?", "top_k": 1})
    assert response.status_code == (400 if isinstance(error, ValueError)
                                    else 200 if endpoint == "/ask" else 500)
    rows = main.tracer.list()
    assert len(rows) == 1
    saved = main.tracer.get(rows[0]["id"])
    assert saved["status"] == "error"
    assert saved["spans"][0]["attributes"]["error"].startswith(type(error).__name__)
    if response.status_code == 200:
        assert response.json()["trace_id"] == saved["id"]


def test_upload_and_reindex_traces(traced_client):
    client, main = traced_client
    response = client.post("/documents", files={"file": ("notes.md", b"secret body " * 80)})
    assert response.status_code == 200
    saved = main.tracer.get(main.tracer.list(kind="indexing")[0]["id"])
    assert saved["input"] == {"filename": "notes.md"}
    assert saved["status"] == "ok"
    assert saved["totals"] == {"n_chunks": response.json()["n_chunks"]}
    assert [s["name"] for s in saved["spans"]] == ["chunk", "embed", "bm25_index"]
    assert "secret body" not in json.dumps(saved)
    settings = {"chunk_size": 100, "overlap_percent": 20, "top_k": 3}
    assert client.put("/settings", json=settings).status_code == 200
    saved = main.tracer.get(main.tracer.list(kind="indexing")[0]["id"])
    assert saved["input"] == {"chunk_size": 100, "overlap_percent": 20}
    assert saved["totals"]["n_chunks"] > response.json()["n_chunks"]
    assert [s["name"] for s in saved["spans"]] == ["chunk", "embed", "bm25_index"]


def test_indexing_failure_finishes_trace(traced_client):
    client, main = traced_client

    def broken(**kwargs):
        raise RuntimeError("embedding unavailable")

    main.store.collection.add = broken
    response = client.post("/documents", files={"file": ("notes.md", b"secret body")})
    assert response.status_code == 500
    saved = main.tracer.get(main.tracer.list(kind="indexing")[0]["id"])
    assert saved["status"] == "error"
    assert saved["totals"] == {"n_chunks": 0}
    assert saved["spans"][-1]["attributes"]["error"] == "RuntimeError: embedding unavailable"
