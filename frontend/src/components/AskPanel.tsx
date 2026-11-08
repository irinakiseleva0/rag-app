import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { AskRequest, AskResult } from '../api'
import { errorMessage } from '../errors'
import { ReferenceList } from './ReferenceList'
import { GraphPath } from './GraphPath'

const retrieverOptions = [
  { key: 'dense', label: 'Dense' },
  { key: 'bm25', label: 'BM25' },
  { key: 'graph', label: 'Graph' },
] as const

type Props = {
  selectedIds: string[]
  topK: number | null
}

export function AskPanel({ selectedIds, topK }: Props) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retrievers, setRetrievers] = useState<NonNullable<AskRequest['retrievers']>>({
    dense: true, bm25: true, graph: false,
  })
  const enabledCount = Object.values(retrievers).filter(Boolean).length

  const blockedReason =
    selectedIds.length === 0
      ? 'Select at least one document to ask a question.'
      : topK === null
        ? 'Settings are not loaded yet.'
        : null

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (blockedReason || topK === null || !question.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.ask({ question: question.trim(), doc_ids: selectedIds, top_k: topK, retrievers })
      setResult(res)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="ask" aria-labelledby="ask-title">
      <h2 id="ask-title">Ask the documents</h2>

      <form onSubmit={handleSubmit}>
        <fieldset className="retriever-options" disabled={loading}>
          <legend>Retrievers</legend>
          {retrieverOptions.map(({ key, label }) => (
            <label className="retriever-option" key={key}>
              <input
                type="checkbox"
                checked={retrievers[key]}
                disabled={retrievers[key] && enabledCount === 1}
                onChange={(event) => setRetrievers((current) => ({
                  ...current, [key]: event.target.checked,
                }))}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="For example: how does password reset work?"
          rows={3}
        />
        <div className="ask-actions">
          <button type="submit" disabled={loading || !!blockedReason || !question.trim()}>
            {loading ? 'Searching…' : 'Ask'}
          </button>
          {blockedReason && <span className="muted small">{blockedReason}</span>}
          {!blockedReason && (
            <span className="muted small">
              Searching {selectedIds.length} document{selectedIds.length > 1 ? 's' : ''}, top {topK}{' '}
              chunks
            </span>
          )}
        </div>
      </form>

      {error && (
        <div className="result error-box" role="alert">
          <strong>Something went wrong.</strong> {error}
        </div>
      )}

      {result && (
        <div className="result">
          {result.status === 'error' && (
            <div className="error-box" role="alert">
              <strong>The answer could not be produced.</strong> {result.error ?? 'Unknown error.'}
            </div>
          )}
          {result.status === 'not_found' && (
            <div className="neutral-box">
              The selected documents do not contain an answer to this question.
            </div>
          )}
          {result.status === 'answered' && <p className="answer">{result.answer}</p>}
          <p className="retrieval-cost muted small">
            LLM calls: {result.cost.llm_calls} · tokens: {result.cost.tokens} · latency: {result.cost.latency_ms} ms
          </p>
          <GraphPath path={result.graph_path} />
          {result.status === 'answered' && (
            <>
              <h3>References</h3>
              <ReferenceList references={result.references} />
            </>
          )}
        </div>
      )}
    </section>
  )
}
