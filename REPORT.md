# RAG App — Report (V1 and V2)

V1 sections first, then [V2](#v2).

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

**Backend: FastAPI + Pydantic.**
Considered: Flask.
FastAPI checks the requests with Pydantic and gives /docs for free.
The same Pydantic models are used to check the LLM answer.

**Embedding model: all-MiniLM-L6-v2 (Chroma default, local, 384 dimensions).**
Considered: Gemini embeddings.
Local = free, no API key, no rate limit. Re-indexing after a settings change costs nothing.
Downside: small English model, weaker on paraphrases (see the hard questions).

**Vector database: ChromaDB with cosine distance.**
Considered: FAISS.
Chroma runs inside the Python process and saves to disk (`backend/data/`), no server to install.
Score = 1 - cosine distance. It is a similarity, not a confidence.

**Chunking: fixed size in characters, overlap in %.**
Naive on purpose: V1 is the baseline.
We keep `char_start` / `char_end` so that `text[start:end]` is the chunk, the user can check the source.
Downside: one chunk can mix several slides (known failure 5).

**What is recomputed when settings change.**
`chunk_size` or `overlap`: all documents are chunked and embedded again, from the original files saved in `backend/data/files/`.
`top_k`: nothing is recomputed, it only changes the search.

**Prompt and output of /ask.**
Each chunk is sent with its id in brackets. Gemini must answer only from the chunks.
It returns JSON: status (answered / not_found), answer, used_chunk_ids. Temperature 0 for stable answers.

**Validation of the LLM answer.**
The JSON is checked with Pydantic. We return status "error" if the JSON is invalid,
the answer is empty, no chunk is cited, or a cited id was not retrieved.
First version used all chunks as references when the ids were wrong: this hid wrong citations, fixed after Irina's review.

**Nothing retrieved.**
If no chunk is found, /ask returns not_found without calling Gemini.
No score threshold: scores of good and unanswerable questions overlap (see evaluation).

**Errors.**
Every error returns `{"detail": "..."}` (400, 404, 413, 422).
Unexpected errors return a short message, the details are only in the server logs.

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


---

# V2

## Team (V2)

| Member | V2 work |
|---|---|
| Irina Kiseleva | Kestrel corpus and question sets (JSONL), no-context test, evaluation (Hit@k / Recall@k, CLI + Evaluation tab), Words tab (backend + frontend), hidden `/about` page, hand grading, README |

| Paulo Rogerio Guimaraes Filho | Review of the Words PR (code read, 33 tests run), `.gitattributes` fix for known failure 7 (LF line endings), review of the V2 report |

## Corpora and question sets

| Set | Corpus | Questions | Types |
|---|---|---|---|
| `kestrel` | `docs/kestrel/` (5 files, 44 chunks at 800) | 10 provided | exact_identifier 2, split_answer 2, vocabulary 1, versions 2, two_hop 1, not_in_corpus 2 |
| `courses` | `docs/corpus/` (5 course decks, 194 chunks at 800) | 22 ours | other 11, exact_identifier 2, vocabulary 3, split_answer 2, not_in_corpus 4 |

`courses.jsonl` is our V1 set converted to the Kestrel format. Ids and wording unchanged; only `type` and `evidence: {source, quote}` were added.

## No-context test

Every question asked to Gemini without retrieval (`eval/no_context.py`). Files: `eval/results/*-no-context.json`.

| Set | Answerable questions the model answers correctly anyway |
|---|---|
| Kestrel | 0 / 8 |
| Courses | 9 / 18: q02, q07, q08, q09, q10, q11, q12, h01, h03 |

Notes:
- Kestrel q09 (iPhone app): the model talks about another company called Kestrel (weather meters).
- Kestrel q06 (refund at 45 days): the model guesses "30 days", the rule of the *old* policy.
- Courses q04, q05, q06: confident and wrong (port 3000, medical triage categories, HTTP 422).
- Unanswerable courses questions u01, u03, u04: the model answers from general knowledge. The app must still say "not in the documents".

Decision: we keep the 9 flagged questions (the set stays fixed) and report them. Retrieval on the two halves at 800 / 10%:
Hit@5 = 0.78 on the 9 flagged questions, 0.89 on the 9 others.

## Results

Relevance: a chunk is relevant if it comes from the evidence source and contains the evidence quote.
Hit@k: at least one evidence quote in the top k. Recall@k: share of the evidence quotes in the top k.
Unanswerable questions are left out. Top-k for answers: 5.

### Kestrel

| Type | n | Config | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 |
|---|---|---|---|---|---|---|---|
| **overall** | 8 | 800 / 10% | 0.625 | 0.625 | 0.75 | 1.00 | 0.72 |
| | | 400 / 10% | 0.375 | 0.625 | 0.75 | 0.75 | 0.69 |
| exact_identifier | 2 | 800 / 10% | 0.50 | 0.50 | 0.50 | 1.00 | 0.50 |
| | | 400 / 10% | 0.00 | 0.00 | 0.50 | 0.50 | 0.50 |
| split_answer | 2 | 800 / 10% | 1.00 | 1.00 | 1.00 | 1.00 | 0.88 |
| | | 400 / 10% | 0.50 | 1.00 | 1.00 | 1.00 | 0.75 |
| versions | 2 | 800 / 10% | 0.50 | 0.50 | 1.00 | 1.00 | 1.00 |
| | | 400 / 10% | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| vocabulary | 1 | 800 / 10% | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| | | 400 / 10% | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| two_hop | 1 | 800 / 10% | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| | | 400 / 10% | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

### Courses

| Type | n | Config | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Recall@5 |
|---|---|---|---|---|---|---|---|
| **overall** | 18 | 800 / 10% | 0.50 | 0.78 | 0.83 | 1.00 | 0.83 |
| | | 400 / 10% | 0.33 | 0.67 | 0.78 | 0.94 | 0.75 |
| exact_identifier | 2 | 800 / 10% | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |
| | | 400 / 10% | 0.50 | 0.50 | 0.50 | 0.50 | 0.50 |
| split_answer | 2 | 800 / 10% | 0.00 | 0.50 | 0.50 | 1.00 | 0.50 |
| | | 400 / 10% | 0.50 | 0.50 | 1.00 | 1.00 | 0.75 |
| vocabulary | 3 | 800 / 10% | 0.00 | 0.33 | 0.33 | 1.00 | 0.33 |
| | | 400 / 10% | 0.00 | 0.33 | 0.33 | 1.00 | 0.33 |
| other | 11 | 800 / 10% | 0.73 | 0.91 | 1.00 | 1.00 | 1.00 |
| | | 400 / 10% | 0.36 | 0.82 | 0.91 | 1.00 | 0.91 |

### What we changed, and what moved

Only the chunk size changed (800 → 400 characters, overlap 10%, same embedding model, same questions).

- Hit@1 drops on both corpora (Kestrel 0.625 → 0.375, Courses 0.50 → 0.33): a small chunk carries less context around the answer, so it ranks first less often.
- Kestrel exact_identifier and two_hop leave the top 10 (q01 KST-2044, q08 KST-5031).
- Courses q06 ("502 invalid_model_output") is not found at any k with 400. Hypothesis: the evidence quote is cut by a chunk boundary more often with small chunks; this is also a limit of our relevance rule.
- Only gain: Courses split_answer at k = 5 (0.50 → 1.00).
- Hit@10 is 1.00 on both corpora at 800: every answer is retrieved, but 2 Kestrel (q01, q08) and 3 Courses (h01, h03, h04) questions only at ranks 6–10, which top-k 5 never shows to the model. The main problem is ranking.

Best configuration: **800 / 10%**.

## Hand grading (Kestrel, 800 / 10%, top-k 5)

Rules, written before grading:
- **correct**: all key facts of the expected answer, nothing that contradicts the documents.
- **partial**: some key facts right, an important one missing.
- **wrong**: the main fact is wrong (old policy, wrong code), or the app answers an unanswerable question, or returns not_found / error on an answerable one.
- **unsupported**: says things the referenced chunks do not say.
- Unanswerable questions are correct only if the app says the answer is not in the documents.

| id | type | grade | failure | note |
|---|---|---|---|---|
| q01 | exact_identifier | wrong | retrieval | evidence at rank 6; the app said not_found (no invention) |
| q02 | exact_identifier | correct | | |
| q03 | split_answer | wrong | retrieval + generation | 2025 and 2026 policies mixed: "14 or 21 days", retries 3/7 instead of 1/3/7 |
| q04 | split_answer | partial | retrieval | last setup steps (test with one Admin, enforce) not in the top 5 |
| q05 | vocabulary | correct | | misses "up to 2 business days" |
| q06 | versions | correct | | 60 days, pro-rated (2026 rule) |
| q07 | versions | correct | | 20% |
| q08 | two_hop | partial | retrieval | first hop only ("team that owns postroom"); service catalog not in the top 5 |
| q09 | not_in_corpus | correct | | not_found |
| q10 | not_in_corpus | correct | | not_found |

Total: 6 correct, 2 partial, 2 wrong, 0 unsupported. All 4 failures start with retrieval.
Grades are stored in `eval/results/*-kestrel-c800-o10-answers.json` (`grade`, `grade_note`).

## Two misses diagnosed with the Words tab

**Kestrel q01 — "What does error KST-2044 mean and how do I fix it?"** (first relevant chunk at rank 6)
- `kst-2044` appears in exactly 1 chunk of 44: the answer chunk (`support-runbook-errors.md` #4).
- The neighbour code `kst-2040` (timeout) is alone in the previous chunk (#3).
- `error` is in 9 chunks; `mean` and `fix` do not exist in the corpus.
- So the one word that identifies the answer is unique, but the embedding sees KST-2044 and KST-2040 as almost the same text, and the generic words dominate. An exact keyword match would rank the answer chunk first: argument for keyword / hybrid search (BM25).

**Courses h04 — "When is version 2 of the RAG project due?"** (first relevant chunk at rank 6–10)
- The answer chunk (`ai-systems-c6-rag.md` #38) contains `rag`, `project` and `2`, but **not** `version` (the slide writes "V2") and not `due`.
- `version` exists 18 times in 13 other chunks; `2` is in 55 of 194 chunks; `rag` in 18, `project` in 23.
- No distinctive word of the question is in the answer chunk: different vocabulary ("version 2" vs "V2") on a two-column slide where "V2" and "Nov. 4th" are far apart.

Contrast — Kestrel q05 ("I lost my phone… can't log in"): `phone`, `can't` and `anymore` do not exist in the corpus at all, yet the answer chunk ranks first. Embeddings handled this vocabulary gap; they failed on the exact identifier. Keyword search would do the opposite: the two methods are complementary.

## Decision log (V2)

### Irina

**Relevance = same source + exact quote (normalized).**
Simple and repeatable. Independent of chunk ids, so configurations can be compared.
Limit: a quote cut by a chunk boundary is not counted.

**Hit@k and Recall@k.**
Hit@k says "did the model see something useful". Recall@k says "did it see the whole answer": it matters for split answers and two-hop questions.

**Retrieve top 10 once, then score k = 1, 3, 5, 10.**
One search per question; the four k values are prefixes of the same ranking.

**Each corpus searched alone.**
Both corpora are uploaded together; the evaluation passes only the doc ids of the set's corpus, so Kestrel questions cannot be "helped" or "hurt" by course chunks.

**Evaluation in the UI uses the same `eval/metrics.py` as the CLI.**
One relevance rule, one result format. The UI run calls the store directly (no HTTP loop).

**No-context test with the same model as the app.**
Short prompt: "Answer briefly. If you do not know, say I don't know." Free-tier limits: pause between calls, retry on 429, resume from the last file.

**Words: tokenizer.**
Lowercase; identifiers kept whole (KST-2044, 203.0.113.10, technical_bug); no stemming (it is what keyword search sees); stop words counted but hidden by default.

**Words: counts per chunk, from ChromaDB.**
The index follows the current chunk settings. With overlap, a word in the shared part is counted in both chunks (a test shows 332 counts for 300 occurrences). It is rebuilt at each request: the corpora are small.

**Words: "chunks that hold the answer".**
A question picked from a set uses the evaluation's relevance rule to mark the answer chunks, so we can see if the question's words are in them.

**Kestrel corpus committed, course decks not.**
Kestrel is fictional and provided for the project. The course decks are teachers' material.

### Paulo
### Paulo

**Line endings: LF for the corpus files.**
On Windows, Git turned the files into CRLF: longer text, different chunks (44 instead of 43).
`.gitattributes` keeps LF in `docs/` and `eval/questions/`, where the exact text matters. Same chunks for everyone.

**Words: no stemming, I agree.**
We see the words like a keyword search would.
Stemming would match "paying" and "payment", but could break codes like KST-2044.

**Words backend: review.**
`words_routes.py` uses `store.collection` directly; a method in `Store` would keep the ChromaDB code in one place.
The index is rebuilt for every request: fine for our small corpora, a big one would need a cache.

## Known failures (V2)

| # | Question | Observed | Hypothesis / next step |
|---|---|---|---|
| 1 | Kestrel q03 — card payment fails | The answer mixes the 2025 and 2026 billing policies ("14 or 21 days"). | Both versions are retrieved; chunks have no date or status. V3: metadata (effective date, superseded) and a filter. |
| 2 | Kestrel q01 — KST-2044 | Answer chunk at rank 6, app says not_found. | Embeddings blur close identifiers. V3: hybrid search (BM25 + embeddings). |
| 3 | Kestrel q08 — KST-5031 → team | Only the first hop is answered. | One query cannot do two hops. V3: second retrieval with the service name found in the first answer. |
| 4 | Courses q06 at 400 characters | Evidence not found at any k. | Quote probably cut by a chunk boundary. |
| 5 | No-context, courses | 9 of 18 answerable questions known by the model. | Public topics. Future questions should target course-specific details. |
| 6 | Free Gemini tier | 429 errors during long runs. | Pause and retry in the scripts; one LLM call per question at most. |
| 7 | Same corpus, different chunks | Kestrel gives 44 chunks on Windows and 43 on Linux. | Git converts line endings to CRLF on Windows: the text is longer, chunk boundaries move. Fix: `.gitattributes` with `eol=lf` for `docs/`. |

