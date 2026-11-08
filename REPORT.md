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



---

# V3

## Team (V3)

| Member | V3 work |
|---|---|
| Irina Kiseleva | Concept graph (schema, extraction with Pydantic validation, entity resolution, v1 and v2), graph retriever, 2 new two_hop questions (q11, q12), 10 graded triples, front-end (retriever toggles, `found_by` badges, graph path) |
| Paulo Rogerio Guimaraes Filho | BM25 index (SQLite FTS5), RRF fusion, retriever switches and `found_by` in the API, cost per question, evaluation command (`--retrievers`, `--candidates`, `--set both`), evaluation runs, review and merge of `feat/graph` (graph chunk ids fixed so the graph works on any machine) |

## Results

Settings for every run: chunk 800 / overlap 10 %, embedding all-MiniLM-L6-v2, RRF with k = 60, 20 candidates per retriever before fusion. Retrieval only (no LLM). Files in `eval/results/` (`20261108-1956*` for Kestrel, `20261108-1725*`/`1726*` for the courses).

### Kestrel (10 answerable questions, 2 not_in_corpus left out)

| Retrievers | Hit@1 | Hit@3 | Hit@5 | Rec@1 | Rec@3 | Rec@5 | Rec@10 |
|---|---|---|---|---|---|---|---|
| dense (V2) | 0.50 | 0.80 | 0.90 | 0.33 | 0.70 | 0.75 | 0.90 |
| dense + BM25 | 0.70 | 1.00 | 1.00 | 0.38 | 0.78 | 0.78 | 0.90 |
| dense + BM25 + graph | 0.70 | 1.00 | 1.00 | 0.38 | 0.82 | 0.88 | 1.00 |
| graph alone | 0.00 | 0.20 | 0.30 | 0.00 | 0.10 | 0.20 | 0.30 |

Recall@5 per question type:

| Retrievers | exact_identifier (2) | split_answer (2) | vocabulary (1) | versions (2) | two_hop (3) |
|---|---|---|---|---|---|
| dense (V2) | 0.50 | 1.00 | 1.00 | 1.00 | 0.50 |
| dense + BM25 | 1.00 | 0.62 | 1.00 | 1.00 | 0.50 |
| dense + BM25 + graph | 1.00 | 0.62 | 1.00 | 1.00 | 0.83 |
| graph alone | 0.00 | 0.00 | 0.00 | 0.00 | 0.67 |

### Courses (18 answerable questions, 4 not_in_corpus left out)

No graph on this corpus (see known failures).

| Retrievers | Hit@1 | Hit@3 | Hit@5 | Rec@1 | Rec@3 | Rec@5 | Rec@10 |
|---|---|---|---|---|---|---|---|
| dense (V2) | 0.50 | 0.78 | 0.83 | 0.50 | 0.75 | 0.83 | 1.00 |
| dense + BM25 | 0.50 | 0.89 | 1.00 | 0.50 | 0.86 | 1.00 | 1.00 |

| Retrievers | exact_identifier (2) | other (11) | split_answer (2) | vocabulary (3) |
|---|---|---|---|---|
| dense (V2) | 1.00 | 1.00 | 0.50 | 0.33 |
| dense + BM25 | 1.00 | 1.00 | 1.00 | 1.00 |

### Cost per question

| Retrievers | LLM calls | Tokens | Latency (retrieval) |
|---|---|---|---|
| dense | 0 | 0 | ~110 ms |
| dense + BM25 | 0 | 0 | ~95 ms |
| dense + BM25 + graph | 0 | 0 | ~100 ms |
| BM25 alone | 0 | 0 | 0.2 ms |
| graph alone | 0 | 0 | < 1 ms |

The differences between ~95 and ~110 ms are noise: the time is spent embedding the question. BM25 and the graph cost almost nothing at query time. The graph retriever calls no LLM (entities are found by matching names and aliases in the question). `/ask` adds one LLM call per question, as in V2.

