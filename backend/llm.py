import os

from google import genai
from google.genai import types
from pydantic import ValidationError

from schemas import AskResult, LLMAnswer

PROMPT = """You answer questions using ONLY the context chunks below.
Each chunk starts with its id in square brackets.

Rules:
- If the chunks contain the answer: status = "answered", write a short answer,
  and list in used_chunk_ids the ids of the chunks you used.
- If the chunks do not contain the answer: status = "not_found", answer = "",
  used_chunk_ids = []. Never use outside knowledge.

Context:
{context}

Question: {question}
"""


def call_gemini(prompt):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in backend/.env")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=LLMAnswer,
        ),
    )
    return response.text or ""


def answer_question(question, chunks, llm=call_gemini):
    if len(chunks) == 0:
        return AskResult(status="not_found", answer="", references=[], error=None)

    context = ""
    for c in chunks:
        context += f"[{c.chunk_id}]\n{c.text}\n\n"
    prompt = PROMPT.format(context=context, question=question)

    try:
        raw = llm(prompt)
    except Exception as e:
        return AskResult(status="error", answer="", references=[], error=f"LLM call failed: {e}")

    try:
        parsed = LLMAnswer.model_validate_json(raw)
    except ValidationError:
        return AskResult(
            status="error",
            answer="",
            references=[],
            error="The model returned an invalid answer (not the expected JSON).",
        )

    if parsed.status == "not_found":
        return AskResult(status="not_found", answer="", references=[], error=None)

    used = []
    for c in chunks:
        if c.chunk_id in parsed.used_chunk_ids:
            used.append(c)
    if len(used) == 0:
        used = chunks

    return AskResult(status="answered", answer=parsed.answer, references=used, error=None)