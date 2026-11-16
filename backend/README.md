# Backend

FastAPI + ChromaDB + an LLM (Gemini by default). The API is described in `../API.md`.

## Run on Windows (PowerShell)

```
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and put your key in `LLM_API_KEY` (Gemini key: https://aistudio.google.com/app/api-keys). To use another LLM, see "Use another LLM" below.

```
uvicorn main:app --reload
```

If PowerShell refuses to run `Activate.ps1`, run this first:
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

## Run on macOS / Linux

```
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

## Check it works

- API docs: http://127.0.0.1:8000/docs
- Tests (no API key needed): `pytest -q`
- The first upload is slow: ChromaDB downloads its embedding model once (~80 MB).
- To use it with the frontend, set `VITE_USE_MOCK=false` in `frontend/.env`.

## Use another LLM

Put these 3 lines in `backend/.env` (examples in `.env.example`), then restart uvicorn:

```
LLM_URL="https://openrouter.ai/api/v1"
LLM_API_KEY="your_key"
LLM_MODEL="nvidia/nemotron-3.5-lightning:free"
```

Any server with `/chat/completions` (OpenAI format) works: Gemini, Ollama, OpenRouter...
