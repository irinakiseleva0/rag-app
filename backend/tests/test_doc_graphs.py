import json
import sys
import threading
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import graph_build
import llm_client
import main
from doc_graphs import DocGraphs
from graph_build import GENERIC_PROMPT, build_graph
from graph_retriever import GraphRetriever
from graph_schema import GenericEntity, GenericExtraction, GenericTriple
from redaction import redact
from store import Store
from test_api import FakeEmbedding
from tracing import Tracer


def triple(subject="Messaging", target="Delivery", relation="OWNS"):
    return {"subject": {"name": subject, "type": "Team"}, "relation": relation,
            "object": {"name": target, "type": "Service"}}


def reply(*triples):
    return json.dumps({"triples": list(triples)})


@pytest.fixture
def graphs(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_GRAPH_DELAY_SECONDS", "0")
    store = Store(tmp_path / "store", FakeEmbedding())
    tracer = Tracer(tmp_path / "traces.sqlite3")
    return DocGraphs(tmp_path / "graphs", store, tracer, None,
                     llm=lambda prompt: (reply(triple()), 12))


def join(thread):
    thread.join(timeout=10)
    assert not thread.is_alive(), "Graph build did not finish"


def test_generic_build_normalizes_relations_and_drops_placeholders():
    graph = build_graph(
        [{"chunk_id": "doc#0000", "text": "Messaging depends on Delivery."}],
        llm=lambda prompt: reply(triple(relation="depends on"), triple(subject="[NAME]"),
                                 triple(target="[EMAIL]"), triple(subject="[PHONE]")),
        prompt=GENERIC_PROMPT, extraction_model=GenericExtraction,
    )
    assert graph["edges"][0]["relation"] == "DEPENDS_ON"
    assert graph["stats"]["dropped"] == 3
    assert len(graph["nodes"]) == 2


@pytest.mark.parametrize("value", ["x", "1_OWNS", "A/B", "A" * 41, ""])
def test_generic_relation_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        GenericTriple.model_validate(triple(relation=value))


def test_generic_names_and_hyphenated_relation():
    with pytest.raises(ValidationError):
        GenericEntity(name="  ", type="Person")
    assert GenericTriple.model_validate(triple(relation="  part-of ")).relation == "PART_OF"


def test_progress_and_delay_include_failures_and_validation_retries(monkeypatch):
    events = []
    answers = iter(["invalid", reply(triple()), RuntimeError("unavailable")])

    def llm(prompt):
        events.append("call")
        value = next(answers)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(graph_build, "sleep", lambda seconds: events.append(("sleep", seconds)))
    graph = build_graph(
        [{"chunk_id": f"doc#{i:04d}", "text": "Fact"} for i in range(2)], llm=llm,
        prompt=GENERIC_PROMPT, extraction_model=GenericExtraction,
        on_progress=lambda done, total: events.append(("progress", done, total)), delay_seconds=4,
    )
    assert events == ["call", ("sleep", 4), "call", ("progress", 1, 2),
                      ("sleep", 4), "call", ("progress", 2, 2)]
    assert graph["stats"]["llm_calls"] == 3
    assert graph["stats"]["failures"] == 1


def test_build_persists_document_provenance_redacts_contacts_and_traces(graphs):
    document = "Inès Moreau leads Messaging. Contact a@b.com or +33 6 12 34 56 78. " * 20
    doc = graphs.store.add_document("notes.md", document)
    prompts = []
    changes = []

    def llm(prompt):
        prompts.append(prompt)
        return reply(triple()), 12

    graphs.llm = llm
    graphs.on_change = lambda: changes.append(True)
    assert graphs.status(doc.id)["status"] == "none"
    join(graphs.start_build(doc.id))
    status = graphs.status(doc.id)
    assert status["status"] == "ready"
    assert status["progress"] == {"done": doc.n_chunks, "total": doc.n_chunks}
    assert status["stats"]["nodes"] == 2
    assert status["stats"]["edges"] == 1
    assert status["stats"]["llm_calls"] == doc.n_chunks
    assert status["stats"]["tokens"] == 12 * doc.n_chunks
    for item in status["nodes"] + status["edges"]:
        assert item["chunk_ids"]
        assert all(chunk_id.startswith(doc.id + "#") for chunk_id in item["chunk_ids"])
    assert any("Inès Moreau" in prompt for prompt in prompts)
    assert any("[EMAIL]" in prompt and "[PHONE]" in prompt for prompt in prompts)
    assert all("a@b.com" not in prompt and "+33 6 12 34 56 78" not in prompt for prompt in prompts)
    assert changes == [True]
    path = graphs.graph_dir / f"{doc.id}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["stats"]["nodes"] == 2
    restarted = DocGraphs(graphs.graph_dir, graphs.store, graphs.tracer, None)
    assert restarted.status(doc.id) == status
    trace = graphs.tracer.get(graphs.tracer.list()[0]["id"])
    assert trace["kind"] == "indexing" and trace["status"] == "ok"
    assert trace["input"] == {"graph_for": "notes.md"}
    assert len(trace["spans"]) == 1
    span = trace["spans"][0]
    assert span["name"] == "graph_build"
    for key in ("chunks", "nodes", "edges", "llm_calls", "tokens", "failures", "model"):
        assert key in span["attributes"]
    assert "Inès" not in json.dumps(trace)


def test_all_failed_chunks_report_short_error_and_write_no_file(graphs):
    doc = graphs.store.add_document("notes.md", "Messaging owns Delivery.")

    def fail(prompt):
        raise RuntimeError("model unavailable " + "x" * 300)

    graphs.llm = fail
    join(graphs.start_build(doc.id))
    status = graphs.status(doc.id)
    assert status["status"] == "error"
    assert status["error"].startswith("model unavailable")
    assert len(status["error"]) == 200
    assert status["nodes"] == status["edges"] == []
    assert status["stats"] is None
    assert status["progress"]["done"] == doc.n_chunks
    assert not (graphs.graph_dir / f"{doc.id}.json").exists()
    trace = graphs.tracer.get(graphs.tracer.list()[0]["id"])
    assert trace["status"] == "error"
    assert trace["spans"][0]["attributes"]["failures"] == doc.n_chunks
    graphs.llm = lambda prompt: reply(triple())
    join(graphs.start_build(doc.id))
    assert graphs.status(doc.id)["status"] == "ready"


def test_successful_empty_extraction_is_ready(graphs):
    doc = graphs.store.add_document("notes.md", "No explicit facts.")
    graphs.llm = lambda prompt: reply()
    join(graphs.start_build(doc.id))
    status = graphs.status(doc.id)
    assert status["status"] == "ready"
    assert status["nodes"] == status["edges"] == []


def test_from_graphs_merges_names_aliases_and_edges_without_mutating_inputs(graphs):
    def graph(prefix, name, entity_type):
        return {
            "nodes": [
                {"id": "a", "name": name, "type": entity_type,
                 "aliases": [prefix], "chunk_ids": [f"{prefix}#0000"]},
                {"id": "b", "name": "Delivery", "type": "Service", "chunk_ids": [f"{prefix}#0001"]},
            ],
            "edges": [{"source": "a", "relation": "OWNS", "target": "b", "chunk_ids": [f"{prefix}#0000"]}],
        }

    inputs = [graph("doc1", "Messaging", "Team"), graph("doc2", "The Messaging team", "Service")]
    original = json.dumps(inputs)
    merged = GraphRetriever.from_graphs(inputs, graphs.store)
    assert len(merged.nodes) == 2
    messaging = next(node for node in merged.nodes.values() if node["name"] == "Messaging")
    assert messaging["type"] == "Team"
    assert messaging["chunk_ids"] == ["doc1#0000", "doc2#0000"]
    assert set(messaging["aliases"]) == {"Messaging", "The Messaging team", "doc1", "doc2"}
    assert merged.edges == [{"source": messaging["id"], "relation": "OWNS", "target": "n2",
                             "chunk_ids": ["doc1#0000", "doc2#0000"]}]
    assert json.dumps(inputs) == original


def test_api_conflict_chunk_lookup_and_delete(graphs, monkeypatch):
    monkeypatch.setattr(main, "store", graphs.store)
    monkeypatch.setattr(main, "tracer", graphs.tracer)
    monkeypatch.setattr(main, "doc_graphs", graphs)
    monkeypatch.setattr(main, "graph", GraphRetriever.from_graphs([], graphs.store))
    graphs.on_change = main.rebuild_graph
    client = TestClient(main.app)
    text = "Messaging owns Delivery."
    doc = client.post("/documents", files={"file": ("notes.md", text, "text/plain")}).json()
    url = f"/documents/{doc['id']}/graph"
    entered, release = threading.Event(), threading.Event()

    def llm(prompt):
        entered.set()
        assert release.wait(10)
        return reply(triple())

    graphs.llm = llm
    try:
        response = client.post(url)
        assert response.status_code == 202 and response.json() == {"status": "building"}
        assert entered.wait(10)
        status = client.get(url).json()
        assert status["status"] == "building"
        assert status["progress"] == {"done": 0, "total": doc["n_chunks"]}
        assert status["nodes"] == status["edges"] == []
        assert client.post(url).status_code == 409
    finally:
        release.set()
        join(graphs.threads[doc["id"]])
    assert client.get(url).json()["status"] == "ready"
    result = client.post("/retrieve", json={"question": "Messaging", "doc_ids": [doc["id"]], "top_k": 3,
                         "retrievers": {"dense": False, "bm25": False, "graph": True}})
    assert result.status_code == 200
    assert result.json()["chunks"][0]["text"] == text
    chunk_id = f"{doc['id']}#0000"
    passage = client.get("/chunks/" + quote(chunk_id, safe="")).json()
    assert passage["chunk_id"] == chunk_id and passage["text"] == text and passage["score"] == 0
    assert client.get("/chunks/missing%230000").status_code == 404
    assert client.get("/documents/missing/graph").status_code == 404
    assert client.post("/documents/missing/graph").status_code == 404
    assert client.delete(f"/documents/{doc['id']}").status_code == 200
    assert not (graphs.graph_dir / f"{doc['id']}.json").exists()
    assert main.graph.nodes == {}


def test_kestrel_subgraph_maps_only_this_documents_provenance(graphs, tmp_path):
    doc = graphs.store.add_document("service-catalog.md", "Service catalog.")
    path = tmp_path / "kestrel.json"
    graph = {
        "nodes": [
            {"id": "a", "name": "Messaging", "type": "Team", "chunk_ids": ["service-catalog.md#0003", "other.md#0001"]},
            {"id": "b", "name": "Delivery", "type": "Service", "chunk_ids": ["service-catalog.md#0003"]},
            {"id": "c", "name": "Other", "type": "Concept", "chunk_ids": ["other.md#0001"]},
        ],
        "edges": [
            {"source": "a", "relation": "OWNS", "target": "b", "chunk_ids": ["service-catalog.md#0003", "other.md#0001"]},
            {"source": "c", "relation": "USES", "target": "b", "chunk_ids": ["other.md#0001"]},
        ],
        "stats": {"chunks": 20, "nodes": 3, "edges": 2, "llm_calls": 20, "tokens": 400, "seconds": 8, "model": "fake"},
    }
    path.write_text(json.dumps(graph), encoding="utf-8")
    graphs.kestrel_graph_path = path
    status = graphs.status(doc.id)
    assert status["status"] == "ready"
    assert [node["id"] for node in status["nodes"]] == ["a", "b"]
    assert len(status["edges"]) == 1
    for item in status["nodes"] + status["edges"]:
        assert item["chunk_ids"] == [f"{doc.id}#0003"]
    assert status["stats"] == {"nodes": 2, "edges": 1, "llm_calls": 20, "tokens": 400, "seconds": 8, "model": "fake"}
    join(graphs.start_build(doc.id))
    assert len(graphs.all_graphs()) == 2
    graphs.clear_all()
    assert graphs.all_graphs() == [graph]
    assert graphs.status(doc.id)["status"] == "ready"
    assert path.exists()


def test_redact_can_keep_names():
    clean, count = redact("Inès Moreau, a@b.com", names=False)
    assert clean == "Inès Moreau, [EMAIL]" and count == 1
    assert "[NAME]" in redact("Inès Moreau, a@b.com")[0]


@pytest.mark.parametrize("operation", ["delete", "clear_all"])
def test_invalidated_build_cannot_recreate_stale_graph(graphs, operation):
    doc = graphs.store.add_document("notes.md", "Messaging owns Delivery.")
    entered, release = threading.Event(), threading.Event()

    def llm(prompt):
        entered.set()
        assert release.wait(10)
        return reply(triple())

    graphs.llm = llm
    thread = graphs.start_build(doc.id)
    try:
        assert entered.wait(10)
        if operation == "delete":
            graphs.delete(doc.id)
        else:
            graphs.clear_all()
    finally:
        release.set()
        join(thread)
    assert not (graphs.graph_dir / f"{doc.id}.json").exists()
    assert graphs.status(doc.id)["status"] == "none"


def test_settings_only_discards_graphs_when_reindexing(graphs, monkeypatch):
    monkeypatch.setattr(main, "store", graphs.store)
    monkeypatch.setattr(main, "tracer", graphs.tracer)
    monkeypatch.setattr(main, "doc_graphs", graphs)
    monkeypatch.setattr(main, "graph", GraphRetriever.from_graphs([], graphs.store))
    graphs.on_change = main.rebuild_graph
    doc = graphs.store.add_document("notes.md", "Messaging owns Delivery. " * 40)
    join(graphs.start_build(doc.id))
    client = TestClient(main.app)
    settings = client.get("/settings").json()
    settings["top_k"] += 1
    assert client.put("/settings", json=settings).status_code == 200
    assert graphs.status(doc.id)["status"] == "ready"
    settings["chunk_size"] = 100
    assert client.put("/settings", json=settings).status_code == 200
    assert graphs.status(doc.id)["status"] == "none"
    assert graphs.all_graphs() == []
    assert main.graph.nodes == {}


def test_local_llm_without_key_omits_authorization(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1/")
    calls = []

    def post(url, json, headers, timeout):
        calls.append(headers)
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(llm_client.httpx, "post", post)
    assert llm_client.chat_json("hello") == ("{}", 0)
    assert calls == [{}]
    monkeypatch.setenv("LLM_URL", llm_client.DEFAULT_URL + "/")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm_client.chat_json("hello")
