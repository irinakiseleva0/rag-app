# RAG App — V1 Report

## Team

| Member | Main work |
|---|---|
| Irina Kiseleva | Frontend (React + Vite), API contract (`API.md`), corpus preparation, evaluation (`eval/`) |
| Paulo Rogerio Guimaraes Filho| Backend (FastAPI, chunking, ChromaDB, `/retrieve`, `/ask`) |

Both of us reviewed each other's pull requests.

## Corpus

Five EPITA S5 course decks, converted from PDF/PPTX to Markdown (one `## Slide N` section per slide):

| File | Course | Slides |
|---|---|---|
| `ai-systems-c4-llm-api-integration.md` | AI Systems Integration — LLM API | 59 |
| `ai-systems-c6-rag.md` | AI Systems Integration — RAG | 59 |
| `devops-foundations.md` | DevOps | 60 |
| `docker-compose-multi-container.md` | Shipping Containerized Applications — Docker Compose | 24 |
| `cybersecurity-vocabulary-60-terms.md` | Cybersecurity vocabulary | 61 |

The files are not committed (teachers' material). See the README for how to get them.

## Decision log


### Irina

**Corpus: our S5 course slides.**
Considered: FastAPI docs, a public-domain book.
Chose our courses: we know them, so we can check answers. The LLM does not know our labs.

**Corpus conversion: one section per slide, no repeated footers.**
Footers on every page would add noise to every chunk.
`## Slide N` lets the user find the original slide.

**Frontend: React + Vite, not Next.js.**
The backend is a separate Python service. Vite is simpler and enough.

**Mock API.**
I built the UI before the backend was ready.
`VITE_USE_MOCK` switches between mock and real backend.

**Zod validation in the frontend.**
A wrong backend response shows an error message instead of crashing the page.

**Evaluation with evidence phrases, not chunk ids.**
Chunk ids change when chunk size changes. A phrase from the text does not.
So V1 and V2 results can be compared.

**Evaluation calls `/retrieve`, not `/ask`.**
It measures retrieval only: no LLM, free, fast, repeatable.
`--ask` is a separate option to check "not found" answers.

**22 questions: 12 normal, 6 hard, 4 unanswerable.**
Hard ones test paraphrase, different words, a two-column slide, and two documents.
Unanswerable ones include near misses (Pinecone is named, but not its default model).

### Paulo

<!-- Paulo: write your own entries. Suggested topics:
- FastAPI + Pydantic
- Embedding model (which one, local or hosted, dimension)
- Vector database (ChromaDB, distance metric)
- Chunking (fixed characters, overlap, offsets)
- What is recomputed when settings change
- Prompt and output format of /ask
- Validation of the LLM answer and of the cited chunk ids
- What happens when nothing is retrieved
-->

## Evaluation results

Run: `python eval/run_eval.py --label v1-baseline` and `--ask`
(files in `eval/results/`). 22 questions: 12 normal, 6 hard, 4 unanswerable.

| Setting | Value |
|---|---|
| Chunk size | 800 characters |
| Overlap | 10 % |
| Top-k | 5 |
| Embedding model | all-MiniLM-L6-v2 (Chroma default, local ONNX, 384 dimensions) |
| LLM | Gemini (google-genai, structured JSON output) |

| Metric | Value |
|---|---|
| Hit rate @5 (all answerable) | 0.83 (15/18) |
| Hit rate — normal | 1.00 (12/12) |
| Hit rate — hard | 0.50 (3/6) |
| MRR | 0.62 |
| Mean top score — answerable | 0.46 |
| Mean top score — unanswerable | 0.35 |
| Correct refusals (`--ask`) | 4/4 |
| `/ask` status counts | 14 answered, 5 not_found, 3 error |
| Mean retrieval latency | ~300 ms |

Observations:
- Every normal question is retrieved. Half of the hard ones are not.
- The right chunk is often not first (q01 rank 3, q02 rank 4).
- Similarity is not confidence: CALMS (q07) scores only 0.33 but is
  retrieved first and answered correctly.
- Evaluation limit: h01 counts as a MISS (evidence phrase not in top 5),
  but /ask answered correctly. The same explanation exists on another
  slide. One evidence phrase per question undercounts hits when the
  answer appears in several places.
- Top scores of unanswerable questions (0.29–0.41) overlap with
  answerable ones (q03 = 0.24, h03 = 0.29). A score threshold
  would reject good questions: not a solution for "not found".
- All 4 unanswerable questions got "not_found": the prompt rule works
  on this set (only 4 questions, so this is weak evidence).

## Known failures

| # | Question | Observed | Hypothesis |
|---|---|---|---|
| 1 | q04 (triage app URL), h06 (why the key stays on the server) | Evidence retrieved (rank 3 and 2), but /ask returned error: "The model cited chunks that were not retrieved." | The model rewrites the chunk ids. The citation check catches it (no silent wrong answer), but the user gets no answer. V2: log the raw model output to see the wrong ids; show ids more clearly in the prompt; retry once. |
| 2 | h04 — When is version 2 of the RAG project due? | Evidence not retrieved. /ask: not_found. | Two-column slide: after PDF extraction, "V2" and "Nov. 4th" are far apart, often in different chunks. |
| 3 | h03 — Is a similarity score of 0.83 the same as 83% confidence? | Evidence not retrieved. /ask: error "The LLM call failed". | Retrieval: the corpus writes "83 %" with a space and uses other words. LLM error: free Gemini tier, 22 calls in a row (rate limit). |
| 4 | h01 — My app container cannot reach Postgres at localhost:5432 | Counted as MISS, but the answer is correct. | The explanation exists on two slides; our metric checks only one phrase. Evaluation problem, not retrieval. V2: allow alternative evidence phrases. |
| 5 | Ranking — q01, q02 | Evidence at rank 3–4. | Fixed 800-character windows mix several slides in one chunk. |

Ideas for V2 (to measure, not yet done):
- Chunk by slide (`## Slide N`) instead of fixed characters.
- Compare top-k 5 vs 8.
- Hybrid search (keywords + embeddings) for numbers and exact terms.
- Log the raw LLM answer; retry once on invalid citations.
- Alternative evidence phrases in the question set.