import os
import re

import httpx

DEFAULT_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"


def get_url():
    return (os.getenv("LLM_URL") or DEFAULT_URL).rstrip("/")


def get_model():
    return os.getenv("LLM_MODEL") or DEFAULT_MODEL


def get_key():
    return os.getenv("LLM_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text)
        text = re.sub(r"```$", "", text)
    return text.strip()


def chat_json(prompt, timeout=60):
    key = get_key()
    if not key:
        raise RuntimeError("LLM_API_KEY is not set in backend/.env")

    url = get_url() + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}"}
    body = {
        "model": get_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    response = httpx.post(url, json=body, headers=headers, timeout=timeout)
    if response.status_code in (400, 422):
        del body["response_format"]
        response = httpx.post(url, json=body, headers=headers, timeout=timeout)
    response.raise_for_status()

    data = response.json()
    text = data["choices"][0]["message"]["content"] or ""
    usage = data.get("usage") or {}
    tokens = usage.get("total_tokens") or 0
    return strip_fences(text), tokens