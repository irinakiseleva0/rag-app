import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from chromadb import EmbeddingFunction
from fastapi.testclient import TestClient

import llm
import main
from chunking import split_text
from store import Store

WORDS = ["docker", "git", "firewall", "cors", "kubernetes", "python", "branch", "commit"]

DOC = "Git is a version control tool. A branch is a line of work. " * 20
DOC += "Docker runs containers. Docker images are built from a Dockerfile. " * 20


class FakeEmbedding(EmbeddingFunction):
    def __init__(self):
        pass

    def __call__(self, input):
        vectors = []
        for text in input:
            vectors.append([text.lower().count(w) + 0.01 for w in WORDS])
        return vectors

    @staticmethod
    def name():
        return "fake"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return FakeEmbedding()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Every test gets its own data folder: never touch backend/data (real graphs and traces).
    from doc_graphs import DocGraphs
    from graph_retriever import GraphRetriever
    from tracing import Tracer

    store = Store(tmp_path, FakeEmbedding())
    tracer = Tracer(tmp_path / "traces.sqlite3")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "tracer", tracer)
    monkeypatch.setattr(main, "doc_graphs", DocGraphs(tmp_path / "graphs", store, tracer, None))
    monkeypatch.setattr(main, "graph", GraphRetriever.from_graphs([], store))
    return TestClient(main.app)


def upload(client, name, content):
    return client.post("/documents", files={"file": (name, content, "text/plain")})


def fake_gemini(monkeypatch, output):
    def fake_llm(prompt):
        if isinstance(output, Exception):
            raise output
        context = prompt.split("Context:")[1]
        first_id = context.split("[")[1].split("]")[0]
        return output.replace("FIRST_ID", first_id)

    def fake_answer(question, chunks):
        return llm.answer_question(question, chunks, llm=fake_llm)

    monkeypatch.setattr(main, "answer_question", fake_answer)


def ask(client, doc_id):
    body = {"question": "docker?", "doc_ids": [doc_id], "top_k": 3}
    return client.post("/ask", json=body).json()


def test_chunks_match_text():
    text = "abcdefghij" * 50
    chunks = split_text(text, 100, 20)
    for c in chunks:
        assert text[c["start"]:c["end"]] == c["text"]


def test_overlap():
    chunks = split_text("x" * 1000, 100, 10)
    assert chunks[1]["start"] == 90


def test_upload_list_delete(client):
    r = upload(client, "git.md", DOC.encode())
    assert r.status_code == 200
    doc = r.json()
    assert doc["n_chunks"] > 1

    docs = client.get("/documents").json()
    assert len(docs) == 1

    r = client.delete("/documents/" + doc["id"])
    assert r.json() == {"deleted": True}
    assert client.get("/documents").json() == []


def test_upload_wrong_extension(client):
    r = upload(client, "notes.pdf", b"hello")
    assert r.status_code == 400


def test_upload_empty(client):
    r = upload(client, "empty.txt", b"   ")
    assert r.status_code == 400


def test_upload_not_utf8(client):
    r = upload(client, "bad.txt", b"\xff\xfe\x00bad")
    assert r.status_code == 400


def test_upload_too_big(client):
    r = upload(client, "big.txt", b"a" * (3 * 1024 * 1024))
    assert r.status_code == 413


def test_delete_unknown(client):
    r = client.delete("/documents/nope")
    assert r.status_code == 404


def test_settings_reindex(client):
    doc = upload(client, "git.md", DOC.encode()).json()
    settings = client.get("/settings").json()
    settings["chunk_size"] = 200
    r = client.put("/settings", json=settings)
    assert r.status_code == 200
    new_doc = client.get("/documents").json()[0]
    assert new_doc["n_chunks"] > doc["n_chunks"]


def test_invalid_settings(client):
    r = client.put("/settings", json={"chunk_size": 0, "overlap_percent": 10, "top_k": 5})
    assert r.status_code == 422
    assert type(r.json()["detail"]) == str


