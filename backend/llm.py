import logging

from pydantic import ValidationError

from llm_client import chat_json
from schemas import AskResult, Cost, LLMAnswer

logger = logging.getLogger("rag")

PROMPT = """You answer questions using ONLY the context chunks below.
Each chunk starts with its id in square brackets.

Rules:
- If the chunks contain the answer: status = "answered", write a short answer,
  and list in used_chunk_ids the ids of the chunks you used.
- If the chunks do not contain the answer: status = "not_found", answer = "",
  used_chunk_ids = []. Never use outside knowledge.

Return only a JSON object with these 3 keys, nothing else:
{{"status": "answered" or "not_found", "answer": "your short answer", "used_chunk_ids": ["id1", "id2"]}}

Context:
{context}

Question: {question}
"""


def error(message):
    return AskResult(status="error", answer="", references=[], error=message)


def answer_question(question, chunks, llm=chat_json):
    if len(chunks) == 0:
        return AskResult(status="not_found", answer="", references=[], error=None)

    context = ""
    for c in chunks:
        context += f"[{c.chunk_id}]\n{c.text}\n\n"
    prompt = PROMPT.format(context=context, question=question)

    try:
        raw = llm(prompt)
    except Exception:
        logger.exception("LLM call failed")
        return error("The LLM call failed (server unavailable, wrong key or quota exceeded).")

    tokens = 0
    if isinstance(raw, tuple):
        raw, tokens = raw
    cost = Cost(llm_calls=1, tokens=tokens)

    try:
        parsed = LLMAnswer.model_validate_json(raw)
    except ValidationError:
        return error("The model returned an invalid answer (not the expected JSON).")

    if parsed.status == "not_found":
        return AskResult(status="not_found", answer="", references=[], error=None, cost=cost)

    if parsed.answer.strip() == "":
        return error("The model said it answered but the answer is empty.")

    if len(parsed.used_chunk_ids) == 0:
        return error("The model did not cite any chunk.")

    retrieved_ids = [c.chunk_id for c in chunks]
    for chunk_id in parsed.used_chunk_ids:
        if chunk_id not in retrieved_ids:
            return error("The model cited chunks that were not retrieved.")

    used = []
    for c in chunks:
        if c.chunk_id in parsed.used_chunk_ids:
            used.append(c)

    return AskResult(status="answered", answer=parsed.answer, references=used, error=None, cost=cost)