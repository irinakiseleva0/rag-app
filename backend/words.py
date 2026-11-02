"""Words analytics: which words the corpus contains, and where.

Tokenization (a deliberate, simple choice, see REPORT.md):
- lowercase;
- a word is a run of letters/digits, which may contain inner "-", "_", "." or "'"
  so that identifiers stay whole: KST-2044, 203.0.113.10, technical_bug, can't;
- punctuation around a word is dropped ("fix." -> "fix");
- no stemming: "invite" and "invitation" are different words (this is what
  keyword search would see);
- stop words are counted like any word, only flagged, so the UI can hide them.

Counts are per CHUNK, not per file: with overlap, a word that sits in the shared
part of two neighbouring chunks is counted in both. That is what retrieval sees.
"""

import re
from collections import Counter, defaultdict

TOKEN_RE = re.compile(r"[^\W_]+(?:[-_.'][^\W_]+)*")

STOP_WORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how i if in into is it its itself just me more most
my myself no nor not now of off on once only or other our ours ourselves out over own same she should
so some such than that the their theirs them themselves then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves
""".split())


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    return TOKEN_RE.findall(text)


def unique_in_order(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(tokens))


class WordIndex:
    """Inverted index over chunks: word -> {chunk_id: count}."""

    def __init__(self, chunks: list[dict]):
        # chunks: [{"chunk_id", "filename", "chunk_index", "text"}]
        self.chunks = {c["chunk_id"]: c for c in chunks}
        self.postings: dict[str, Counter] = defaultdict(Counter)
        for c in chunks:
            for word, n in Counter(tokenize(c["text"])).items():
                self.postings[word][c["chunk_id"]] = n

    def count(self, word: str) -> int:
        return sum(self.postings.get(word, {}).values())

    def n_chunks(self, word: str) -> int:
        return len(self.postings.get(word, {}))

    def vocabulary(self) -> list[dict]:
        rows = [{"word": w, "count": sum(p.values()), "n_chunks": len(p), "stop": w in STOP_WORDS}
                for w, p in self.postings.items()]
        return sorted(rows, key=lambda r: (-r["count"], r["word"]))

    def chunks_for(self, word: str, answer_ids: set[str] = frozenset(), with_text: bool = False) -> list[dict]:
        out = []
        for cid, n in sorted(self.postings.get(word, {}).items(), key=lambda kv: (-kv[1], kv[0])):
            c = self.chunks[cid]
            row = {"chunk_id": cid, "filename": c["filename"], "chunk_index": c["chunk_index"],
                   "count": n, "is_answer": cid in answer_ids}
            if with_text:
                row["text"] = c["text"]
            out.append(row)
        return out
