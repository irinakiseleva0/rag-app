# API contract V3

Same endpoints as V2 (`POST /retrieve`, `POST /ask`). New fields are optional, so the V2 front and eval still work (default = dense + BM25, our default configuration, see REPORT.md).

## Request

```json
{
  "question": "What does error KST-2044 mean?",
  "doc_ids": ["d6be19330e67"],
  "top_k": 5,
  "retrievers": { "dense": true, "bm25": true, "graph": false },
  "candidates": 20
}
```

- `retrievers`: at least one must be on, otherwise 400.
- `candidates`: how many chunks each retriever gives before fusion (default 20).
- `graph: true` returns 400 if `backend/data/graph/kestrel_graph.json` is missing.

## Response (`/ask`)

```json
{
  "status": "answered",
  "answer": "...",
  "references": [
    {
      "chunk_id": "d6be19330e67#0003",
      "filename": "support-runbook-errors.md",
      "chunk_index": 3, "char_start": 2160, "char_end": 2960,
      "text": "...",
      "score": 0.61,
      "rrf_score": 0.03252,
      "found_by": [
        { "retriever": "dense", "rank": 3 },
        { "retriever": "bm25", "rank": 1 }
      ]
    }
  ],
  "error": null,
  "graph_path": null,
  "cost": { "llm_calls": 1, "tokens": 1840, "latency_ms": 920 }
}
```

- `score` is the score of the first retriever that found the chunk (cosine for dense, BM25 for bm25). Use `rrf_score` for the order.
- `/retrieve` returns `{ "chunks": [...], "graph_path": ..., "cost": ... }` with the same chunk format.
- `graph_path` is `null` when the graph is off. When on: `{ "entities": [...], "edges": [{ "from", "relation", "to", "chunk_id" }] }`.

## Graph retriever

`backend/main.py` loads `backend/data/graph/kestrel_graph.json` if it exists. The retriever has:

```python
def search(self, question, doc_ids, n):
    return {"chunks": [Reference, ...], "path": {...}, "llm_calls": 0, "tokens": 0}
```

In the graph file, chunks are stored as `<filename>#0003` (doc ids are random and change at every upload). The retriever maps them back to the local `<doc_id>#0003`.
