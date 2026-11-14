import { useEffect, useId, useState } from 'react'
import { api } from '../api'
import type { Trace } from '../api'

const labels: Record<string, string> = {
  dense: 'Meaning search (dense)',
  bm25: 'Keyword search (BM25)',
  graph: 'Concept graph',
  rrf: 'Fusion (RRF)',
  llm: 'Answer generation (LLM)',
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
      item !== null && typeof item === 'object' && !Array.isArray(item))
    : []
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function display(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '—'
}

function SpanAttributes({ span }: { span: Trace['spans'][number] }) {
  const a = span.attributes
  if (['dense', 'bm25', 'graph'].includes(span.name)) {
    const candidates = records(a.candidates)
    return <>
      {span.name === 'graph' && <>
        <p>Entities: {strings(a.entities).join(', ') || 'None'}</p>
        <p>Edges followed: {display(a.edges_count)}</p>
      </>}
      {candidates.length === 0 ? <p>No candidates.</p> : (
        <ol className="trace-candidates">
          {candidates.slice(0, 10).map((candidate, i) => (
            <li key={i}>#{display(candidate.rank)} <code>{display(candidate.chunk_id)}</code></li>
          ))}
        </ol>
      )}
      {candidates.length > 10 && <p className="muted">… {candidates.length - 10} more</p>}
    </>
  }
  if (span.name === 'rrf') {
    const results = records(a.results)
    return <>
      <p>Top K: {display(a.top_k)}</p>
      {results.length === 0 ? <p>No results.</p> : <ul className="trace-items">
        {results.map((result, i) => <li key={i}>
          <code>{display(result.chunk_id)}</code> · RRF score {display(result.rrf_score)} · found by{' '}
          {records(result.found_by).map((found) => `${display(found.retriever)} #${display(found.rank)}`).join(', ') || 'None'}
        </li>)}
      </ul>}
    </>
  }
  if (span.name === 'llm') {
    return <>
      <p>Model: {display(a.model)}</p>
      <p>Tokens: {display(a.tokens)} · Status: {display(a.status)}</p>
      <p>Error: {display(a.error ?? 'None')}</p>
      <p>Chunks sent:</p>
      {strings(a.chunks_sent).length === 0 ? <p>None</p> : <ul className="trace-items">
        {strings(a.chunks_sent).map((id, i) => <li key={i}><code>{id}</code></li>)}
      </ul>}
    </>
  }
  return <pre className="trace-json">{JSON.stringify(a, null, 2)}</pre>
}

function TraceStep({ span, longest }: { span: Trace['spans'][number]; longest: number }) {
  const [open, setOpen] = useState(false)
  const detailsId = useId()
  const label = Object.hasOwn(labels, span.name) ? labels[span.name] : span.name
  const error = typeof span.attributes.error === 'string' ? span.attributes.error : null
  return <li className="trace-step">
    <div className="trace-step-row">
      <span className="trace-step-label">{label}</span>
      <span className="trace-duration">{span.duration_ms} ms</span>
      <button type="button" className="link-button" aria-expanded={open}
        aria-controls={detailsId} aria-label={`${open ? 'Hide' : 'Show'} ${label} details`}
        onClick={() => setOpen((value) => !value)}>
        {open ? 'Hide' : 'Show'}
      </button>
    </div>
    <div className="trace-bar-track" aria-hidden="true">
      <div className="trace-bar" style={{ width: `${longest > 0 ? span.duration_ms / longest * 100 : 0}%` }} />
    </div>
    {error !== null && <p className="trace-error">{error}</p>}
    <div id={detailsId} hidden={!open}>
      {open && <div className="trace-attributes"><SpanAttributes span={span} /></div>}
    </div>
  </li>
}

export function TraceDetails({ traceId }: { traceId: string }) {
  const [loaded, setLoaded] = useState<{ id: string; trace: Trace | null } | null>(null)

  useEffect(() => {
    let active = true
    api.getTrace(traceId).then(
      (trace) => { if (active) setLoaded({ id: traceId, trace }) },
      () => { if (active) setLoaded({ id: traceId, trace: null }) },
    )
    return () => { active = false }
  }, [traceId])

  if (loaded === null || loaded.id !== traceId) {
    return <p className="muted small" role="status">Loading details…</p>
  }
  if (loaded.trace === null) {
    return <p className="trace-error small" role="alert">The details of this answer could not be loaded.</p>
  }

  const trace = loaded.trace
  const longest = Math.max(0, ...trace.spans.map((span) => span.duration_ms))
  const started = new Date(trace.started_at)
  return <section className="trace-details" aria-label="Answer details">
    <p className="trace-summary small">
      Status: {trace.status} · Total: {trace.duration_ms} ms · LLM calls: {display(trace.totals.llm_calls)}
      {' '}· Tokens: {display(trace.totals.tokens)} ·{' '}
      {Number.isNaN(started.getTime()) ? display(trace.started_at)
        : <time dateTime={trace.started_at}>{started.toLocaleString()}</time>}
    </p>
    <ol className="trace-steps">
      {trace.spans.map((span, i) => <TraceStep key={`${trace.id}-${i}`} span={span} longest={longest} />)}
    </ol>
    <p className="trace-id muted small">Trace id: {trace.id}</p>
  </section>
}
