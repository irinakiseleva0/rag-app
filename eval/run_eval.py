"""RAG V2 evaluation: retrieval quality on a question set, optional answers.

Usage (backend running, both corpora uploaded):
    python eval/run_eval.py --set kestrel --label c800-o10
    python eval/run_eval.py --set courses --label c800-o10
    python eval/run_eval.py --set kestrel --label c800-o10 --answers   # also calls /ask (LLM)
    python eval/run_eval.py --set kestrel --check-only                  # quotes exist in the corpus?

--set kestrel -> eval/questions/kestrel.jsonl, documents from docs/kestrel/
--set courses -> eval/questions/courses.jsonl, documents from docs/corpus/
Only the documents of that corpus are searched (doc_ids filtered by filename).

Standard library only.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics import KS, matches, normalize, score_question, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "kestrel": (ROOT / "eval/questions/kestrel.jsonl", ROOT / "docs/kestrel"),
    "courses": (ROOT / "eval/questions/courses.jsonl", ROOT / "docs/corpus"),
}
RESULTS = ROOT / "eval/results"


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def http(api: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} failed: HTTP {e.code} {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Cannot reach the backend at {api}: {e.reason}")


def check_only(questions, corpus_dir: Path) -> int:
    files = {p.name: normalize(p.read_text("utf-8")) for p in corpus_dir.glob("*.md")}
    missing = 0
    for q in questions:
        for e in q["evidence"]:
            ok = e["source"] in files and normalize(e["quote"]) in files[e["source"]]
            missing += not ok
            print(f"{'ok ' if ok else 'MISSING'} {q['id']}: {e['source']} | {e['quote']!r}")
    print(f"\n{missing} quote(s) not found.")
    return 1 if missing else 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=SETS, required=True)
    p.add_argument("--label", default="run", help="configuration name, e.g. c800-o10")
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--answers", action="store_true", help="also generate answers with /ask (uses the LLM)")
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args()

    qpath, corpus_dir = SETS[args.set]
    questions = load_questions(qpath)
    if args.check_only:
        sys.exit(check_only(questions, corpus_dir))

    api = args.api.rstrip("/")
    settings = http(api, "GET", "/settings")
    corpus_files = {p.name for p in corpus_dir.glob("*.md")}
    docs = [d for d in http(api, "GET", "/documents") if d["filename"] in corpus_files]
    if not docs:
        raise SystemExit(f"None of the files in {corpus_dir} is uploaded.")
    doc_ids = [d["id"] for d in docs]
    kmax = max(KS)

    rows = []
    for q in questions:
        chunks = http(api, "POST", "/retrieve",
                      {"question": q["question"], "doc_ids": doc_ids, "top_k": kmax})["chunks"]
        s = score_question(q, chunks)
        row = {
            "id": q["id"], "type": q["type"], "answerable": q["answerable"],
            "question": q["question"], "expected_answer": q.get("expected_answer"),
            **s,
            "retrieved": [{"rank": i + 1, "chunk_id": c["chunk_id"], "filename": c["filename"],
                           "score": c["score"],
                           "relevant": any(matches(c, e) for e in q["evidence"])}
                          for i, c in enumerate(chunks)],
        }
        if args.answers:
            res = http(api, "POST", "/ask",
                       {"question": q["question"], "doc_ids": doc_ids, "top_k": settings["top_k"]})
            row["answer"] = {"status": res["status"], "text": res["answer"] or res.get("error"),
                             "references": [r["chunk_id"] for r in res["references"]]}
            # Hand grading: correct | partial | wrong | unsupported. Fill in by hand.
            row["grade"] = None
            row["grade_note"] = ""
        rows.append(row)
        hits = " ".join(f"@{k}={'Y' if s['hit'].get(k) else '-'}" for k in KS) if q["answerable"] else "(unanswerable)"
        print(f"{q['id']:4} {q['type']:17} {hits}  {q['question'][:55]}")

    summary = summarize(rows)
    print_table(summary)

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{stamp}-{args.set}-{args.label}.json"
    out.write_text(json.dumps({
        "set": args.set, "label": args.label,
        "date": datetime.now().isoformat(timespec="seconds"),
        "settings": settings, "documents": [d["filename"] for d in docs],
        "with_answers": args.answers, "summary": summary, "rows": rows,
    }, indent=2, ensure_ascii=False), "utf-8")
    print(f"\nSaved to {out.relative_to(ROOT)}")


def print_table(summary: dict) -> None:
    head = "| type | n | " + " | ".join(f"Hit@{k}" for k in KS) + " | " + " | ".join(f"Rec@{k}" for k in KS) + " |"
    print("\n" + head)
    print("|" + "---|" * (2 + 2 * len(KS)))
    lines = [("overall", summary["overall"])] + list(summary["by_type"].items())
    for name, b in lines:
        if b:
            print(f"| {name} | {b['n']} | " + " | ".join(f"{b[f'hit@{k}']:.2f}" for k in KS)
                  + " | " + " | ".join(f"{b[f'recall@{k}']:.2f}" for k in KS) + " |")
    print(f"\nUnanswerable questions (left out): {summary['n_unanswerable']}")


if __name__ == "__main__":
    main()
