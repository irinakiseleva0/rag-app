"""Words analytics: tokenizer rules and the three endpoints (fake embedding)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

import main
from store import Store
from test_api import FakeEmbedding
from words import tokenize

KESTREL = Path(__file__).resolve().parents[2] / "docs" / "kestrel"


def test_tokenize_keeps_identifiers_whole():
    assert tokenize("Error KST-2044: add 203.0.113.10 now.") == ["error", "kst-2044", "add", "203.0.113.10", "now"]
    assert tokenize("category technical_bug") == ["category", "technical_bug"]
    assert tokenize("I can’t log in!") == ["i", "can't", "log", "in"]
    assert tokenize("Inès Moreau") == ["inès", "moreau"]
    assert tokenize("  -- ... ") == []


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", Store(tmp_path, FakeEmbedding()))
    return TestClient(main.app)


def upload(client, name, text):
    return client.post("/documents", files={"file": (name, text.encode(), "text/plain")}).json()


def test_vocabulary_counts_words_and_chunks(client):
    doc = upload(client, "a.txt", "Docker docker DOCKER git. " * 3)
    body = client.post("/words/vocabulary", json={"doc_ids": [doc["id"]]}).json()
    words = {w["word"]: w for w in body["words"]}
    assert words["docker"]["count"] == 9
    assert words["git"]["count"] == 3
    assert words["docker"]["n_chunks"] == body["n_chunks"] == 1
    assert body["words"][0]["word"] == "docker"          # sorted by count


def test_word_lists_chunks_with_counts(client):
    doc = upload(client, "a.txt", "alpha " * 300 + "beta " * 300)   # several chunks
    body = client.post("/words/word", json={"word": "Beta", "doc_ids": [doc["id"]]}).json()
    assert body["word"] == "beta"
    # Counts are per chunk: with overlap, a word in the shared part is counted twice.
    assert body["count"] >= 300
    assert body["n_chunks"] >= 2
    assert all("text" in c for c in body["chunks"])


def test_word_must_be_one_word(client):
    assert client.post("/words/word", json={"word": "two words"}).status_code == 400


def test_unknown_document(client):
    assert client.post("/words/vocabulary", json={"doc_ids": ["nope"]}).status_code == 404


def test_question_mode_on_kestrel_finds_missing_words_and_answer_chunks(client):
    ids = [upload(client, f.name, f.read_text("utf-8"))["id"] for f in sorted(KESTREL.glob("*.md"))]
    body = client.post("/words/question",
                       json={"doc_ids": ids, "set_name": "kestrel", "question_id": "q05"}).json()
    # "I lost my phone and I can't log in anymore": the docs never say "phone".
    assert "phone" in body["missing"]
    assert body["answer_chunks"]                           # evidence chunks found
    lost = next(t for t in body["tokens"] if t["word"] == "lost")
    assert lost["in_answer_chunks"] <= lost["n_chunks"]


def test_question_needs_text(client):
    assert client.post("/words/question", json={"question": "  "}).status_code == 400


def test_questions_list_both_sets(client):
    sets = {q["set_name"] for q in client.get("/words/questions").json()}
    assert {"kestrel", "courses"} <= sets
