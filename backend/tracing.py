"""Local traces containing request metadata and timings, never document bodies."""

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Span:
    def __init__(self, attributes):
        self.attributes = attributes

    def set(self, key, value):
        self.attributes[key] = value


class Trace:
    def __init__(self, tracer, kind, input):
        self.tracer = tracer
        self.id = uuid.uuid4().hex
        self.kind = kind
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.input = input
        self.spans = []
        self._start = time.perf_counter()

    @contextmanager
    def span(self, name, **attributes):
        start = time.perf_counter()
        span = Span(attributes)
        try:
            yield span
        except Exception as exc:
            span.set("error", f"{type(exc).__name__}: {exc}"[:200])
            raise
        finally:
            self.spans.append({
                "name": name,
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "attributes": span.attributes,
            })

    def finish(self, status, totals: dict):
        duration_ms = int((time.perf_counter() - self._start) * 1000)
        data = json.dumps({"input": self.input, "spans": self.spans, "totals": totals})
        with closing(sqlite3.connect(self.tracer.db_path)) as conn, conn:
            conn.execute(
                "INSERT OR REPLACE INTO traces VALUES (?, ?, ?, ?, ?, ?)",
                (self.id, self.kind, self.started_at, duration_ms, status, data),
            )
            conn.execute(
                "DELETE FROM traces WHERE id IN "
                "(SELECT id FROM traces ORDER BY started_at DESC, rowid DESC LIMIT -1 OFFSET ?)",
                (self.tracer.max_traces,),
            )


class Tracer:
    def __init__(self, db_path, max_traces=500):
        if max_traces < 0:
            raise ValueError("max_traces must be nonnegative")
        self.db_path = Path(db_path)
        self.max_traces = max_traces
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS traces "
                "(id TEXT PRIMARY KEY, kind TEXT, started_at TEXT, "
                "duration_ms INTEGER, status TEXT, data TEXT)"
            )

    def start(self, kind, input: dict) -> Trace:
        if kind not in {"question", "indexing"}:
            raise ValueError("Unknown trace kind")
        return Trace(self, kind, input)

    def get(self, trace_id):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM traces WHERE id = ?", (trace_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result.update(json.loads(result.pop("data")))
        return result

    def list(self, kind=None, limit=20):
        query = "SELECT id, kind, started_at, duration_ms, status FROM traces"
        params = []
        if kind is not None:
            query += " WHERE kind = ?"
            params.append(kind)
        query += " ORDER BY started_at DESC, rowid DESC LIMIT ?"
        params.append(max(0, limit))
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(query, params)]
