"""Retrieval evaluation for the RAG app (V1 baseline, re-run in V2).

For each question in questions.json, call POST /retrieve and check whether the
retrieved chunks contain the question's evidence phrase(s).

Why evidence phrases and not chunk ids? Chunk ids change when chunk size or
overlap change. A phrase from the source text does not, so V1 and V2 numbers
stay comparable.

Usage (backend running, corpus uploaded):
    python eval/run_eval.py --label v1-baseline
    python eval/run_eval.py --label v1-baseline --ask     # also calls /ask (uses the LLM)
    python eval/run_eval.py --check-only                  # only checks questions.json against docs/corpus

Standard library only: no pip install needed.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "questions.json"
CORPUS = ROOT / "docs" / "corpus"
RESULTS = ROOT / "eval" / "results"


def normalize(text: str) -> str:
    """Lowercase, unify quotes/dashes, collapse whitespace (line breaks inside chunks)."""
    for a, b in {"“": '"', "”": '"', "’": "'", "‘": "'", "–": "-", "—": "-"}.items():
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).lower().strip()


def http(api: str, method: str, path: str, body: dict | None = None) -> dict | list:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        api + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} failed: HTTP {e.code} {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Cannot reach the backend at {api}: {e.reason}")


def check_only(questions: list[dict]) -> int:
    """Make sure every evidence phrase really exists in the corpus files."""
    corpus = {p.name: normalize(p.read_text("utf-8")) for p in CORPUS.glob("*.*")}
    if not corpus:
        print(f"No files in {CORPUS}")
        return 1
    problems = 0
    for q in questions:
        for ev in q["evidence"]:
            found = [name for name, text in corpus.items() if normalize(ev) in text]
            status = "ok " if found else "MISSING"
            if not found:
                problems += 1
            print(f"{status} {q['id']}: {ev!r} -> {found}")
    print(f"\n{problems} evidence phrase(s) not found.")
    return 1 if problems else 0


def evaluate(args: argparse.Namespace, questions: list[dict]) -> None:
    api = args.api.rstrip("/")
    settings = http(api, "GET", "/settings")
    top_k = args.top_k or settings["top_k"]
    documents = http(api, "GET", "/documents")
    if not documents:
        raise SystemExit("No documents uploaded. Upload docs/corpus/*.md first.")
    doc_ids = [d["id"] for d in documents]

    rows = []
    for q in questions:
        start = time.perf_counter()
        chunks = http(api, "POST", "/retrieve",
                      {"question": q["question"], "doc_ids": doc_ids, "top_k": top_k})["chunks"]
        latency_ms = round((time.perf_counter() - start) * 1000)
        texts = [normalize(c["text"]) for c in chunks]

        evidence = [normalize(e) for e in q["evidence"]]
        found = [any(e in t for t in texts) for e in evidence]
        # rank (1-based) of the first chunk that contains the first evidence phrase
        rank = next((i + 1 for i, t in enumerate(texts) if evidence and evidence[0] in t), None)

        row = {
            "id": q["id"],
            "type": q["type"],
            "question": q["question"],
            "hit": bool(evidence) and all(found),
            "partial": bool(evidence) and any(found) and not all(found),
            "rank": rank,
            "top_score": chunks[0]["score"] if chunks else None,
            "retrieved": [{"chunk_id": c["chunk_id"], "filename": c["filename"],
                           "score": c["score"]} for c in chunks],
            "latency_ms": latency_ms,
        }

        if args.ask:
            res = http(api, "POST", "/ask",
                       {"question": q["question"], "doc_ids": doc_ids, "top_k": top_k})
            row["ask_status"] = res["status"]
            row["ask_answer"] = res["answer"] or res.get("error")
            row["expected_answer"] = q["expected_answer"]
            if q["type"] == "unanswerable":
                row["correct_refusal"] = res["status"] == "not_found"

        rows.append(row)
        mark = "-" if q["type"] == "unanswerable" else ("HIT " if row["hit"] else "MISS")
        extra = f" ask={row['ask_status']}" if args.ask else ""
        print(f"{q['id']:4} {q['type']:12} {mark:4} rank={rank} "
              f"top_score={row['top_score']}{extra}  {q['question'][:60]}")

    summary = summarize(rows, args.ask)
    print("\n" + json.dumps(summary, indent=2))

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{stamp}-{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label,
        "date": datetime.now().isoformat(timespec="seconds"),
        "settings": {**settings, "top_k": top_k},
        "n_documents": len(documents),
        "summary": summary,
        "rows": rows,
    }, indent=2), "utf-8")
    print(f"\nSaved to {out.relative_to(ROOT)}")


def summarize(rows: list[dict], with_ask: bool) -> dict:
    answerable = [r for r in rows if r["type"] != "unanswerable"]
    unanswerable = [r for r in rows if r["type"] == "unanswerable"]

    def rate(rs: list[dict], key: str) -> float | None:
        return round(sum(r[key] for r in rs) / len(rs), 3) if rs else None

    def mean(values: list[float]) -> float | None:
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 4) if values else None

    summary = {
        "n_questions": len(rows),
        "hit_rate_at_k": rate(answerable, "hit"),
        "hit_rate_normal": rate([r for r in answerable if r["type"] == "normal"], "hit"),
        "hit_rate_hard": rate([r for r in answerable if r["type"] == "hard"], "hit"),
        # Mean Reciprocal Rank: 1 if the evidence is in the 1st chunk, 0.5 if 2nd, ... 0 if missing
        "mrr": mean([1 / r["rank"] if r["rank"] else 0 for r in answerable]),
        # If unanswerable questions get scores as high as answerable ones,
        # a similarity threshold cannot separate them (an idea for V2).
        "mean_top_score_answerable": mean([r["top_score"] for r in answerable]),
        "mean_top_score_unanswerable": mean([r["top_score"] for r in unanswerable]),
        "mean_latency_ms": mean([r["latency_ms"] for r in rows]),
    }
    if with_ask:
        summary["correct_refusal_rate"] = rate(unanswerable, "correct_refusal")
        summary["ask_status_counts"] = {
            s: sum(r["ask_status"] == s for r in rows) for s in ("answered", "not_found", "error")
        }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--label", default="run", help="name of the run, e.g. v1-baseline")
    parser.add_argument("--top-k", type=int, help="default: the backend's current top_k")
    parser.add_argument("--ask", action="store_true", help="also call /ask (uses the LLM, costs tokens)")
    parser.add_argument("--check-only", action="store_true", help="only check evidence against docs/corpus")
    args = parser.parse_args()

    questions = json.loads(QUESTIONS.read_text("utf-8"))
    if args.check_only:
        sys.exit(check_only(questions))
    evaluate(args, questions)


if __name__ == "__main__":
    main()
