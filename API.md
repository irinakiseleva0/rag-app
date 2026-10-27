# API contract (V1)

Base URL (dev): `http://127.0.0.1:8000`. All bodies are JSON unless noted.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/documents` | – | `DocumentInfo[]` |
| POST | `/documents` | multipart, field `file` (`.md` / `.txt`) | `DocumentInfo` |
| DELETE | `/documents/{id}` | – | `{"deleted": true}` |
| GET | `/settings` | – | `Settings` |
| PUT | `/settings` | `Settings` | `Settings` (changing `chunk_size` or `overlap_percent` re-indexes all documents) |
| POST | `/retrieve` | `{question, doc_ids, top_k}` | `{"chunks": Reference[]}` (no LLM call, used by the eval script) |
| POST | `/ask` | `{question, doc_ids, top_k}` | `AskResult` |

## Types

```
DocumentInfo = {id: str, filename: str, n_chunks: int, uploaded_at: str (ISO 8601)}
Settings     = {chunk_size: int, overlap_percent: int, top_k: int}
Reference    = {chunk_id: str, filename: str, chunk_index: int,
                char_start: int, char_end: int, text: str, score: float}
AskResult    = {status: "answered" | "not_found" | "error",
                answer: str,
                references: Reference[],
                error: str | null}
```

- `chunk_id` format: `{doc_id}#{index:04d}`.
- `text[char_start:char_end]` of the original file equals `Reference.text`.
- `references` only contains chunks that were actually retrieved for this question.
- `score` is the similarity score, not a confidence.

## Errors

HTTP 4xx/5xx with `{"detail": "human readable message"}`:
400 wrong extension, empty file, or not UTF-8 · 404 unknown document id ·
413 file too large · 422 invalid request body.

`/ask` never crashes on a bad LLM response: it returns `status: "error"` with a message.
