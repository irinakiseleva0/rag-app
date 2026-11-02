"""Words tab: corpus mode (vocabulary, word -> chunks) and question mode
(question -> which words exist, in which chunks, and which do not exist).

The index is built from the chunks currently stored in ChromaDB, so it follows
the chunk size / overlap settings. It is rebuilt on each request: the corpora
are small (a few hundred chunks), so this stays fast and never goes stale.
"""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from eval_routes import SETS, load_questions
from metrics import matches
from words import STOP_WORDS, WordIndex, tokenize, unique_in_order


class DocsRequest(BaseModel):
    doc_ids: list[str] = []


class WordRequest(DocsRequest):
    word: str = Field(min_length=1, max_length=100)


class QuestionWordsRequest(DocsRequest):
    question: str = Field(default="", max_length=2000)
    set_name: str | None = None
    question_id: str | None = None


def make_words_router(get_store: Callable) -> APIRouter:
    router = APIRouter(prefix="/words")

    def load_chunks(doc_ids: list[str]) -> list[dict]:
        store = get_store()
        known = {d.id for d in store.list_documents()}
        unknown = [d for d in doc_ids if d not in known]
        if unknown:
            raise HTTPException(404, f"Unknown document id: {unknown[0]}")
        where = {"doc_id": {"$in": doc_ids}} if doc_ids else None
        got = store.collection.get(where=where, include=["documents", "metadatas"])
        return [{"chunk_id": cid, "filename": m["filename"], "chunk_index": m["chunk_index"], "text": t}
                for cid, t, m in zip(got["ids"], got["documents"], got["metadatas"])]

    @router.get("/questions")
    def list_questions():
        out = []
        for name, (qpath, _) in SETS.items():
            if qpath.exists():
                out += [{"set_name": name, "id": q["id"], "type": q["type"], "question": q["question"]}
                        for q in load_questions(qpath)]
        return out

    @router.post("/vocabulary")
    def vocabulary(req: DocsRequest):
        chunks = load_chunks(req.doc_ids)
        index = WordIndex(chunks)
        words = index.vocabulary()
        return {"n_chunks": len(chunks), "n_tokens": sum(w["count"] for w in words),
                "n_distinct": len(words), "words": words}

    @router.post("/word")
    def word(req: WordRequest):
        tokens = tokenize(req.word)
        if len(tokens) != 1:
            raise HTTPException(400, "Type one word (no spaces).")
        w = tokens[0]
        index = WordIndex(load_chunks(req.doc_ids))
        return {"word": w, "stop": w in STOP_WORDS, "count": index.count(w),
                "n_chunks": index.n_chunks(w), "chunks": index.chunks_for(w, with_text=True)}

    @router.post("/question")
    def question(req: QuestionWordsRequest):
        text, evidence = req.question, []
        if req.set_name and req.question_id:
            if req.set_name not in SETS:
                raise HTTPException(404, f"Unknown question set: {req.set_name}")
            q = next((q for q in load_questions(SETS[req.set_name][0]) if q["id"] == req.question_id), None)
            if q is None:
                raise HTTPException(404, f"Unknown question: {req.question_id}")
            text, evidence = q["question"], q["evidence"]
        if not text.strip():
            raise HTTPException(400, "Type a question or pick one from a question set.")

        chunks = load_chunks(req.doc_ids)
        index = WordIndex(chunks)
        # Chunks that hold the answer: same rule as the evaluation (source + quote).
        answer_ids = {c["chunk_id"] for c in chunks if any(matches(c, e) for e in evidence)}

        tokens = []
        for w in unique_in_order(tokenize(text)):
            found = index.chunks_for(w, answer_ids)
            tokens.append({"word": w, "stop": w in STOP_WORDS, "count": index.count(w),
                           "n_chunks": len(found),
                           "in_answer_chunks": sum(c["is_answer"] for c in found),
                           "chunks": found})
        return {
            "question": text,
            "n_chunks": len(chunks),
            "answerable": bool(evidence) if req.question_id else None,
            "answer_chunks": [{"chunk_id": c["chunk_id"], "filename": c["filename"],
                               "chunk_index": c["chunk_index"]}
                              for c in chunks if c["chunk_id"] in answer_ids],
            "tokens": tokens,
            "missing": [t["word"] for t in tokens if t["count"] == 0],
        }

    return router
