"""Retrieval metrics. Pure functions: no HTTP, no LLM. Used by run_eval.py
(and can be imported by the backend to run the evaluation from the frontend).

A retrieved chunk is RELEVANT to an evidence item when it comes from the same
source file AND contains the quote (after normalizing case, quotes, dashes and
whitespace). Unanswerable questions have no evidence and are left out.
"""

import re

KS = (1, 3, 5, 10)


def normalize(text: str) -> str:
    for a, b in {"“": '"', "”": '"', "’": "'", "‘": "'", "–": "-", "—": "-"}.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).lower().strip()


def matches(chunk: dict, evidence: dict) -> bool:
    return chunk["filename"] == evidence["source"] and normalize(evidence["quote"]) in normalize(chunk["text"])


def score_question(question: dict, chunks: list[dict], ks=KS) -> dict:
    """chunks: retrieved chunks in rank order (at least max(ks) of them if available)."""
    evidence = question["evidence"]
    result = {"hit": {}, "recall": {}, "first_relevant_rank": None}
    if not evidence:
        return result
    for rank, chunk in enumerate(chunks, start=1):
        if any(matches(chunk, e) for e in evidence):
            result["first_relevant_rank"] = rank
            break
    for k in ks:
        top = chunks[:k]
        found = [any(matches(c, e) for c in top) for e in evidence]
        result["hit"][k] = any(found)                       # HitRate@k: at least one evidence in top k
        result["recall"][k] = round(sum(found) / len(found), 3)  # Recall@k: share of evidence in top k
    return result


def summarize(rows: list[dict], ks=KS) -> dict:
    """rows: [{"type":..., "answerable":..., "hit":{k:bool}, "recall":{k:float}}]"""
    answerable = [r for r in rows if r["answerable"]]

    def block(rs):
        if not rs:
            return None
        return {
            "n": len(rs),
            **{f"hit@{k}": round(sum(r["hit"][k] for r in rs) / len(rs), 3) for k in ks},
            **{f"recall@{k}": round(sum(r["recall"][k] for r in rs) / len(rs), 3) for k in ks},
        }

    by_type = {}
    for t in sorted({r["type"] for r in answerable}):
        by_type[t] = block([r for r in answerable if r["type"] == t])
    return {"overall": block(answerable), "by_type": by_type,
            "n_unanswerable": len(rows) - len(answerable)}
