"""Evaluation from the frontend: fake embedding, fake LLM, temporary result folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

import eval_routes
import main
from schemas import AskResult
from store import Store
from test_api import FakeEmbedding

KESTREL = Path(__file__).resolve().parents[2] / "docs" / "kestrel"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", Store(tmp_path / "data", FakeEmbedding()))
    monkeypatch.setattr(eval_routes, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(eval_routes, "LLM_PAUSE_SECONDS", 0)
    return TestClient(main.app)


def upload_kestrel(client):
    for f in sorted(KESTREL.glob("*.md")):
        client.post("/documents", files={"file": (f.name, f.read_bytes(), "text/markdown")})


def test_sets_report_uploaded_documents(client):
    sets = {s["name"]: s for s in client.get("/eval/sets").json()}
    assert sets["kestrel"]["n_questions"] == 12
    assert sets["kestrel"]["uploaded"] == 0
    upload_kestrel(client)
    sets = {s["name"]: s for s in client.get("/eval/sets").json()}
    assert sets["kestrel"]["uploaded"] == 5


def test_run_without_documents_is_a_clear_error(client):
    res = client.post("/eval/run", json={"set_name": "kestrel"})
    assert res.status_code == 400
    assert "docs/kestrel" in res.json()["detail"]


def test_unknown_set_and_bad_label(client):
    assert client.post("/eval/run", json={"set_name": "nope"}).status_code == 404
    assert client.post("/eval/run", json={"set_name": "kestrel", "label": "../x"}).status_code == 422


def test_run_retrieval_only_writes_a_result_file(client, tmp_path):
    upload_kestrel(client)
    res = client.post("/eval/run", json={"set_name": "kestrel", "label": "test"})
    assert res.status_code == 200
    body = res.json()
    assert set(body["summary"]["overall"]) >= {"n", "hit@1", "hit@10", "recall@5"}
    assert body["summary"]["overall"]["n"] == 10         # 2 unanswerable left out
    assert body["summary"]["n_unanswerable"] == 2
    assert "answer" not in body["rows"][0]                # retrieval only by default
    assert list((tmp_path / "results").glob("*-kestrel-test.json"))


def test_run_with_answers_uses_the_llm(client, monkeypatch):
    upload_kestrel(client)
    calls = []

    def fake_answer(question, chunks):
        calls.append(question)
        return AskResult(status="not_found", answer="", references=[], error=None)

    monkeypatch.setattr(eval_routes.llm, "answer_question", fake_answer)
    body = client.post("/eval/run", json={"set_name": "kestrel", "answers": True}).json()
    assert len(calls) == 12
    assert body["rows"][0]["answer"]["status"] == "not_found"
    assert body["rows"][0]["grade"] is None
