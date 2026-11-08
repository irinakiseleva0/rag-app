# RAG App — V3

A web app that answers questions about a document corpus, with references
to the passages used. EPITA BCS S5 — AI Systems Integration & Operations.

Team: Irina Kiseleva (frontend, evaluation, concept graph), Paulo Rogerio Guimaraes Filho (backend, BM25, fusion, evaluation runs).
Design choices, results and known failures: see [REPORT.md](REPORT.md).

## Structure

| Folder / file | Content |
|---|---|
| `backend/` | FastAPI + ChromaDB + Gemini ([backend/README.md](backend/README.md)) |
| `frontend/` | React + Vite + TypeScript |
| `eval/` | Question sets (JSONL), evaluation scripts, results ([eval/README.md](eval/README.md)) |
| `API.md` | API contract between frontend and backend (V1/V2) |
| `docs/api-contract.md` | V3 changes: retrievers, `found_by`, `graph_path`, cost |
| `backend/data/graph/` | Kestrel concept graph (`kestrel_graph.json`, and v1 kept for the report) |
| `REPORT.md` | Team, decision log, evaluation results, known failures |
| `docs/kestrel/` | Kestrel Analytics knowledge base (provided corpus, fictional) |
| `docs/corpus/` | Our corpus: course decks in Markdown (not committed) |

## Run (Windows PowerShell)

### 1. Backend

See [backend/README.md](backend/README.md). Short version:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # put your Gemini key in GOOGLE_API_KEY
uvicorn main:app --reload
```

API docs: http://127.0.0.1:8000/docs

### 2. Frontend

In a second terminal:

```powershell
cd frontend
npm install
copy .env.example .env      # set VITE_USE_MOCK=false to use the real backend
npm run dev
```

Open http://localhost:5173

### 3. Corpora

The app works on two corpora. Upload them with **Upload a document** in the left panel:

- **Kestrel KB**: the 5 files of `docs/kestrel/` (in the repository).
- **Our corpus**: the course decks (`.md`) in `docs/corpus/`. They are not in the repository
  (teachers' material, `docs/corpus/` is git-ignored).

The checkboxes in the **Documents** panel choose which documents a question, or the Words tab, uses.

## Features

The main area has three tabs:

| Tab | What it does |
|---|---|
| **Ask** | Question → grounded answer with references; click a reference to see its chunk |
| **Evaluation** | Runs a question set and shows Hit@k / Recall@k (k = 1, 3, 5, 10), overall, per type and per question. Option: also generate the answers. Results saved in `eval/results/` |
| **Words** | Corpus mode: vocabulary (count, number of chunks) and word → chunks. Question mode: which words of a question exist in the corpus, in which chunks, and which do not exist. A question picked from a set also shows the chunks that hold its answer |

Chunk size, overlap and top-k are in **Retrieval settings** (left panel). Changing chunk size or overlap re-indexes every document.

## Retrievers (V3)

Three retrievers, fused with RRF (Reciprocal Rank Fusion, k = 60):

| Retriever | What it is | Index |
|---|---|---|
| `dense` | embeddings (all-MiniLM-L6-v2), cosine | `backend/data/chroma/` |
| `bm25` | keyword search, SQLite FTS5 | `backend/data/bm25.sqlite3` |
| `graph` | concept graph, entities of the question + 2 hops (Kestrel only) | `backend/data/graph/kestrel_graph.json` |

Default: `dense` + `bm25`. The graph is used when it is switched on and the graph file exists.

**In the UI:** the retriever toggles (dense / BM25 / graph) in the Ask tab. Each reference shows which retriever found it and at which rank.

**In the API:** `"retrievers": {"dense": true, "bm25": true, "graph": false}` in `/ask` and `/retrieve`, and `"candidates"` (chunks taken from each retriever before fusion, default 20). See [docs/api-contract.md](docs/api-contract.md).

The BM25 index is filled when a document is uploaded. Documents uploaded before V3 are copied from Chroma into BM25 at the first start.

### Build the concept graph

Kestrel must be uploaded first, and `GOOGLE_API_KEY` set in `backend/.env`.

```powershell
cd backend
python graph_build.py --limit 5     # test the prompt on 5 chunks
python graph_build.py               # whole Kestrel corpus (one LLM call per chunk, about 3 min on the free tier)
```

The graph is written to `backend/data/graph/kestrel_graph.json` and loaded when the backend starts (restart it after a build).

## Evaluation

Question sets: `eval/questions/kestrel.jsonl` (10 provided + 2 two_hop ours) and `eval/questions/courses.jsonl` (22, ours).
Both corpora must be uploaded; each run only searches the documents of its own corpus.

**From the UI:** tab **Evaluation** → choose the set, type a configuration label (e.g. `c800-o10`) → **Run evaluation**.

**From the terminal** (backend running):

```powershell
python eval/run_eval.py --set kestrel --check-only               # evidence quotes exist in the corpus
python eval/run_eval.py --set kestrel --label c800-o10            # retrieval only: fast, no LLM
python eval/run_eval.py --set courses --label c800-o10
python eval/run_eval.py --set kestrel --label c800-o10 --answers  # also generates answers (LLM)
```

**Retrievers (V3).** `--retrievers` takes any combination of `dense`, `bm25`, `graph` (default `dense`). `--set both` runs the two sets one after the other. The label is the list of retrievers unless `--label` is given.

```powershell
python eval/run_eval.py --set both --retrievers dense
python eval/run_eval.py --set both --retrievers dense,bm25
python eval/run_eval.py --set kestrel --retrievers dense,bm25,graph
python eval/run_eval.py --set kestrel --retrievers graph
python eval/run_eval.py --set kestrel --retrievers dense,bm25,graph --candidates 40
```

Each result file also keeps, for every retrieved chunk, `found_by` (retriever and rank) and the cost per question (LLM calls, tokens, latency).

**Graph extraction quality:** `python eval/sample_triples.py` picks 10 random triples (seed 42) and writes them with their chunks to `eval/triple_grades.md` for hand grading.

**No-context test** (LLM without retrieval; backend venv active, key in `backend/.env`):

```powershell
python eval/no_context.py --set kestrel
python eval/no_context.py --set courses
```

Results, hand grades and no-context flags: `eval/results/`. Details: [eval/README.md](eval/README.md).

## Tests

```powershell
cd backend
pytest                    # fake embedding and fake LLM: no network, no key
```

## API

See [API.md](API.md).
