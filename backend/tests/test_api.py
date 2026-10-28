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
    monkeypatch.setattr(main, "store", Store(tmp_path, FakeEmbedding()))
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