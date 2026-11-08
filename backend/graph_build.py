"""Extract a provenance-aware concept graph from indexed Kestrel chunks."""

import argparse
import json
import logging
import os
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from graph_schema import EntityType, Extraction, RelationType

BACKEND_DIR = Path(__file__).resolve().parent
KESTREL_DIR = BACKEND_DIR.parent / "docs" / "kestrel"
OUTPUT_PATH = BACKEND_DIR / "data" / "graph" / "kestrel_graph.json"
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"
logger = logging.getLogger(__name__)

PROMPT = """Extract concept triples explicitly stated in the chunk below.
Use only this chunk's text. Do not infer facts or use outside knowledge.
Allowed entity types: {entity_types}
Allowed relations: {relations}
Return JSON with a triples list. Each triple has subject and object entities
(each with name and type), and a relation from the allowed list.
Preserve entity names as stated. Return {{"triples": []}} if none are stated.

Rules:
- Every error code like KST-1234 mentioned in the chunk is an ErrorCode entity
  named exactly as written.
- "raised by <service>" -> (ErrorCode) RAISED_BY (Service).
- "escalate to the team that owns <service>" -> (ErrorCode) ESCALATES_TO (Service <service>).
- "Owner: <team>" under a service heading -> (Team) OWNS (Service).
- Never output a triple whose subject and object are the same entity.
- Entity names must be full names written in the chunk, never words like
  "no", "yes", "none", or word fragments.

Chunk [{chunk_id}]:
{text}
"""


def call_gemini(prompt):
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set in backend/.env")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=Extraction,
        ),
    )
    tokens = 0
    if response.usage_metadata:
        tokens = response.usage_metadata.total_token_count or 0
    return response.text or "", tokens


def load_kestrel_chunks(store, limit=None):
    """Select exact corpus filenames and give limits a stable chunk order."""
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")
    filenames = sorted(path.name for path in KESTREL_DIR.iterdir() if path.is_file())
    if not filenames:
        raise ValueError(f"No Kestrel documents found in {KESTREL_DIR}")
    result = store.collection.get(
        where={"filename": {"$in": filenames}},
        include=["documents", "metadatas"],
    )
    chunks = [
        {"chunk_id": f"{metadata['filename']}#{metadata['chunk_index']:04d}", "text": text}
        for text, metadata in zip(result["documents"], result["metadatas"])
        if metadata and metadata.get("filename") in filenames
    ]
    chunks.sort(key=lambda chunk: chunk["chunk_id"])
    return chunks if limit is None else chunks[:limit]


def normalize_entity_name(name):
    name = " ".join(name.lower().split())
    if name.startswith("the "):
        name = name[4:]
    for suffix in (" team", " service"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return name


def entity_key(entity):
    return normalize_entity_name(entity.name)


def build_graph(chunks, llm=call_gemini):
    """Build in memory; llm(prompt) returns JSON text or (JSON text, tokens)."""
    started = perf_counter()
    nodes = {}
    edges = {}
    failures = []
    chunk_count = llm_calls = tokens = dropped = 0

    def resolve(entity, chunk_id):
        key = entity_key(entity)
        if key not in nodes:
            nodes[key] = {
                "id": f"n{len(nodes) + 1}",
                "name": entity.name,
                "type": entity.type.value,
                "types": [],
                "aliases": [],
                "chunk_ids": [],
            }
        node = nodes[key]
        if entity.type.value not in node["types"]:
            node["types"].append(entity.type.value)
        if entity.name not in node["aliases"]:
            node["aliases"].append(entity.name)
        if chunk_id not in node["chunk_ids"]:
            node["chunk_ids"].append(chunk_id)
        return node["id"]

    for chunk in chunks:
        chunk_count += 1
        chunk_id = chunk["chunk_id"]
        prompt = PROMPT.format(
            entity_types=", ".join(item.value for item in EntityType),
            relations=", ".join(item.value for item in RelationType),
            chunk_id=chunk_id,
            text=chunk["text"],
        )
        extraction = None
        for attempt in range(2):
            llm_calls += 1
            try:
                raw = llm(prompt)
            except Exception as error:
                failures.append({"chunk_id": chunk_id, "error": str(error)})
                logger.warning("Chunk %s: %s", chunk_id, error)
                break
            if isinstance(raw, tuple):
                raw, used_tokens = raw
                tokens += used_tokens
            try:
                extraction = Extraction.model_validate_json(raw)
                break
            except ValidationError as error:
                if attempt == 1:
                    failures.append({"chunk_id": chunk_id, "error": str(error)})
                    logger.warning("Chunk %s: %s", chunk_id, error)
        if extraction is None:
            continue
        for triple in extraction.triples:
            subject_key = entity_key(triple.subject)
            object_key = entity_key(triple.object)
            if subject_key == object_key or any(
                len(name) < 3 or name in {"no", "yes", "none", "n/a", "post"}
                for name in (subject_key, object_key)
            ):
                dropped += 1
                continue
            source = resolve(triple.subject, chunk_id)
            target = resolve(triple.object, chunk_id)
            relation = triple.relation.value
            key = source, relation, target
            if key not in edges:
                edges[key] = {
                    "source": source, "relation": relation, "target": target,
                    "chunk_ids": [],
                }
            if chunk_id not in edges[key]["chunk_ids"]:
                edges[key]["chunk_ids"].append(chunk_id)

    node_list = list(nodes.values())
    merges = [
        {"node_id": node["id"], "names": list(node["aliases"])}
        for node in node_list if len(node["aliases"]) > 1
    ]
    return {
        "nodes": node_list,
        "edges": list(edges.values()),
        "merges": merges,
        "failures": failures,
        "stats": {
            "chunks": chunk_count, "nodes": len(nodes), "edges": len(edges),
            "merges": len(merges), "llm_calls": llm_calls, "tokens": tokens,
            "dropped": dropped, "failures": len(failures),
            "seconds": perf_counter() - started,
            "model": os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        },
    }


def main():
    from dotenv import load_dotenv
    from store import Store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Process only the first N chunks")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    load_dotenv(BACKEND_DIR / ".env")
    started = perf_counter()
    store = Store(BACKEND_DIR / "data")
    graph = build_graph(load_kestrel_chunks(store, args.limit))
    graph["stats"]["seconds"] = perf_counter() - started
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(graph["stats"], indent=2))


if __name__ == "__main__":
    main()
