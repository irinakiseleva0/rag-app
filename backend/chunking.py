# Split a document into overlapping chunks.
# We keep start/end so that text[start:end] == chunk text (rule from API.md).


def split_text(text: str, chunk_size: int, overlap_percent: int) -> list[dict]:
    overlap = chunk_size * overlap_percent // 100
    step = max(1, chunk_size - overlap)  # must be > 0, otherwise infinite loop

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append({"index": len(chunks), "start": start, "end": end, "text": text[start:end]})
        if end == len(text):
            break
        start += step
    return chunks
