"""Background builds and provenance-preserving storage for document graphs."""

import json
import logging
import os
import threading
from pathlib import Path

from graph_build import GENERIC_PROMPT, build_graph
from graph_schema import GenericExtraction
from llm_client import chat_json, get_model
from redaction import redact

logger = logging.getLogger(__name__)


class DocGraphs:
    def __init__(self, graph_dir: Path, store, tracer, kestrel_graph_path: Path | None,
                 llm=chat_json):
        self.graph_dir = Path(graph_dir)
        self.store = store
        self.tracer = tracer
        self.kestrel_graph_path = Path(kestrel_graph_path) if kestrel_graph_path else None
        self.llm = llm
        self.on_change = lambda: None
        self.threads = {}
        self._states = {}
        self._jobs = {}
        self._lock = threading.RLock()

    def _document(self, doc_id):
        for doc in self.store.list_documents():
            if doc.id == doc_id:
                return doc
        raise ValueError(f"Unknown document id: {doc_id}")

    def _path(self, doc_id):
        return self.graph_dir / f"{doc_id}.json"

    @staticmethod
    def _ready(result, graph):
        stats = graph.get("stats", {})
        nodes = [{key: node[key] for key in ("id", "name", "type", "chunk_ids")}
                 for node in graph["nodes"]]
        edges = [{key: edge[key] for key in ("source", "relation", "target", "chunk_ids")}
                 for edge in graph["edges"]]
        total = stats.get("chunks", result["progress"]["total"])
        return {**result, "status": "ready", "progress": {"done": total, "total": total},
                "nodes": nodes, "edges": edges,
                "stats": {"nodes": len(nodes), "edges": len(edges),
                          "llm_calls": stats.get("llm_calls", 0), "tokens": stats.get("tokens", 0),
                          "seconds": stats.get("seconds", 0), "model": stats.get("model", "unknown")}}

    def _kestrel_subgraph(self, doc):
        if not self.kestrel_graph_path or not self.kestrel_graph_path.exists():
            return None
        graph = json.loads(self.kestrel_graph_path.read_text(encoding="utf-8"))
        prefix = doc.filename + "#"

        def mapped(chunk_ids):
            return [doc.id + "#" + chunk_id.rsplit("#", 1)[1]
                    for chunk_id in chunk_ids if chunk_id.startswith(prefix)]

        if not any(mapped(item.get("chunk_ids", [])) for item in graph["nodes"] + graph["edges"]):
            return None
        edges = [{**edge, "chunk_ids": mapped(edge["chunk_ids"])}
                 for edge in graph["edges"] if mapped(edge["chunk_ids"])]
        used = {edge[key] for edge in edges for key in ("source", "target")}
        nodes = [{**node, "chunk_ids": mapped(node["chunk_ids"])}
                 for node in graph["nodes"] if node["id"] in used]
        # The original stats describe the corpus build; progress describes this document.
        return {"nodes": nodes, "edges": edges,
                "stats": {**graph.get("stats", {}), "chunks": doc.n_chunks}}

    def status(self, doc_id):
        doc = self._document(doc_id)
        result = {"doc_id": doc_id, "status": "none",
                  "progress": {"done": 0, "total": doc.n_chunks},
                  "error": None, "stats": None, "nodes": [], "edges": []}
        with self._lock:
            state = self._states.get(doc_id)
            if state is not None:
                result.update(state)
                result["progress"] = dict(result["progress"])
                if state["status"] in {"building", "error"}:
                    return result
            try:
                path = self._path(doc_id)
                graph = (json.loads(path.read_text(encoding="utf-8")) if path.exists()
                         else self._kestrel_subgraph(doc))
                if graph is not None:
                    return self._ready(result, graph)
            except (OSError, ValueError, KeyError, TypeError) as error:
                result.update(status="error", error=str(error)[:200])
        return result

    def start_build(self, doc_id):
        doc = self._document(doc_id)
        with self._lock:
            if self._states.get(doc_id, {}).get("status") == "building":
                raise ValueError("The concept graph is already building.")
            token = object()
            self._jobs[doc_id] = token
            self._states[doc_id] = {"status": "building", "error": None,
                                    "progress": {"done": 0, "total": doc.n_chunks}}
            thread = threading.Thread(target=self._build, args=(doc, token), daemon=True,
                                      name=f"graph-{doc_id}")
            self.threads[doc_id] = thread
            thread.start()
            return thread

    def _build(self, doc, token):
        trace = None
        status = "error"
        totals = {"llm_calls": 0, "tokens": 0}

        def progress(done, total):
            with self._lock:
                if self._jobs.get(doc.id) is not token:
                    raise RuntimeError("The graph build was cancelled because its passages changed.")
                self._states[doc.id]["progress"] = {"done": done, "total": total}

        try:
            trace = self.tracer.start("indexing", {"graph_for": doc.filename})
            with trace.span("graph_build", chunks=doc.n_chunks, nodes=0, edges=0,
                            llm_calls=0, tokens=0, failures=0, model=get_model()) as span:
                data = self.store.collection.get(where={"doc_id": doc.id},
                                                 include=["documents", "metadatas"])
                rows = sorted(zip(data["ids"], data["documents"], data["metadatas"]),
                              key=lambda row: row[2]["chunk_index"])
                chunks = [{"chunk_id": chunk_id, "text": redact(text, names=False)[0]}
                          for chunk_id, text, _ in rows]
                progress(0, len(chunks))
                graph = build_graph(
                    chunks, llm=self.llm, prompt=GENERIC_PROMPT, extraction_model=GenericExtraction,
                    on_progress=progress,
                    delay_seconds=float(os.getenv("LLM_GRAPH_DELAY_SECONDS", "0")),
                )
                stats = graph["stats"]
                for key in ("chunks", "nodes", "edges", "llm_calls", "tokens", "failures", "model"):
                    span.set(key, stats[key])
                totals = {key: stats[key] for key in ("llm_calls", "tokens")}
                if graph["failures"] and len(graph["failures"]) == len(chunks):
                    raise RuntimeError(graph["failures"][0]["error"][:200])
                with self._lock:
                    progress(len(chunks), len(chunks))
                    self.graph_dir.mkdir(parents=True, exist_ok=True)
                    path = self._path(doc.id)
                    temporary = path.with_suffix(".json.tmp")
                    try:
                        temporary.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
                        temporary.replace(path)
                    finally:
                        temporary.unlink(missing_ok=True)
                self.on_change()
                with self._lock:
                    if self._jobs.get(doc.id) is token:
                        self._states.pop(doc.id, None)
                status = "ok"
        except Exception as error:
            logger.warning("Graph build for %s failed: %s", doc.id, error)
            with self._lock:
                if self._jobs.get(doc.id) is token:
                    state = self._states.setdefault(doc.id, {
                        "progress": {"done": 0, "total": doc.n_chunks}})
                    state.update(status="error", error=str(error)[:200] or "The graph build failed.")
        finally:
            if trace is not None:
                trace.finish(status, totals)

    def delete(self, doc_id):
        with self._lock:
            self._jobs.pop(doc_id, None)
            self._states.pop(doc_id, None)
            self._path(doc_id).unlink(missing_ok=True)

    def clear_all(self):
        with self._lock:
            self._jobs.clear()
            self._states.clear()
            for path in self.graph_dir.glob("*.json"):
                path.unlink()

    def all_graphs(self):
        with self._lock:
            paths = ([self.kestrel_graph_path] if self.kestrel_graph_path and self.kestrel_graph_path.exists()
                     else [])
            paths += sorted(self.graph_dir.glob("*.json"))
            return [json.loads(path.read_text(encoding="utf-8")) for path in paths]
