import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_build import build_graph, load_kestrel_chunks, normalize_entity_name
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
    assert graph["stats"]["failures"] == 1
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


def test_resolution_ignores_type_and_records_all_types_in_order():
    graph = build_graph(chunks()[:1], llm=lambda prompt: response(
        triple("The   Messaging"), triple(" messaging "), triple("Messaging", "Service")
    ))
    assert len(graph["nodes"]) == 2
    assert len(graph["merges"]) == 1
    assert graph["merges"][0]["names"] == ["The   Messaging", " messaging ", "Messaging"]
    node = graph["nodes"][0]
    assert node["type"] == "Team"
    assert node["types"] == ["Team", "Service"]


def test_team_suffix_merges_names_and_keeps_provenance():
    replies = iter([response(triple("Platform team")), response(triple("Platform"))])
    graph = build_graph(chunks(), llm=lambda prompt: next(replies))
    assert len(graph["nodes"]) == 2
    node = graph["nodes"][0]
    assert node["types"] == ["Team"]
    assert node["chunk_ids"] == ["doc#0000", "doc#0001"]
    assert graph["merges"] == [{"node_id": node["id"], "names": ["Platform team", "Platform"]}]
    assert graph["stats"]["dropped"] == 0


def test_self_loop_is_dropped_after_normalization_even_with_different_types():
    item = triple("The Delivery team")
    graph = build_graph(chunks()[:1], llm=lambda prompt: response(item, triple()))
    assert graph["stats"]["dropped"] == 1
    assert graph["stats"]["llm_calls"] == 1
    assert graph["stats"]["failures"] == 0
    assert len(graph["edges"]) == 1
    assert len(graph["nodes"]) == 2
    assert all("The Delivery team" not in node["aliases"] for node in graph["nodes"])


@pytest.mark.parametrize("name", ["no", " YES ", "The none", "n/a", "post", "ab", "The X service"])
@pytest.mark.parametrize("endpoint", ["subject", "object"])
def test_invalid_normalized_names_are_dropped(name, endpoint):
    item = triple()
    item[endpoint]["name"] = name
    graph = build_graph(chunks()[:1], llm=lambda prompt: response(item))
    assert graph["nodes"] == graph["edges"] == []
    assert graph["stats"]["dropped"] == 1
    assert graph["failures"] == []


def test_normalization_removes_service_suffix():
    assert normalize_entity_name("  The   Delivery  Service ") == "delivery"


def test_raised_by_is_valid_and_prompt_includes_extraction_rules():
    item = {
        "subject": {"name": "KST-1234", "type": "ErrorCode"},
        "relation": "RAISED_BY",
        "object": {"name": "Delivery", "type": "Service"},
    }

    def fake_llm(prompt):
        assert "RAISED_BY" in prompt
        assert "named exactly as written" in prompt
        assert '"escalate to the team that owns <service>"' in prompt
        assert '"Owner: <team>" under a service heading' in prompt
        assert "subject and object are the same entity" in prompt
        assert "word fragments" in prompt
        return response(item)

    graph = build_graph(chunks()[:1], llm=fake_llm)
    assert graph["edges"][0]["relation"] == "RAISED_BY"


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
                    {"filename": "service-catalog.md", "chunk_index": 1},
                    {"filename": "product-guide.md", "chunk_index": 0},
                    {"filename": "other.md", "chunk_index": 0},
                ],
            }

    store = SimpleNamespace(collection=FakeCollection())
    assert load_kestrel_chunks(store, limit=1) == [{"chunk_id": "product-guide.md#0000", "text": "first"}]
    assert len(load_kestrel_chunks(store)) == 2
    assert load_kestrel_chunks(store, limit=0) == []


def test_empty_chunks_do_not_call_llm():
    def fake_llm(prompt):
        pytest.fail("Empty input must not call the LLM")

    graph = build_graph([], llm=fake_llm)
    assert graph["nodes"] == graph["edges"] == graph["merges"] == graph["failures"] == []
    assert graph["stats"]["chunks"] == graph["stats"]["llm_calls"] == graph["stats"]["tokens"] == 0
    assert graph["stats"]["seconds"] >= 0
    assert graph["stats"]["dropped"] == graph["stats"]["failures"] == 0