The cost of the graph is at indexing: graph v2 = 44 LLM calls, 24,145 tokens, 179 s (Gemini flash-lite, free tier). BM25 indexing is part of the upload and is not measurable next to the embeddings.

### What moved

- **exact_identifier**: Kestrel q01 (KST-2044, V2 known failure 2). The first relevant chunk goes from rank 7 (dense) to rank 3 (dense + BM25). BM25 alone puts it at rank 1: the token `kst-2044` exists in one chunk only, so its IDF is high. Recall@5 0.50 → 1.00.
- **two_hop**: the graph moves Recall@5 from 0.50 to 0.83 and Recall@10 from 0.67 to 1.00. q11 and q12 go from 0.5 to 1.0 at k = 5: the second hop (the Messaging / Identity rows of the teams table) is reached through the graph edges. BM25 does not help here.
- **courses vocabulary**: Recall@5 0.33 → 1.00 with BM25. These questions still share rare words with the answer (`localhost:5432`, `0.83`), so keyword search finds them even when the embedding does not.
- **split_answer on Kestrel**: Recall@5 1.00 → 0.62 with BM25. See "One question where adding a retriever made it worse".

## Default configuration

**dense + BM25 on both corpora, plus the graph on Kestrel, 20 candidates per retriever.** `dense + bm25` is also the default of the API.

- Kestrel: Hit@3 0.80 → 1.00 and Recall@5 0.75 → 0.88 against V2. The graph adds +0.33 Recall@5 on two_hop and loses nothing on the other types against dense + BM25.
- Courses: Recall@5 0.83 → 1.00 with BM25. No graph on this corpus.
- Cost: no extra LLM call per question, latency unchanged (~100 ms).
- What we lose: Kestrel q03 (split_answer) Recall@5 1.00 → 0.25. We accept it because the answer chunk is still at rank 1 (Hit@1 unchanged) and the gains are on 3 question types.

The graph is not on by default for the courses corpus: there is no graph for it.

## After fusion: did the graph's chunks reach the top k?

Counted on Kestrel, dense + BM25 + graph, top 5 (`found_by` in the result files).

| Candidates per retriever | Graph chunks in the top 5 (12 questions, 60 slots) | Found by the graph only | two_hop Rec@3 | vocabulary Hit@3 |
|---|---|---|---|---|
| 20 | 11 | 0 | 0.67 | 1.00 |
| 40 | 17 | 0 | 0.83 | 0.00 |

- Yes for the two_hop questions (q08, q11, q12), almost never for the others: the graph only finds entities in questions that name a code, a service or a team.
- No chunk reaches the top 5 with the graph as its **only** retriever. Every graph chunk in the top 5 was also found by dense or BM25. With RRF, one vote at rank 1 is worth 1/61 = 0.016, two votes at rank 10 are worth 2/70 = 0.029. In practice the graph works as a third vote that pushes up a chunk the other two already had, more than as a source of new chunks.
- We measured one change: 40 candidates instead of 20. two_hop Recall@3 goes 0.67 → 0.83, but q05 (vocabulary) goes from rank 2 to rank 4 (Hit@3 1.00 → 0.00): more candidates also give more votes to chunks that are only weakly related. Recall@5 is the same (0.88). We keep 20.
- q10 (not_in_corpus, Business seat price) gets 2 graph chunks in the top 5 because the question names the "Business" plan. The answer step must still say not_found.

## One question where adding a retriever made it worse

**Kestrel q03: "What happens, step by step, when a customer's card payment fails?"** (split_answer, 4 evidence quotes, all in `billing-policy-2026.md`).

| Retrievers | Rank of each top-3 chunk | Recall@3 | Recall@5 |
|---|---|---|---|
| dense | 2026 #5 (relevant), 2026 #4 (relevant), 2025 #3 | 1.00 | 1.00 |
| dense + BM25 | 2026 #4 (relevant), runbook #9, 2025 #1 | 0.25 | 0.25 |

