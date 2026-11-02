"""No-context test: ask every question to the LLM WITHOUT retrieval.

If the model answers correctly anyway, the question tests the model's training,
not our RAG. Flag those questions by hand in the output file
("known_without_rag": true/false), then decide: replace or keep and say so.

Usage (from the repo root, with the backend venv active):
    python eval/no_context.py --set kestrel
    python eval/no_context.py --set courses

Uses the same key and model as the backend (backend/.env).
"""

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parent.parent
SETS = {"kestrel": ROOT / "eval/questions/kestrel.jsonl",
        "courses": ROOT / "eval/questions/courses.jsonl"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=SETS, required=True)
    args = p.parse_args()

    load_dotenv(ROOT / "backend/.env")
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

    questions = [json.loads(l) for l in SETS[args.set].read_text("utf-8").splitlines() if l.strip()]
    rows = []
    for q in questions:
        try:
            res = client.models.generate_content(
                model=model,
                contents="Answer briefly. If you do not know, say \"I don't know\".\n\n"
                         f"Question: {q['question']}")
            answer = (res.text or "").strip()
        except Exception as e:  # rate limit, network...
            answer = f"ERROR: {e}"
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"],
                     "expected_answer": q.get("expected_answer"),
                     "no_context_answer": answer,
                     "known_without_rag": None})  # fill in by hand: true / false
        print(f"\n[{q['id']}] {q['question']}\n  expected: {q.get('expected_answer')}\n  model:    {answer[:300]}")
        time.sleep(1)  # be gentle with the free tier

    out = ROOT / "eval/results" / f"{datetime.now():%Y%m%d-%H%M%S}-{args.set}-no-context.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"set": args.set, "model": model, "rows": rows},
                              indent=2, ensure_ascii=False), "utf-8")
    print(f"\nSaved to {out.relative_to(ROOT)}. Now set known_without_rag by hand.")


if __name__ == "__main__":
    main()
