import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_retriever import GraphRetriever
from retrieval import hybrid_search
from schemas import QuestionRequest, Retrievers


class FakeCollection:
    def __init__(self, chunk_ids):
        self.chunk_ids = set(chunk_ids)
        self.calls = []

    def get(self, ids, include):
        self.calls.append((ids, include))
        assert include == ["documents", "metadatas"]
        # Chroma need not return requested order; omit missing chunks.
        present = [chunk_id for chunk_id in reversed(ids) if chunk_id in self.chunk_ids]
        return {
            "ids": present,
            "documents": [f"Text for {chunk_id}" for chunk_id in present],
            "metadatas": [
                {"filename": "runbook.md", "chunk_index": int(chunk_id.split("#")[1]),
                 "char_start": 10, "char_end": 30}
                for chunk_id in present
            ],
        }


@pytest.fixture
def graph():
    return {
        "nodes": [
            {"id": "error", "name": "KST-2044", "type": "ErrorCode",
             "aliases": ["The   Delivery   Failure"], "chunk_ids": ["a#0000"]},
            {"id": "service", "name": "Delivery", "type": "Service",
             "aliases": [], "chunk_ids": ["b#0000"]},
            {"id": "team", "name": "Messaging", "type": "Team",
             "aliases": [], "chunk_ids": ["b#0001"]},
            {"id": "person", "name": "Alex", "type": "Person",
             "aliases": ["Al"], "chunk_ids": ["c#0000"]},
        ],
        "edges": [
            {"source": "service", "relation": "APPLIES_TO", "target": "error",
             "chunk_ids": ["a#0001"]},
            {"source": "team", "relation": "OWNS", "target": "service",
             "chunk_ids": ["b#0001", "b#0002"]},
            {"source": "person", "relation": "MEMBER_OF", "target": "team",
             "chunk_ids": ["c#0000"]},
        ],
    }


def retriever(tmp_path, graph, missing=()):
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    chunk_ids = {
        chunk_id for item in graph["nodes"] + graph["edges"] for chunk_id in item["chunk_ids"]
    }
    store = SimpleNamespace(collection=FakeCollection(chunk_ids - set(missing)))
    return GraphRetriever(graph_path, store)


def test_reverse_edges_reach_two_hops_and_stop(tmp_path, graph):
    result = retriever(tmp_path, graph).search("What does KST-2044 mean?", [], 10)
    assert [ref.chunk_id for ref in result["chunks"]] == [
        "a#0000", "a#0001", "b#0001", "b#0002", "b#0000"
    ]
    assert result["path"] == {
        "entities": ["KST-2044"],
        "edges": [
            {"from": "Delivery", "relation": "APPLIES_TO", "to": "KST-2044", "chunk_id": "a#0001"},
            {"from": "Messaging", "relation": "OWNS", "to": "Delivery", "chunk_id": "b#0001"},
        ],
    }
    assert result["llm_calls"] == result["tokens"] == 0


def test_no_entity_returns_empty_without_chroma_call(tmp_path, graph):
    searcher = retriever(tmp_path, graph)
    assert searcher.search("How can I sign in?", [], 10) == {
        "chunks": [], "path": {"entities": [], "edges": []}, "llm_calls": 0, "tokens": 0
    }
    assert searcher.store.collection.calls == []


def test_document_filter_runs_before_limit(tmp_path, graph):
    searcher = retriever(tmp_path, graph)
    result = searcher.search("KST-2044", ["b"], 1)
    assert [ref.chunk_id for ref in result["chunks"]] == ["b#0001"]
    assert searcher.search("KST-2044", ["unknown"], 10)["chunks"] == []


def test_ranking_hop_scores_ties_and_reference_metadata(tmp_path, graph):
    refs = retriever(tmp_path, graph).search("KST-2044", [], 10)["chunks"]
    assert [(ref.chunk_id, ref.score) for ref in refs] == [
        ("a#0000", 1.0), ("a#0001", 0.5), ("b#0001", 0.5),
        ("b#0002", 0.3333), ("b#0000", 0.25)
    ]
    assert refs[0].filename == "runbook.md"
    assert refs[0].chunk_index == 0
    assert (refs[0].char_start, refs[0].char_end) == (10, 30)
    assert refs[0].text == "Text for a#0000"


def test_alias_normalization_matches_whole_phrase(tmp_path, graph):
    result = retriever(tmp_path, graph).search(" THE   delivery   failure! ", [], 10)
    assert result["path"]["entities"] == ["KST-2044", "Delivery"]


@pytest.mark.parametrize("question", ["KST-20440", "xKST-2044", "MessagingPlus", "Al"])
def test_partial_names_and_short_aliases_do_not_link(tmp_path, graph, question):
    result = retriever(tmp_path, graph).search(question, [], 10)
    assert result["path"] == {"entities": [], "edges": []}


def test_missing_chroma_chunks_are_skipped(tmp_path, graph):
    refs = retriever(tmp_path, graph, missing=["a#0000"]).search("KST-2044", [], 10)["chunks"]
    assert [ref.chunk_id for ref in refs] == ["a#0001", "b#0001", "b#0002", "b#0000"]


def test_multiple_seeds_score_each_edge_once_at_shortest_hop(tmp_path, graph):
    result = retriever(tmp_path, graph).search("KST-2044 and Delivery", [], 10)
    scores = {ref.chunk_id: ref.score for ref in result["chunks"]}
    assert scores == {"a#0000": 1.0, "b#0000": 1.0, "a#0001": 0.5,
                      "b#0001": 0.75, "b#0002": 0.5, "c#0000": 0.5}
    assert len(result["path"]["edges"]) == 3


def test_node_and_edge_contributions_sum(tmp_path, graph):
    graph["edges"][0]["chunk_ids"].append("a#0000")
    result = retriever(tmp_path, graph).search("KST-2044", [], 10)
    assert result["chunks"][0].score == 1.5


def test_reached_node_contributes_its_own_chunks_at_each_hop(tmp_path, graph):
    graph["nodes"][2]["chunk_ids"] = ["b#0003"]
    result = retriever(tmp_path, graph).search("KST-2044", [], 10)
    scores = {ref.chunk_id: ref.score for ref in result["chunks"]}
    assert scores["b#0000"] == 0.25
    assert scores["b#0003"] == 0.1667
    assert "c#0000" not in scores


def test_linking_uses_shared_team_and_service_normalization(tmp_path, graph):
    graph["nodes"][2]["name"] = "The Messaging team"
    graph["nodes"][1]["aliases"] = ["The Courier service"]
    searcher = retriever(tmp_path, graph)
    assert searcher.search("Messaging", [], 10)["path"]["entities"] == ["The Messaging team"]
    assert searcher.search("Courier", [], 10)["path"]["entities"] == ["Delivery"]


def test_graph_integrates_with_hybrid_search(tmp_path, graph):
    searcher = retriever(tmp_path, graph)
    request = QuestionRequest(question="KST-2044", top_k=3,
                              retrievers=Retrievers(dense=False, graph=True))
    refs, path, cost = hybrid_search(searcher.store, request, searcher)
    assert [ref.chunk_id for ref in refs] == ["a#0000", "a#0001", "b#0001"]
    assert all(ref.found_by[0].retriever == "graph" for ref in refs)
    assert path["entities"] == ["KST-2044"]
    assert cost.llm_calls == cost.tokens == 0
