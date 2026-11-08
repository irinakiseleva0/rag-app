import time

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


def hybrid_search(store, req, graph=None):
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
        lists["dense"] = store.search(req.question, req.doc_ids, n)
    if on.bm25:
        lists["bm25"] = store.bm25_search(req.question, req.doc_ids, n)
    if on.graph:
        result = graph.search(req.question, req.doc_ids, n)
        lists["graph"] = result["chunks"]
        graph_path = result.get("path")
        llm_calls += result.get("llm_calls", 0)
        tokens += result.get("tokens", 0)

    chunks = rrf(lists, req.top_k)
    ms = int((time.perf_counter() - start) * 1000)
    return chunks, graph_path, Cost(llm_calls=llm_calls, tokens=tokens, latency_ms=ms)
