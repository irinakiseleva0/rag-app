# Evaluation (V2)

Two question sets, same JSONL format (Kestrel format):

| Set | File | Corpus | Questions |
|---|---|---|---|
| `kestrel` | `questions/kestrel.jsonl` | `docs/kestrel/` (provided) | 10 starter questions |
| `courses` | `questions/courses.jsonl` | `docs/corpus/` (our course decks, not committed) | 22 questions (V1 set converted to JSONL; ids and wording unchanged) |

`questions.json` is the original V1 file, kept for history.

Question types: `exact_identifier`, `split_answer`, `vocabulary`, `not_in_corpus`, `versions`, `two_hop`, `other`.

## Relevance and metrics

A retrieved chunk is **relevant** to an evidence item if it comes from the same source file
and contains the quote (case, quotes and whitespace normalized). See `metrics.py`.

- **Hit@k**: at least one evidence quote is in the top k chunks.
- **Recall@k**: share of the evidence quotes found in the top k chunks (useful for split answers).
- k = 1, 3, 5, 10, overall and per question type.
- Unanswerable questions (`answerable: false`) are left out of the retrieval measure.

## Run

Backend running, both corpora uploaded (the script only searches the documents of the chosen corpus).

```powershell
python eval/run_eval.py --set kestrel --check-only          # quotes exist in the corpus
python eval/run_eval.py --set kestrel --label c800-o10       # retrieval only: fast, no LLM
python eval/run_eval.py --set courses --label c800-o10
python eval/run_eval.py --set kestrel --label c800-o10 --answers   # also generates answers (LLM)
```

Results: `eval/results/<date>-<set>-<label>.json` (settings, summary table, every retrieved chunk with
a `relevant` flag, and with `--answers` the answer plus empty `grade` / `grade_note` fields to fill in by hand).

## No-context test

Asks every question to the LLM without retrieval (backend venv active, key in `backend/.env`):

```powershell
python eval/no_context.py --set kestrel
python eval/no_context.py --set courses
```

Then set `known_without_rag` to `true` or `false` by hand in the result file.
