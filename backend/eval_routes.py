"""Run the V2 retrieval evaluation from the frontend.

Same question sets, same relevance rule (eval/metrics.py) and same result
files as the CLI (eval/run_eval.py), but run in-process: no HTTP round trip.
"""

import json
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from metrics import KS, matches, score_question, summarize  # noqa: E402

import llm  # noqa: E402

SETS = {
    "kestrel": (ROOT / "eval/questions/kestrel.jsonl", ROOT / "docs/kestrel"),
    "courses": (ROOT / "eval/questions/courses.jsonl", ROOT / "docs/corpus"),
}
RESULTS = ROOT / "eval/results"
LLM_PAUSE_SECONDS = 1.0  # free Gemini tier: stay under the per-minute limit


class EvalRunRequest(BaseModel):
    set_name: str
    label: str = Field(default="ui", pattern=r"^[A-Za-z0-9._-]{1,40}$")
    answers: bool = False


def display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def make_eval_router(get_store: Callable) -> APIRouter:
    router = APIRouter(prefix="/eval")

    def corpus_docs(corpus_dir: Path) -> list:
        files = {p.name for p in corpus_dir.glob("*.md")}
        return [d for d in get_store().list_documents() if d.filename in files]

    @router.get("/sets")
    def list_sets():
        out = []
        for name, (qpath, corpus_dir) in SETS.items():
            if not qpath.exists():
                continue
            files = sorted(p.name for p in corpus_dir.glob("*.md"))
            out.append({"name": name, "n_questions": len(load_questions(qpath)),
                        "corpus_files": files, "uploaded": len(corpus_docs(corpus_dir))})
        return out

    @router.post("/run")
    def run(req: EvalRunRequest):
        if req.set_name not in SETS:
            raise HTTPException(404, f"Unknown question set: {req.set_name}")
        qpath, corpus_dir = SETS[req.set_name]
        docs = corpus_docs(corpus_dir)
        if not docs:
            raise HTTPException(
                400, f"No document of {display_path(corpus_dir)} is uploaded.")

        store = get_store()
        settings = store.get_settings()
        doc_ids = [d.id for d in docs]
        rows = []
        for q in load_questions(qpath):
            chunks = [c.model_dump()
                      for c in store.search(q["question"], doc_ids, max(KS))]
            row = {
                "id": q["id"], "type": q["type"], "answerable": q["answerable"],
                "question": q["question"], "expected_answer": q.get("expected_answer"),
                **score_question(q, chunks),
                "retrieved": [{"rank": i + 1, "chunk_id": c["chunk_id"], "filename": c["filename"],
                               "score": c["score"],
                               "relevant": any(matches(c, e) for e in q["evidence"])}
                              for i, c in enumerate(chunks)],
            }
            if req.answers:
                top = store.search(q["question"], doc_ids, settings.top_k)
                res = llm.answer_question(q["question"], top)
                row["answer"] = {"status": res.status, "text": res.answer or res.error,
                                 "references": [r.chunk_id for r in res.references]}
                # hand grading: correct | partial | wrong | unsupported
                row["grade"] = None
                row["grade_note"] = ""
                time.sleep(LLM_PAUSE_SECONDS)
            rows.append(row)

        summary = summarize(rows)
        RESULTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = RESULTS / f"{stamp}-{req.set_name}-{req.label}.json"
        out.write_text(json.dumps({
            "set": req.set_name, "label": req.label, "source": "ui",
            "date": datetime.now().isoformat(timespec="seconds"),
            "settings": settings.model_dump(), "documents": [d.filename for d in docs],
            "with_answers": req.answers, "summary": summary, "rows": rows,
        }, indent=2, ensure_ascii=False), "utf-8")

        # json round trip: integer k keys become strings, as in the saved file
        return json.loads(json.dumps({
            "file": display_path(out),
            "settings": settings.model_dump(), "summary": summary,
            "rows": [{k: v for k, v in r.items() if k != "retrieved"} for r in rows],
        }))

    return router
