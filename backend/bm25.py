import sqlite3
from pathlib import Path

from words import STOP_WORDS, tokenize


def bm25_tokens(text):
    tokens = []
    for t in tokenize(text):
        if t in STOP_WORDS:
            continue
        tokens.append(t.replace("'", ""))
    return tokens


class BM25Index:
    def __init__(self, path: Path):
        self.path = path
        with self.connect() as db:
            db.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                    tokens,
                    chunk_id UNINDEXED, doc_id UNINDEXED, filename UNINDEXED,
                    chunk_index UNINDEXED, char_start UNINDEXED, char_end UNINDEXED,
                    text UNINDEXED,
                    tokenize = "unicode61 tokenchars '-_.'"
                )"""
            )

    def connect(self):
        return sqlite3.connect(self.path)

    def add(self, rows):
        with self.connect() as db:
            db.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(" ".join(bm25_tokens(r["text"])), r["chunk_id"], r["doc_id"], r["filename"],
                  r["chunk_index"], r["char_start"], r["char_end"], r["text"]) for r in rows],
            )

    def delete_document(self, doc_id):
        with self.connect() as db:
            db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

    def clear(self):
        with self.connect() as db:
            db.execute("DELETE FROM chunks")

    def count(self):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def search(self, question, doc_ids, top_k):
        terms = list(dict.fromkeys(bm25_tokens(question)))
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)

        sql = ("SELECT chunk_id, filename, chunk_index, char_start, char_end, text, bm25(chunks) "
               "FROM chunks WHERE chunks MATCH ?")
        params = [match]
        if doc_ids:
            sql += f" AND doc_id IN ({', '.join('?' for _ in doc_ids)})"
            params += list(doc_ids)
        sql += " ORDER BY bm25(chunks) LIMIT ?"
        params.append(top_k)

        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [{"chunk_id": r[0], "filename": r[1], "chunk_index": r[2], "char_start": r[3],
                 "char_end": r[4], "text": r[5], "score": round(-r[6], 4)} for r in rows]
