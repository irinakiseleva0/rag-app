"""Link question entities and retrieve evidence within two graph hops."""

import json
import re
from collections import defaultdict, deque
from pathlib import Path

from schemas import Reference


def normalize(text):
    text = " ".join(text.lower().split())
    return text[4:] if text.startswith("the ") else text


class GraphRetriever:
    def __init__(self, graph_path, store):
        graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
        self.store = store
        self.nodes = {node["id"]: node for node in graph["nodes"]}
        self.edges = graph["edges"]
        self.names = {}
        self.adjacency = defaultdict(list)
        for node_id, node in self.nodes.items():
            names = {normalize(name) for name in [node["name"], *node.get("aliases", [])]}
            self.names[node_id] = [
                re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
                for name in sorted(names) if len(name) >= 3
            ]
        for index, edge in enumerate(self.edges):
            self.adjacency[edge["source"]].append(index)
            self.adjacency[edge["target"]].append(index)

    def search(self, question, doc_ids, n):
        question = normalize(question)
        found = [
            node_id for node_id, patterns in self.names.items()
            if any(pattern.search(question) for pattern in patterns)
        ]
        path = {"entities": [self.nodes[node_id]["name"] for node_id in found], "edges": []}
        result = {"chunks": [], "path": path, "llm_calls": 0, "tokens": 0}
        if not found:
            return result

        scores = defaultdict(float)
        for node_id in found:
            for chunk_id in self.nodes[node_id]["chunk_ids"]:
                scores[chunk_id] += 1.0

        # Multiple starting entities share a BFS, so each edge is scored once
        # at the shortest hop, including in cycles or overlapping neighborhoods.
        queue = deque((node_id, 0) for node_id in found)
        visited_nodes = set(found)
        visited_edges = set()
        while queue:
            node_id, distance = queue.popleft()
            if distance == 2:
                continue
            hop = distance + 1
            for index in self.adjacency[node_id]:
                if index in visited_edges:
                    continue
                visited_edges.add(index)
                edge = self.edges[index]
                for chunk_id in edge["chunk_ids"]:
                    scores[chunk_id] += 1 / (1 + hop)
                path["edges"].append({
                    "from": self.nodes[edge["source"]]["name"],
                    "relation": edge["relation"],
                    "to": self.nodes[edge["target"]]["name"],
                    "chunk_id": edge["chunk_ids"][0],
                })
                neighbor = edge["target"] if edge["source"] == node_id else edge["source"]
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    queue.append((neighbor, hop))

        allowed_docs = set(doc_ids)
        ranked = sorted(
            (chunk_id for chunk_id in scores
             if not allowed_docs or chunk_id.split("#", 1)[0] in allowed_docs),
            key=lambda chunk_id: (-scores[chunk_id], chunk_id),
        )[:max(0, n)]
        if not ranked:
            return result
        data = self.store.collection.get(ids=ranked, include=["documents", "metadatas"])
        rows = {
            chunk_id: (text, metadata)
            for chunk_id, text, metadata in zip(data["ids"], data["documents"], data["metadatas"])
        }
        for chunk_id in ranked:
            if chunk_id not in rows:
                continue
            text, metadata = rows[chunk_id]
            result["chunks"].append(Reference(
                chunk_id=chunk_id,
                filename=metadata["filename"],
                chunk_index=metadata["chunk_index"],
                char_start=metadata["char_start"],
                char_end=metadata["char_end"],
                text=text,
                score=round(scores[chunk_id], 4),
            ))
        return result
