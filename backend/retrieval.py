import time
from contextlib import nullcontext

from schemas import Cost, Found

RRF_K = 60


def rrf(lists, top_k):
    scores = {}
    found = {}
    refs = {}
    for name, ranked in lists.items():
        for rank, ref in enumerate(ranked, start=1):
            scores[ref.chunk_id] = scores.get(ref.chunk_id, 0) + 1 / (RRF_K + rank)
            found.setdefault(ref.chunk_id, []).append(Found(retriever=name, rank=rank))
            refs.setdefault(ref.chunk_id, ref)

    best = sorted(scores, key=lambda cid: -scores[cid])[:top_k]
    out = []
    for cid in best:
        ref = refs[cid].model_copy()
        ref.found_by = found[cid]
        ref.rrf_score = round(scores[cid], 5)
        out.append(ref)
    return out


def hybrid_search(store, req, graph=None, trace=None):
    start = time.perf_counter()
    on = req.retrievers
    if not (on.dense or on.bm25 or on.graph):
        raise ValueError("At least one retriever must be on.")
    if on.graph and graph is None:
        raise ValueError("The graph retriever is not available (graph not built).")

    n = max(req.candidates, req.top_k)
    lists = {}
    graph_path = None
    llm_calls = 0
    tokens = 0
    if on.dense:
        with trace.span("dense") if trace is not None else nullcontext() as span:
            lists["dense"] = store.search(req.question, req.doc_ids, n)
            if span is not None:
                span.set("candidates", [
                    {"chunk_id": ref.chunk_id, "rank": rank}
                    for rank, ref in enumerate(lists["dense"], 1)
                ])
    if on.bm25:
        with trace.span("bm25") if trace is not None else nullcontext() as span:
            lists["bm25"] = store.bm25_search(req.question, req.doc_ids, n)
            if span is not None:
                span.set("candidates", [
                    {"chunk_id": ref.chunk_id, "rank": rank}
                    for rank, ref in enumerate(lists["bm25"], 1)
                ])
    if on.graph:
        with trace.span("graph") if trace is not None else nullcontext() as span:
            result = graph.search(req.question, req.doc_ids, n)
            if span is not None:
                path = result.get("path") or {}
                span.set("candidates", [
                    {"chunk_id": ref.chunk_id, "rank": rank}
                    for rank, ref in enumerate(result["chunks"], 1)
                ])
                span.set("entities", path.get("entities", []))
                span.set("edges_count", len(path.get("edges", [])))
        lists["graph"] = result["chunks"]
        graph_path = result.get("path")
        llm_calls += result.get("llm_calls", 0)
        tokens += result.get("tokens", 0)

    with trace.span("rrf", top_k=req.top_k) if trace is not None else nullcontext() as span:
        chunks = rrf(lists, req.top_k)
        if span is not None:
            span.set("results", [
                {"chunk_id": ref.chunk_id, "rrf_score": ref.rrf_score,
                 "found_by": [found.model_dump() for found in ref.found_by]}
                for ref in chunks
            ])
    ms = int((time.perf_counter() - start) * 1000)
    return chunks, graph_path, Cost(llm_calls=llm_calls, tokens=tokens, latency_ms=ms)
