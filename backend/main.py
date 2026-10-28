from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from llm import answer_question
from schemas import AskResult, DocumentInfo, QuestionRequest, RetrieveResult, Settings
from store import Store

load_dotenv()

MAX_FILE_SIZE = 2 * 1024 * 1024

app = FastAPI()
store = Store(Path(__file__).parent / "data")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    error = exc.errors()[0]
    field = error["loc"][-1]
    return JSONResponse(status_code=422, content={"detail": f"Invalid request: {field} {error['msg']}"})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {exc}"})


def check_doc_ids(doc_ids):
    known = [d.id for d in store.list_documents()]
    for doc_id in doc_ids:
        if doc_id not in known:
            raise HTTPException(404, f"Unknown document id: {doc_id}")


@app.get("/documents", response_model=list[DocumentInfo])
def list_documents():
    return store.list_documents()


@app.post("/documents", response_model=DocumentInfo)
async def upload_document(file: UploadFile):
    filename = file.filename or ""
    if not (filename.lower().endswith(".md") or filename.lower().endswith(".txt")):
        raise HTTPException(400, "Only .md and .txt files are accepted.")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 2 MB).")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "The file is not valid UTF-8 text.")
    if text.strip() == "":
        raise HTTPException(400, "The file is empty.")

    return store.add_document(filename, text)


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    if not store.delete_document(doc_id):
        raise HTTPException(404, f"Unknown document id: {doc_id}")
    return {"deleted": True}


@app.get("/settings", response_model=Settings)
def get_settings():
    return store.get_settings()


@app.put("/settings", response_model=Settings)
def put_settings(settings: Settings):
    return store.update_settings(settings)


@app.post("/retrieve", response_model=RetrieveResult)
def retrieve(req: QuestionRequest):
    check_doc_ids(req.doc_ids)
    chunks = store.search(req.question, req.doc_ids, req.top_k)
    return RetrieveResult(chunks=chunks)


@app.post("/ask", response_model=AskResult)
def ask(req: QuestionRequest):
    check_doc_ids(req.doc_ids)
    try:
        chunks = store.search(req.question, req.doc_ids, req.top_k)
    except Exception as e:
        return AskResult(status="error", answer="", references=[], error=f"Retrieval failed: {e}")
    return answer_question(req.question, chunks)