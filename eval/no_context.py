"""No-context test: ask every question to the LLM WITHOUT retrieval.

If the model answers correctly anyway, the question tests the model's training,
not our RAG. Flag those questions by hand in the output file
("known_without_rag": true/false), then decide: replace or keep and say so.

Usage (from the repo root, with the backend venv active):
    python eval/no_context.py --set kestrel
    python eval/no_context.py --set courses
    python eval/no_context.py --set courses --resume eval/results/<file>-courses-no-context.json

--resume reuses the answers already obtained in a previous file (and your
known_without_rag flags); only questions that failed (ERROR) are asked again.
Free tier: --sleep (default 6 s) keeps us under the per-minute limit, and a
429 is retried after a pause.

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
PROMPT = "Answer briefly. If you do not know, say \"I don't know\".\n\nQuestion: {q}"


def ask(client, model: str, question: str, retries: int = 3) -> str:
    for attempt in range(retries + 1):
        try:
            res = client.models.generate_content(model=model, contents=PROMPT.format(q=question))
            return (res.text or "").strip()
        except Exception as e:  # rate limit, network...
            if "429" in str(e) and attempt < retries:
                wait = 30 * (attempt + 1)
                print(f"  429 rate limit, waiting {wait} s...")
                time.sleep(wait)
                continue
            return f"ERROR: {str(e)[:200]}"
    return "ERROR: retries exhausted"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=SETS, required=True)
    p.add_argument("--resume", help="previous no-context result file to complete")
    p.add_argument("--sleep", type=float, default=6.0, help="seconds between calls")
    args = p.parse_args()

    load_dotenv(ROOT / "backend/.env")
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

    previous = {}
    if args.resume:
        old = json.loads(Path(args.resume).read_text("utf-8"))
        previous = {r["id"]: r for r in old["rows"]
                    if not str(r.get("no_context_answer", "")).startswith("ERROR")}
        print(f"Resuming: {len(previous)} answers reused.")

    questions = [json.loads(l) for l in SETS[args.set].read_text("utf-8").splitlines() if l.strip()]
    rows = []
    for q in questions:
        if q["id"] in previous:
            rows.append(previous[q["id"]])
            continue
        answer = ask(client, model, q["question"])
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"],
                     "expected_answer": q.get("expected_answer"),
                     "no_context_answer": answer,
                     "known_without_rag": None})  # fill in by hand: true / false
        print(f"\n[{q['id']}] {q['question']}\n  expected: {q.get('expected_answer')}\n  model:    {answer[:300]}")
        time.sleep(args.sleep)

    errors = sum(str(r["no_context_answer"]).startswith("ERROR") for r in rows)
    out = ROOT / "eval/results" / f"{datetime.now():%Y%m%d-%H%M%S}-{args.set}-no-context.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"set": args.set, "model": model, "rows": rows},
                              indent=2, ensure_ascii=False), "utf-8")
    print(f"\nSaved to {out.relative_to(ROOT)}. Errors: {errors}. Now set known_without_rag by hand.")
    if errors:
        print(f"Run again later with: --resume {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
