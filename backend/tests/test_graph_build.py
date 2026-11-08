import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_build import build_graph, load_kestrel_chunks
from graph_schema import Entity, Extraction


def triple(name="Messaging", entity_type="Team"):
    return {
        "subject": {"name": name, "type": entity_type},
        "relation": "OWNS",
        "object": {"name": "Delivery", "type": "Service"},
    }


def response(*triples):
    return json.dumps({"triples": triples})


def chunks():
    return [
        {"chunk_id": "doc#0000", "text": "Messaging owns Delivery."},
        {"chunk_id": "doc#0001", "text": "Messaging owns Delivery too."},
    ]


def test_names_merge_with_all_chunk_provenance():
    replies = iter([response(triple()), response(triple(" messaging "))])
    graph = build_graph(chunks(), llm=lambda prompt: next(replies))
    node = next(node for node in graph["nodes"] if node["type"] == "Team")
    assert len(graph["nodes"]) == 2
    assert node["chunk_ids"] == ["doc#0000", "doc#0001"]
    assert node["aliases"] == ["Messaging", " messaging "]
    assert graph["merges"] == [
        {"node_id": node["id"], "names": ["Messaging", " messaging "]}
    ]
    assert graph["stats"]["merges"] == 1


def test_invalid_json_retried_once_then_recorded_and_skipped():
    replies = iter([("invalid", 5), ("still invalid", 7), (response(triple()), 11)])
    prompts = []

    def fake_llm(prompt):
        prompts.append(prompt)
        return next(replies)

    graph = build_graph(chunks(), llm=fake_llm)
    assert len(prompts) == 3
    assert prompts[0] == prompts[1]
    assert graph["stats"]["llm_calls"] == 3
    assert graph["stats"]["tokens"] == 23
    assert graph["stats"]["chunks"] == 2
    assert len(graph["failures"]) == 1
    assert graph["failures"][0]["chunk_id"] == "doc#0000"
    assert graph["failures"][0]["error"]
    assert all(node["chunk_ids"] == ["doc#0001"] for node in graph["nodes"])


def test_edge_in_two_chunks_has_both_chunk_ids():
    graph = build_graph(chunks(), llm=lambda prompt: (response(triple(), triple()), 10))
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["relation"] == "OWNS"
    assert edge["chunk_ids"] == ["doc#0000", "doc#0001"]
    assert {edge["source"], edge["target"]} == {n["id"] for n in graph["nodes"]}
    assert graph["stats"]["tokens"] == 20


def test_schema_validation_failure_can_recover_on_retry():
    invalid = triple()
    invalid["relation"] = "INVENTED"
    replies = iter([response(invalid), response(triple())])
    graph = build_graph(chunks()[:1], llm=lambda prompt: next(replies))
    assert graph["stats"]["llm_calls"] == 2
    assert graph["failures"] == []
    assert len(graph["edges"]) == 1


def test_normalization_and_type_are_both_used_for_resolution():
    graph = build_graph(chunks()[:1], llm=lambda prompt: response(
        triple("The   Messaging"), triple(" messaging "), triple("Messaging", "Service")
    ))
    assert len(graph["nodes"]) == 3
    assert len(graph["merges"]) == 1
    assert graph["merges"][0]["names"] == ["The   Messaging", " messaging "]


@pytest.mark.parametrize("name", ["", "   "])
def test_entity_rejects_empty_name(name):
    with pytest.raises(ValidationError):
        Entity(name=name, type="Team")


def test_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        Extraction.model_validate_json(response(triple(entity_type="Organization")))


def test_load_filters_exact_kestrel_names_and_applies_limit_after_sorting():
    class FakeCollection:
        def get(self, **kwargs):
            filenames = kwargs["where"]["filename"]["$in"]
            assert len(filenames) == 5
            assert "service-catalog.md" in filenames
            assert kwargs["include"] == ["documents", "metadatas"]
            return {
                "ids": ["z#0001", "a#0000", "other#0000"],
                "documents": ["later", "first", "unrelated"],
                "metadatas": [
                    {"filename": "service-catalog.md"},
                    {"filename": "product-guide.md"},
                    {"filename": "other.md"},
                ],
            }

    store = SimpleNamespace(collection=FakeCollection())
    assert load_kestrel_chunks(store, limit=1) == [{"chunk_id": "a#0000", "text": "first"}]
    assert len(load_kestrel_chunks(store)) == 2
    assert load_kestrel_chunks(store, limit=0) == []


def test_empty_chunks_do_not_call_llm():
    def fake_llm(prompt):
        pytest.fail("Empty input must not call the LLM")

    graph = build_graph([], llm=fake_llm)
    assert graph["nodes"] == graph["edges"] == graph["merges"] == graph["failures"] == []
    assert graph["stats"]["chunks"] == graph["stats"]["llm_calls"] == graph["stats"]["tokens"] == 0
    assert graph["stats"]["seconds"] >= 0