Why:
- Dense rank 1 (2026 chunk 5, the retry dates and the suspension) is only rank 10 for BM25: its words ("retry", "suspended", "days") are not the words of the question. RRF: 1/61 + 1/70 = 0.0307.
- Chunks that are in the middle of both lists pass in front: the runbook chunk 9 (dense 4, BM25 2: 1/64 + 1/62 = 0.0318), the **2025** policy chunk 1 (dense 7, BM25 1: 1/67 + 1/61 = 0.0313) and the 2025 chunk 3 (dense 3, BM25 6: 0.0310). The relevant chunk falls from rank 1 to rank 7.
- The question words ("card", "payment", "fails", "customer") are in both versions of the billing policy. BM25 cannot tell 2025 from 2026: it is V2 known failure 1 (two versions), made worse.

The same effect, smaller, on q05 (vocabulary, "I lost my phone and I can't log in"): rank 1 → 2. The answer chunk (product guide #6) is not in the 20 BM25 candidates, so it has one vote; runbook chunk 2 (dense 2, BM25 1) passes in front.

What would fix it: weighted RRF (lower weight for BM25 on long questions) or a date / status filter on the policies. Not done in V3 (weighted RRF is the teams-of-3 piece).

## Decision log (V3)
## Concept graph (Kestrel)

This section covers how the graph is built and used. Its retrieval numbers are in "Results", and what happened to its chunks after fusion is in "After fusion" above.

### Schema

The schema is **fixed**, not open. Kestrel is a small, well-structured support corpus (error codes, services, teams, people, channels, plans, policies), so a closed list of types keeps the graph clean and makes every LLM output checkable.

- Entity types: `ErrorCode`, `Service`, `Team`, `Person`, `Channel`, `Plan`, `Policy`, `Feature`, `Version`.
- Relation types: `OWNS`, `ESCALATES_TO`, `RAISED_BY`, `CONTACT_VIA`, `MEMBER_OF`, `LEADS`, `APPLIES_TO`, `PART_OF`, `REPLACES`, `DEPENDS_ON`.

Trade-off: an open schema would capture more facts, but with no way to validate them and more synonyms (`owns`, `is owner of`, `maintains`) to merge later.

### Build (`backend/graph_build.py`)

1. One LLM call per Kestrel chunk (Gemini, `gemini-3.1-flash-lite-preview`, temperature 0, JSON output with the Pydantic schema).
2. **Validation:** every output is checked with `Extraction.model_validate_json` (Pydantic). If it fails, we retry once. If it fails again, the chunk is skipped and logged in `failures`.
3. **Post-validation filter (v2):** self-loops and entities with junk names (`no`, `yes`, `none`, fragments under 3 characters) are dropped and counted.
4. **Provenance:** every node and every edge keeps the list of `chunk_id`s it comes from. The same triple found in two chunks is one edge with two chunk ids.

### Entity resolution

Key = normalized name: lowercase, collapsed spaces, leading `the ` removed, trailing ` team` / ` service` removed. In v1 the type was part of the key; in v2 it is not (the first type seen is kept, all types are recorded).

- **Merge we got right (v1):** `E-mail` and `e-mail` → one node.
- **Merge we missed (v1):** `Platform team` (from the runbook header) and `Platform` (from the service catalog) stayed two nodes. v2 fixes it by stripping the ` team` suffix.
- Limit: no alias or fuzzy matching. `mailman` and `postroom` are not merged, which is correct (different services), but the graph only links them through a `REPLACES` edge if the LLM extracts it.

### Retrieval (`backend/graph_retriever.py`)

Local search, no LLM at query time:

1. **Entity linking:** node names and aliases are matched as whole phrases in the normalized question.
2. **Traversal:** breadth-first, both edge directions, up to 2 hops.
3. **Scoring:** found nodes add 1.0 to their chunks; an edge at hop h adds 1/(1+h); a node reached at hop h adds 0.5/(1+h).
4. Returns a ranked list of chunks plus the path (entities, edges, chunk ids) shown in the UI.

Other options we considered: LLM-based entity extraction from the question (better recall, but 1 extra LLM call per question); embedding match on entity names, as in LightRAG (handles paraphrases); GraphRAG community summaries for global questions (much higher indexing cost, not needed for a 44-chunk corpus).

### Graph in numbers

| | v1 | v2 (current) |
|---|---|---|
| Chunks | 44 | 44 |
| Entities | 67 | 36 |
| Relations | 68 | 31 |
| Merges | 1 | 0 |
| LLM calls (indexing) | 44 | 44 |
| Tokens (indexing) | 21,078 | 24,145 |
| Build time | 345 s | 179 s |
| Failed chunks | 0 | 2 (HTTP 429, free tier rate limit) |
| Dropped triples | — | 2 |
| LLM calls per question | 0 | 0 |

### v1 → v2: what went wrong and what we changed

v1 did not find q08 at all (graph-only Hit@10 = 0). The chain is `KST-5031 → postroom → Messaging → #oncall-messaging`, and two links were missing:

- No `KST-5031` node: from that chunk the LLM extracted `postroom ESCALATES_TO post`.
- No `Messaging OWNS postroom`, although the catalog says `Owner: Messaging`.
- Junk triples: `Platform team ESCALATES_TO Platform team` (self-loop), `KST-2051 ESCALATES_TO no`, `Identity OWNS tication` (word cut by a chunk boundary).

v2 changes: a `RAISED_BY` relation, explicit prompt rules (every `KST-####` is an ErrorCode, `Owner: X` under a service heading is `X OWNS service`, no self-loops), the junk filter, name-only resolution, and node-level scoring in the retriever. v2 is smaller (36 entities instead of 67), but graph alone now reaches two_hop Recall@5 0.67 (v1: 0.00 on q08).

### Extraction quality (10 random triples, seed 42)

**8 correct / 2 wrong / 0 unsupported** (details in `eval/triple_grades.md`).

Both wrong triples come from **chunk boundaries** (800 characters):

- `Payments Core OWNS payment processor`: the `### ledger` heading is in the previous chunk, so the LLM attached the owner to the wrong entity.
- `KST-5038 ESCALATES_TO postroom`: the chunk says `Escalate: no` for KST-5038; the postroom sentence at the top belongs to KST-5031.

**What the bad triple costs:** for a question about KST-5038, the graph follows KST-5038 → postroom → Messaging and pulls chunks that suggest escalating to Messaging, while the correct answer is "do not escalate".

Sample bias: 5 of the 10 triples come from the same chunk (the teams table). Table rows are easy, so 8/10 is probably optimistic for prose chunks.

### Where the graph fails

- Chunk boundaries split sections, and the extractor only sees one chunk at a time (both wrong triples).
- Entity linking is exact string matching: a question that paraphrases an entity ("the e-mail service" instead of "postroom") finds nothing.
- Only Kestrel has a graph; our own course corpus does not.
- Optional features not implemented: time validity (`from` / `until`), properties, aliases from an LLM.
- The UI path for the KST-5031 question shows the wrong edge `KST-5038 ESCALATES_TO postroom` (graded triple #8): the bad triple is followed at query time.
### Paulo

**BM25 index: SQLite FTS5, in `backend/data/bm25.sqlite3`.**
Options we looked at:

| Option | Why not |
|---|---|
| The `norag-rag` version (in memory) | Rebuilt at every start; the index is lost when the backend stops. |
| `rank_bm25` saved with pickle | Still in memory; every upload means rebuilding the whole index (IDF changes). |
| `bm25s` | Fast, but one more dependency and the same rebuild on every upload. |
| Postgres `tsvector` | One more service to run; `ts_rank` is not BM25. |
| Elasticsearch | Real BM25, but a heavy server for 237 chunks. |

FTS5 is in Python's `sqlite3` (nothing to install), the index is on disk next to Chroma, and its `bm25()` ranking is standard BM25 (k1 = 1.2, b = 0.75).

**Tokenization: the same as the Words tab, without stop words.**
Lowercase, a word can contain `-`, `_`, `.`, `'` inside, so `KST-2044`, `203.0.113.10` and `technical_bug` stay one token. No stemming. Stop words (same list as the Words tab) are removed from the chunks and from the question. We tokenize in Python and give FTS5 the tokens joined by spaces, with `tokenchars '-_.'` so that FTS5 does not split `KST-2044` again. The question is sent as an OR of its tokens, each one quoted. Check: BM25 alone puts the KST-2044 chunk at rank 1 (Kestrel q01), and the tests check that `KST-2044` does not match `KST-2040`.

**Updates: incremental.**
Upload = insert the rows of the new chunks. Delete = delete the rows of that `doc_id`. A change of chunk size or overlap re-indexes Chroma and BM25 together. Documents that were only in Chroma (uploaded in V1/V2) are copied into BM25 once at start. Limit: there is one table for both corpora, so the IDF is computed on both corpora together. The eval filters by `doc_ids`, but a word that is rare in Kestrel and common in the courses gets a lower IDF. We kept one table because the app lets the user mix documents from both corpora.

**Fusion: plain RRF, k = 60, 20 candidates per retriever.**
RRF only uses ranks, so we do not need to put a cosine score, a BM25 score and a graph score on the same scale. k = 60 is the value of the original paper; we did not tune it. Candidates: 20 and 40 measured, 20 kept (see "After fusion").

**API: same endpoints, optional fields.**
`/ask` and `/retrieve` take `retrievers` and `candidates`, and return `found_by`, `rrf_score`, `graph_path` and `cost`. The V2 front and the V2 eval keep working. Contract in `docs/api-contract.md`.

**Graph chunk ids: `filename#index`.**
The graph was built with chunk ids like `2f6285882623#0003`. The doc id is random and changes at every upload, so on another machine the graph retriever found no chunk at all, without any error. The graph files and `graph_build.py` now use `support-runbook-errors.md#0003`, and the retriever maps them back to the local ids. Results above were run on a fresh database to check it.

## Known failures (V3)

| # | Question / part | Observed | Hypothesis / next step |
|---|---|---|---|
| 1 | Kestrel q03 (split_answer) | Recall@5 1.00 → 0.25 with BM25. | BM25 votes for the 2025 policy and the runbook. Weighted RRF, or a date / superseded filter (V2 failure 1 still open). |
| 2 | Kestrel q08 (two_hop) | Recall@5 stays at 0.50, even with the graph. | The answer (Messaging row, `service-catalog.md#0003`) is 3 hops from KST-5031 (KST-5031 → postroom → Messaging → channel). The retriever stops at 2 hops. The word "team" in the question is also linked to the plan "Team", which adds noise. |
| 3 | Graph provenance | The graph was built on a Windows copy with CRLF line endings (44 chunks). With LF there are 43 chunks, so some chunk boundaries move. 48 of the 53 node → chunk pointers still point to a chunk that contains the entity name. | Same cause as V2 failure 7. Rebuild the graph from LF text (one LLM call per chunk, ~3 min). Not done before the deadline because the graded triples and the numbers would change. |
| 4 | Graph v2 coverage | `product-guide.md` has no triple, and 2 chunks of `service-catalog.md` (#4, #5) failed with 429 (free tier, 15 requests/min). | Pause between calls in `graph_build.py`, and a schema that fits the product guide (features, roles). |
| 5 | BM25 IDF | One FTS5 table for both corpora: the IDF mixes Kestrel and the courses. | One table per corpus, or a corpus column used in the ranking. |
| 6 | Courses | No graph for our own corpus (optional in V3). | Course decks are mostly definitions, not chains; a subset (DevOps tools → owners) could work. |
| 7 | Cost per question | Measured on retrieval only (0 LLM calls). Tokens per answer not measured for each configuration. | Run `--answers` for each configuration (1 LLM call per question). |
