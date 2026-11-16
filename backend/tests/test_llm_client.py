import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import pytest

import llm_client
from llm_client import chat_json, strip_fences


def answer(content, tokens=42):
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": tokens}}


def fake_server(monkeypatch, responses):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append({"url": url, "body": dict(json), "headers": headers})
        status, data = responses[len(calls) - 1]
        return httpx.Response(status, json=data, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm_client.httpx, "post", fake_post)
    return calls


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ["LLM_URL", "LLM_API_KEY", "LLM_MODEL", "GOOGLE_API_KEY"]:
        monkeypatch.delenv(name, raising=False)


def test_default_gemini_request(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "abc")
    calls = fake_server(monkeypatch, [(200, answer('{"ok": true}'))])
    text, tokens = chat_json("hello")
    assert text == '{"ok": true}'
    assert tokens == 42
    call = calls[0]
    assert call["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer abc"
    assert call["body"]["model"] == "gemini-3.1-flash-lite-preview"
    assert call["body"]["temperature"] == 0
    assert call["body"]["response_format"] == {"type": "json_object"}
    assert call["body"]["messages"] == [{"role": "user", "content": "hello"}]


def test_other_server_from_env(monkeypatch):
    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1/")
    monkeypatch.setenv("LLM_API_KEY", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    calls = fake_server(monkeypatch, [(200, answer("{}"))])
    chat_json("hello")
    assert calls[0]["url"] == "http://localhost:11434/v1/chat/completions"
    assert calls[0]["body"]["model"] == "llama3.2"


def test_old_env_with_google_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "old-key")
    calls = fake_server(monkeypatch, [(200, answer("{}"))])
    chat_json("hello")
    assert calls[0]["headers"]["Authorization"] == "Bearer old-key"


def test_llm_key_wins_over_google_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "old-key")
    monkeypatch.setenv("LLM_API_KEY", "new-key")
    calls = fake_server(monkeypatch, [(200, answer("{}"))])
    chat_json("hello")
    assert calls[0]["headers"]["Authorization"] == "Bearer new-key"


def test_no_key(monkeypatch):
    calls = fake_server(monkeypatch, [])
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        chat_json("hello")
    assert calls == []


def test_retry_without_response_format(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "abc")
    calls = fake_server(monkeypatch, [(400, {"error": "response_format not supported"}), (200, answer("{}"))])
    text, tokens = chat_json("hello")
    assert text == "{}"
    assert len(calls) == 2
    assert "response_format" in calls[0]["body"]
    assert "response_format" not in calls[1]["body"]


def test_server_error_is_raised(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "abc")
    calls = fake_server(monkeypatch, [(500, {"error": "down"})])
    with pytest.raises(httpx.HTTPStatusError):
        chat_json("hello")
    assert len(calls) == 1


def test_wrong_key_is_not_retried(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "bad")
    calls = fake_server(monkeypatch, [(401, {"error": "unauthorized"})])
    with pytest.raises(httpx.HTTPStatusError):
        chat_json("hello")
    assert len(calls) == 1


def test_no_usage_means_zero_tokens(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "abc")
    fake_server(monkeypatch, [(200, {"choices": [{"message": {"content": "{}"}}]})])
    assert chat_json("hello") == ("{}", 0)


def test_strip_fences():
    assert strip_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences('```\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_fences('  {"a": 1}  ') == '{"a": 1}'


def test_fences_removed_from_answer(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "abc")
    fake_server(monkeypatch, [(200, answer('```json\n{"status": "not_found"}\n```'))])
    text, _ = chat_json("hello")
    assert text == '{"status": "not_found"}'