# RAG App — V1

A web app that answers questions about a document corpus, with references
to the passages used. EPITA BCS S5 — AI Systems Integration & Operations.

Team: Irina Kiseleva (frontend, evaluation), Paulo Rogerio Guimaraes Filho (backend).
Design choices, results and known failures: see [REPORT.md](REPORT.md).

## Structure

| Folder / file | Content |
|---|---|
| `backend/` | FastAPI + ChromaDB + Gemini ([backend/README.md](backend/README.md)) |
| `frontend/` | React + Vite + TypeScript |
| `eval/` | Question set and retrieval evaluation script ([eval/README.md](eval/README.md)) |
| `API.md` | API contract between frontend and backend |
| `REPORT.md` | Team, decision log, evaluation results, known failures |
| `docs/corpus/` | Course decks in Markdown (not committed) |

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

### 3. Corpus

Put the course decks (`.md`) in `docs/corpus/`, then upload them in the UI.
They are not in the repository: they are teachers' material, and `docs/corpus/` is git-ignored.

## Evaluation

With the backend running and the corpus uploaded:

```powershell
python eval/run_eval.py --check-only            # evidence phrases exist in docs/corpus
python eval/run_eval.py --label v1-baseline     # retrieval only, no LLM call
python eval/run_eval.py --label v1-ask --ask    # full pipeline, uses Gemini
```

Results are saved in `eval/results/`. See [eval/README.md](eval/README.md).

## API

See [API.md](API.md).