def test_retrieve(client):
    doc = upload(client, "devops.md", DOC.encode()).json()
    body = {"question": "docker containers", "doc_ids": [doc["id"]], "top_k": 3}
    chunks = client.post("/retrieve", json=body).json()["chunks"]
    assert len(chunks) == 3
    for c in chunks:
        assert DOC[c["char_start"]:c["char_end"]] == c["text"]
    assert "docker" in chunks[0]["text"].lower()


def test_retrieve_unknown_doc(client):
    body = {"question": "x", "doc_ids": ["nope"], "top_k": 3}
    r = client.post("/retrieve", json=body)
    assert r.status_code == 404


def test_ask_answered(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Docker runs containers.", "used_chunk_ids": ["FIRST_ID"]}')
    r = ask(client, doc["id"])
    assert r["status"] == "answered"
    assert len(r["references"]) == 1


def test_ask_cites_unknown_chunk(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "ok", "used_chunk_ids": ["FIRST_ID", "fake#0001"]}')
    r = ask(client, doc["id"])
    assert r["status"] == "error"


def test_ask_no_citation(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "ok", "used_chunk_ids": []}')
    r = ask(client, doc["id"])
    assert r["status"] == "error"


def test_ask_empty_answer(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "  ", "used_chunk_ids": ["FIRST_ID"]}')
    r = ask(client, doc["id"])
    assert r["status"] == "error"


def test_ask_not_found(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, '{"status": "not_found", "answer": "", "used_chunk_ids": []}')
    r = ask(client, doc["id"])
    assert r["status"] == "not_found"
    assert r["references"] == []


def test_ask_invalid_json(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, "not json at all")
    r = ask(client, doc["id"])
    assert r["status"] == "error"


def test_ask_gemini_down(client, monkeypatch):
    doc = upload(client, "devops.md", DOC.encode()).json()
    fake_gemini(monkeypatch, RuntimeError("quota exceeded"))
    r = ask(client, doc["id"])
    assert r["status"] == "error"


def test_internal_error_is_hidden(client, monkeypatch):
    def broken():
        raise RuntimeError("secret details")

    monkeypatch.setattr(main.store, "list_documents", broken)
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.get("/documents")
    assert r.status_code == 500
    assert "secret" not in r.json()["detail"]

def test_retrieve_dense_and_bm25(client):
    doc_id = upload(client, "a.md", DOC).json()["id"]
    body = {"question": "docker images", "doc_ids": [doc_id], "top_k": 3,
            "retrievers": {"dense": True, "bm25": True, "graph": False}}
    res = client.post("/retrieve", json=body).json()
    assert len(res["chunks"]) == 3
    assert res["graph_path"] is None
    names = {f["retriever"] for c in res["chunks"] for f in c["found_by"]}
    assert names == {"dense", "bm25"}


def test_retrieve_needs_one_retriever(client):
    body = {"question": "docker", "top_k": 3, "retrievers": {"dense": False, "bm25": False, "graph": False}}
    assert client.post("/retrieve", json=body).status_code == 400


def test_graph_not_built(client, monkeypatch):
    monkeypatch.setattr(main, "graph", None)
    body = {"question": "docker", "top_k": 3, "retrievers": {"dense": True, "graph": True}}
    assert client.post("/retrieve", json=body).status_code == 400


def test_ask_reports_cost(client, monkeypatch):
    doc_id = upload(client, "a.md", DOC).json()["id"]
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Containers.", "used_chunk_ids": ["FIRST_ID"]}')
    res = ask(client, doc_id)
    assert res["cost"]["llm_calls"] == 1


def test_ask_sends_redacted_question_to_llm(client, monkeypatch, tmp_path):
    from tracing import Tracer

    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    doc_id = upload(client, "a.md", DOC).json()["id"]
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Containers.", "used_chunk_ids": ["FIRST_ID"]}')
    fake_answer = main.answer_question
    questions = []

    def record_answer(question, chunks):
        questions.append(question)
        return fake_answer(question, chunks)

    monkeypatch.setattr(main, "answer_question", record_answer)
    response = client.post("/ask", json={
        "question": "Contact jane.doe@example.com or Inès Moreau about docker",
        "doc_ids": [doc_id], "top_k": 3,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert len(questions) == 1
    assert "[EMAIL_" in questions[0]
    assert "[NAME_" in questions[0]
    assert "jane.doe@example.com" not in questions[0]
    assert "Inès" not in questions[0]


@pytest.mark.parametrize("endpoint", ["/ask", "/retrieve"])
def test_question_trace_stores_redacted_question(client, monkeypatch, tmp_path, endpoint):
    from tracing import Tracer

    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    doc_id = upload(client, "a.md", DOC).json()["id"]
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Containers.", "used_chunk_ids": ["FIRST_ID"]}')
    response = client.post(endpoint, json={
        "question": "Contact jane.doe@example.com or Inès Moreau about docker",
        "doc_ids": [doc_id], "top_k": 3,
    })
    assert response.status_code == 200
    trace_response = client.get("/traces/" + response.json()["trace_id"])
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert "jane.doe@example.com" not in trace["input"]["question"]
    assert "Inès" not in trace["input"]["question"]
    assert ("[EMAIL_" if endpoint == "/ask" else "[EMAIL]") in trace["input"]["question"]
    assert ("[NAME_" if endpoint == "/ask" else "[NAME]") in trace["input"]["question"]
    assert trace["input"]["redactions"] >= 2
    if endpoint == "/ask":
        llm_span = next(span for span in trace["spans"] if span["name"] == "llm")
        assert llm_span["attributes"]["redactions_question"] == trace["input"]["redactions"]
        assert llm_span["attributes"]["redactions_chunks"] == 0


@pytest.mark.parametrize("endpoint", ["/ask", "/retrieve"])
def test_retrieval_keeps_original_question(client, monkeypatch, tmp_path, endpoint):
    from tracing import Tracer

    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    doc_id = upload(client, "a.md", DOC).json()["id"]
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Containers.", "used_chunk_ids": ["FIRST_ID"]}')
    original = "Contact jane.doe@example.com or Inès Moreau about docker"
    search = main.hybrid_search
    questions = []

    def record_search(store, req, graph=None, trace=None):
        questions.append(req.question)
        return search(store, req, graph, trace=trace)

    monkeypatch.setattr(main, "hybrid_search", record_search)
    response = client.post(endpoint, json={"question": original, "doc_ids": [doc_id], "top_k": 3})
    assert response.status_code == 200
    assert questions == [original]


def test_ask_redacts_question_and_chunk_copies(client, monkeypatch, tmp_path):
    from tracing import Tracer

    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    document = "Lead: Inès Moreau, inès@example.com, docker"
    doc_id = upload(client, "lead.md", document.encode("utf-8")).json()["id"]
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Containers.", "used_chunk_ids": ["FIRST_ID"]}')
    fake_answer = main.answer_question
    received = []
    retrieved = []
    search = main.hybrid_search

    def record_search(store, req, graph=None, trace=None):
        result = search(store, req, graph, trace=trace)
        retrieved.extend(result[0])
        return result

    def record_answer(question, chunks):
        received.append((question, chunks))
        return fake_answer(question, chunks)

    monkeypatch.setattr(main, "hybrid_search", record_search)
    monkeypatch.setattr(main, "answer_question", record_answer)
    response = client.post("/ask", json={
        "question": "Contact jane.doe@example.com about docker",
        "doc_ids": [doc_id], "top_k": 3,
    })
    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert len(received) == 1
    question, chunks = received[0]
    assert chunks
    assert "@example.com" not in question
    assert "Inès" not in question
    assert "[EMAIL_" in question
    for original, redacted in zip(retrieved, chunks):
        assert original is not redacted
        assert original.text == document
        assert "Inès" not in redacted.text
        assert "[NAME_" in redacted.text
        assert "@example.com" not in redacted.text


def test_ask_returns_original_references_after_redaction(client, monkeypatch, tmp_path):
    from tracing import Tracer

    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    document = "Lead: Inès Moreau, inès@example.com, docker"
    doc_id = upload(client, "lead.md", document.encode("utf-8")).json()["id"]
    fake_gemini(monkeypatch, '{"status": "answered", "answer": "Containers.", "used_chunk_ids": ["FIRST_ID"]}')
    originals = {}
    search = main.hybrid_search

    def record_search(store, req, graph=None, trace=None):
        result = search(store, req, graph, trace=trace)
        originals.update({chunk.chunk_id: chunk.model_dump() for chunk in result[0]})
        return result

    monkeypatch.setattr(main, "hybrid_search", record_search)
    response = client.post("/ask", json={
        "question": "Contact jane.doe@example.com about docker",
        "doc_ids": [doc_id], "top_k": 3,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "answered"
    assert result["references"]
    for reference in result["references"]:
        assert reference == originals[reference["chunk_id"]]
        assert reference["text"] == document
        assert "Inès" in reference["text"]
        assert reference["found_by"]
        assert reference["rrf_score"] is not None
    trace_response = client.get("/traces/" + result["trace_id"])
    assert trace_response.status_code == 200
    trace = trace_response.json()
    assert "jane.doe@example.com" not in trace["input"]["question"]
    assert trace["input"]["redactions"] >= 1
    llm_span = next(span for span in trace["spans"] if span["name"] == "llm")
    assert llm_span["attributes"]["redactions_question"] == trace["input"]["redactions"]
    assert llm_span["attributes"]["redactions_chunks"] >= 1


@pytest.mark.parametrize("raw_answer, expected_answer, restored", [
    ("led by [NAME_1]", "led by Omar Haddad", 1),
    ("[NAME_1], [NAME_1]: [EMAIL_1]; ask [NAME_9]",
     "Omar Haddad, Omar Haddad: omar@example.com; ask [NAME_9]", 2),
    ("Ask [NAME_9]", "Ask [NAME_9]", 0),
])
def test_ask_restores_answer_locally_and_keeps_trace_private(
        client, monkeypatch, tmp_path, raw_answer, expected_answer, restored):
    import json
    from tracing import Tracer

    monkeypatch.setattr(main, "tracer", Tracer(tmp_path / "traces.sqlite3"))
    document = "Omar Haddad leads Payments. Contact omar@example.com."
    doc_id = upload(client, "payments.md", document.encode("utf-8")).json()["id"]
    prompts = []

    def fake_llm(prompt):
        prompts.append(prompt)
        context = prompt.split("Context:", 1)[1]
        chunk_id = context.split("[", 1)[1].split("]", 1)[0]
        return json.dumps({"status": "answered", "answer": raw_answer,
                           "used_chunk_ids": [chunk_id]})

    def fake_answer(question, chunks):
        return llm.answer_question(question, chunks, llm=fake_llm)

    monkeypatch.setattr(main, "answer_question", fake_answer)
    response = client.post("/ask", json={
        "question": "Does Omar Haddad lead Payments? Contact omar@example.com.",
        "doc_ids": [doc_id], "top_k": 3,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "answered"
    assert result["answer"] == expected_answer
    assert result["references"][0]["text"] == document
    assert len(prompts) == 1
    assert "Omar" not in prompts[0]
    assert "omar@example.com" not in prompts[0]
    context, question = prompts[0].split("Context:", 1)[1].split("Question:", 1)
    assert "[NAME_1]" in context and "[NAME_1]" in question
    assert "[EMAIL_1]" in context and "[EMAIL_1]" in question
    trace = client.get("/traces/" + result["trace_id"]).json()
    assert "[NAME_1]" in trace["input"]["question"]
    assert "[EMAIL_1]" in trace["input"]["question"]
    assert "Omar" not in json.dumps(trace)
    assert "omar@example.com" not in json.dumps(trace)
    assert "mapping" not in json.dumps(trace)
    span = next(span for span in trace["spans"] if span["name"] == "llm")
    assert span["attributes"]["restored"] == restored
