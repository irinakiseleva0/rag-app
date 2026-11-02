# RAG App — V2

A web app that answers questions about a document corpus, with references
to the passages used. EPITA BCS S5 — AI Systems Integration & Operations.

Team: Irina Kiseleva (frontend, evaluation), Paulo Rogerio Guimaraes Filho (backend).
Design choices, results and known failures: see [REPORT.md](REPORT.md).

## Structure

| Folder / file | Content |
|---|---|
| `backend/` | FastAPI + ChromaDB + Gemini ([backend/README.md](backend/README.md)) |
| `frontend/` | React + Vite + TypeScript |
| `eval/` | Question sets (JSONL), evaluation scripts, results ([eval/README.md](eval/README.md)) |
| `API.md` | API contract between frontend and backend |
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

## Evaluation

Question sets: `eval/questions/kestrel.jsonl` (10 provided) and `eval/questions/courses.jsonl` (22, ours).
Both corpora must be uploaded; each run only searches the documents of its own corpus.

**From the UI:** tab **Evaluation** → choose the set, type a configuration label (e.g. `c800-o10`) → **Run evaluation**.

**From the terminal** (backend running):

```powershell
python eval/run_eval.py --set kestrel --check-only               # evidence quotes exist in the corpus
python eval/run_eval.py --set kestrel --label c800-o10            # retrieval only: fast, no LLM
python eval/run_eval.py --set courses --label c800-o10
python eval/run_eval.py --set kestrel --label c800-o10 --answers  # also generates answers (LLM)
```

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
