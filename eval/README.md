# Retrieval evaluation

`questions.json`: 22 questions on `docs/corpus/`.

| Type | Count | Purpose |
|---|---|---|
| normal | 12 | Facts stated clearly on one slide |
| hard | 6 | Paraphrase, vocabulary mismatch, multi-column slide, two documents |
| unanswerable | 4 | Not in the corpus: the app should answer `not_found` |

Each answerable question has `evidence`: exact short phrase(s) from the corpus.
A question is a **hit** when every evidence phrase appears in the top-k retrieved chunks.
Phrases stay valid when chunk size changes, so V1 and V2 results are comparable.

## Run

```powershell
python eval/run_eval.py --check-only            # evidence phrases exist in docs/corpus
python eval/run_eval.py --label v1-baseline     # backend running, corpus uploaded
python eval/run_eval.py --label v1-ask --ask    # also calls /ask (uses the LLM)
```

Results are saved in `eval/results/<date>-<label>.json`.

## Metrics

- `hit_rate_at_k`: share of answerable questions whose evidence is in the top-k chunks.
- `mrr`: mean reciprocal rank (1 = evidence in the first chunk, 0 = not retrieved).
- `mean_top_score_answerable` vs `mean_top_score_unanswerable`: if they are close,
  a similarity threshold cannot detect unanswerable questions.
- `correct_refusal_rate` (with `--ask`): share of unanswerable questions answered `not_found`.
