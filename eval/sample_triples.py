"""Pick 10 random triples from the graph and write them with their chunk text for hand grading."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from store import Store  # noqa: E402

graph = json.loads((ROOT / "backend/data/graph/kestrel_graph.json").read_text(encoding="utf-8"))
names = {n["id"]: n["name"] for n in graph["nodes"]}
store = Store(ROOT / "backend/data")
by_name = {d.filename: d.id for d in store.list_documents()}

random.seed(42)
sample = random.sample(graph["edges"], 10)

lines = ["# Extraction quality: 10 random triples (seed 42)", "",
         "Grades: correct / wrong / unsupported", ""]
for i, e in enumerate(sample, 1):
    cid = e["chunk_ids"][0]
    name, index = cid.rsplit("#", 1)
    text = store.collection.get(ids=[f"{by_name[name]}#{index}"], include=["documents"])["documents"][0]
    lines += [f"## {i}. ({names[e['source']]}) -{e['relation']}-> ({names[e['target']]})", "",
              f"Chunk: `{cid}`", "", "```", text.strip(), "```", "",
              "**Grade:** ", "", "**Why:** ", ""]
lines += ["## Counts", "", "correct: / wrong: / unsupported: ", ""]

out = ROOT / "eval/triple_grades.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out}")