import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from chunking import split_text
from schemas import DocumentInfo, Reference, Settings

DEFAULT_SETTINGS = Settings(chunk_size=800, overlap_percent=10, top_k=5)


class Store:
    def __init__(self, data_dir: Path, embedding_function=None):
        self.files_dir = data_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.docs_path = data_dir / "documents.json"
        self.settings_path = data_dir / "settings.json"
        self.embedding_function = embedding_function
        self.client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
        self.collection = self.get_collection()

    def get_collection(self):
        if self.embedding_function is None:
            return self.client.get_or_create_collection("chunks", metadata={"hnsw:space": "cosine"})
        return self.client.get_or_create_collection(
            "chunks", metadata={"hnsw:space": "cosine"}, embedding_function=self.embedding_function
        )

    def list_documents(self):
        if not self.docs_path.exists():
            return []
        data = json.loads(self.docs_path.read_text())
        return [DocumentInfo(**d) for d in data]

    def save_documents(self, docs):
        self.docs_path.write_text(json.dumps([d.model_dump() for d in docs], indent=2))

    def index_document(self, doc, text, settings):
        chunks = split_text(text, settings.chunk_size, settings.overlap_percent)
        ids = []
        texts = []
        metadatas = []
        for c in chunks:
            ids.append(f"{doc.id}#{c['index']:04d}")
            texts.append(c["text"])
            metadatas.append({
                "doc_id": doc.id,
                "filename": doc.filename,
                "chunk_index": c["index"],
                "char_start": c["start"],
                "char_end": c["end"],
            })
        self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
        return len(chunks)

    def add_document(self, filename, text):
        doc = DocumentInfo(
            id=uuid.uuid4().hex[:12],
            filename=filename,
            n_chunks=0,
            uploaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        path = self.files_dir / f"{doc.id}.txt"
        path.write_bytes(text.encode("utf-8"))
        doc.n_chunks = self.index_document(doc, text, self.get_settings())
        docs = self.list_documents()
        docs.append(doc)
        self.save_documents(docs)
        return doc

    def delete_document(self, doc_id):
        docs = self.list_documents()
        ids = [d.id for d in docs]
        if doc_id not in ids:
            return False
        self.collection.delete(where={"doc_id": doc_id})
        path = self.files_dir / f"{doc_id}.txt"
        if path.exists():
            path.unlink()
        docs = [d for d in docs if d.id != doc_id]
        self.save_documents(docs)
        return True

    def get_settings(self):
        if not self.settings_path.exists():
            return DEFAULT_SETTINGS
        return Settings(**json.loads(self.settings_path.read_text()))

    def update_settings(self, new):
        old = self.get_settings()
        self.settings_path.write_text(new.model_dump_json())
        if new.chunk_size != old.chunk_size or new.overlap_percent != old.overlap_percent:
            self.reindex_all(new)
        return new

    def reindex_all(self, settings):
        self.client.delete_collection("chunks")
        self.collection = self.get_collection()
        docs = self.list_documents()
        for doc in docs:
            path = self.files_dir / f"{doc.id}.txt"
            text = path.read_bytes().decode("utf-8")
            doc.n_chunks = self.index_document(doc, text, settings)
        self.save_documents(docs)

    def search(self, question, doc_ids, top_k):
        if self.collection.count() == 0:
            return []
        where = None
        if doc_ids:
            where = {"doc_id": {"$in": doc_ids}}
        result = self.collection.query(query_texts=[question], n_results=top_k, where=where)

        references = []
        for i in range(len(result["ids"][0])):
            meta = result["metadatas"][0][i]
            ref = Reference(
                chunk_id=result["ids"][0][i],
                filename=meta["filename"],
                chunk_index=meta["chunk_index"],
                char_start=meta["char_start"],
                char_end=meta["char_end"],
                text=result["documents"][0][i],
                score=round(1 - result["distances"][0][i], 4),
            )
            references.append(ref)
        return references