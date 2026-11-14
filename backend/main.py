import logging
import os
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from eval_routes import make_eval_router
from llm import answer_question
from retrieval import hybrid_search
from words_routes import make_words_router
from schemas import AskResult, Cost, DocumentInfo, QuestionRequest, RetrieveResult, Settings
from store import Store
from tracing import Tracer

load_dotenv()
logger = logging.getLogger("rag")

MAX_FILE_SIZE = 2 * 1024 * 1024

app = FastAPI()
store = Store(Path(__file__).parent / "data")
tracer = Tracer(Path(__file__).parent / "data" / "traces.sqlite3")
graph_path = Path(__file__).parent / "data" / "graph" / "kestrel_graph.json"
if graph_path.exists():
    from graph_retriever import GraphRetriever

    graph = GraphRetriever(graph_path, store)
else:
    graph = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Evaluation from the frontend (V2). The lambda reads the current store.
app.include_router(make_eval_router(lambda: store))
app.include_router(make_words_router(lambda: store))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    error = exc.errors()[0]
    field = error["loc"][-1]
    return JSONResponse(status_code=422, content={"detail": f"Invalid request: {field} {error['msg']}"})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception("Unexpected error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. See the backend logs."})


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

    trace = tracer.start("indexing", {"filename": filename})
    status = "error"
    try:
        doc = store.add_document(filename, text, trace=trace)
        status = "ok"
        return doc
    finally:
        trace.finish(status, {"n_chunks": indexed_chunks(trace)})


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
    trace = tracer.start("indexing", {
        "chunk_size": settings.chunk_size, "overlap_percent": settings.overlap_percent,
    })
    status = "error"
    try:
        result = store.update_settings(settings, trace=trace)
        status = "ok"
        return result
    finally:
        trace.finish(status, {"n_chunks": indexed_chunks(trace)})


def indexed_chunks(trace):
    return sum(span["attributes"]["n_chunks"] for span in trace.spans
               if span["name"] == "embed" and "error" not in span["attributes"])


def question_trace(req):
    return tracer.start("question", {
        "question": req.question, "doc_ids": req.doc_ids, "top_k": req.top_k,
        "retrievers": req.retrievers.model_dump(), "candidates": req.candidates,
    })


@app.post("/retrieve", response_model=RetrieveResult)
def retrieve(req: QuestionRequest):
    trace = question_trace(req)
    status = "error"
    cost = Cost()
    try:
        check_doc_ids(req.doc_ids)
        chunks, path, cost = hybrid_search(store, req, graph, trace=trace)
        status = "ok"
        return RetrieveResult(chunks=chunks, graph_path=path, cost=cost, trace_id=trace.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        trace.finish(status, {"llm_calls": cost.llm_calls, "tokens": cost.tokens})


@app.post("/ask", response_model=AskResult)
def ask(req: QuestionRequest):
    trace = question_trace(req)
    start = time.perf_counter()
    status = "error"
    cost = Cost()
    try:
        check_doc_ids(req.doc_ids)
        try:
            chunks, path, cost = hybrid_search(store, req, graph, trace=trace)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception:
            logger.exception("Retrieval failed")
            return AskResult(status="error", answer="", references=[], trace_id=trace.id,
                             error="Retrieval failed. See the backend logs.")

        with trace.span("llm", model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview"),
                        chunks_sent=[chunk.chunk_id for chunk in chunks]) as span:
            result = answer_question(req.question, chunks)
            span.set("tokens", result.cost.tokens)
            span.set("status", result.status)
            span.set("error", result.error or None)
        result.graph_path = path
        result.trace_id = trace.id
        result.cost.llm_calls += cost.llm_calls
        result.cost.tokens += cost.tokens
        result.cost.latency_ms = int((time.perf_counter() - start) * 1000)
        cost = result.cost
        status = result.status
        return result
    finally:
        trace.finish(status, {"llm_calls": cost.llm_calls, "tokens": cost.tokens})


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    trace = tracer.get(trace_id)
    if trace is None:
        raise HTTPException(404, "Trace not found")
    return trace


@app.get("/traces")
def list_traces(kind: Literal["question", "indexing"] | None = None, limit: int = Query(20, ge=0)):
    return tracer.list(kind=kind, limit=limit)
