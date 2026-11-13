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
  advanced: boolean
  selectedIds: string[]
  topK: number | null
}

export function AskPanel({ advanced, selectedIds, topK }: Props) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retrievers, setRetrievers] = useState<NonNullable<AskRequest['retrievers']>>({
    dense: true, bm25: true, graph: true,
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
      const message = errorMessage(e)
      setError(
        e instanceof TypeError || /(?:cannot|can't|could not|unable to) reach (?:the )?(?:server|backend)|failed to fetch|network ?error|network request failed/i.test(message)
          ? 'The app cannot reach its server. Please check that the backend is running (see README), then try again.'
          : message,
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="ask" aria-labelledby="ask-title">
      <h2 id="ask-title">Ask the documents</h2>

      <form onSubmit={handleSubmit}>
        {advanced && <fieldset className="retriever-options" disabled={loading}>
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
        </fieldset>}
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the selected documents, for example: What happens when a card payment fails?"
          rows={3}
        />
        <div className="ask-actions">
          <button type="submit" disabled={loading || !!blockedReason || !question.trim()}>
            {loading ? 'Working…' : 'Ask'}
          </button>
          {blockedReason && <span className="muted small">{blockedReason}</span>}
          {!blockedReason && (
            <span className="muted small">
              Searching {selectedIds.length} document{selectedIds.length > 1 ? 's' : ''}
              {advanced && <>, top {topK} chunks</>}
            </span>
          )}
        </div>
      </form>

      {loading && (
        <p className="ask-progress muted small" role="status">
          <span className="spinner" aria-hidden="true" />
          Searching your documents and writing the answer. This usually takes a few seconds.
        </p>
      )}

      {error && (
        <div className="result error-box" role="alert">
          <strong>Something went wrong.</strong> {error}
        </div>
      )}

      {result && (
        <div className="result">
          {result.status === 'error' && (
            <div className="error-box" role="alert">
              Sorry, the answer could not be produced. Please try again in a moment.
              {advanced && result.error && <p className="muted small">{result.error}</p>}
            </div>
          )}
          {result.status === 'not_found' && (
            <div className="neutral-box">
              The selected documents do not contain an answer to this question.{' '}
              Try rephrasing the question or selecting other documents.
            </div>
          )}
          {result.status === 'answered' && <p className="answer">{result.answer}</p>}
          {advanced && <p className="retrieval-cost muted small">
            LLM calls: {result.cost.llm_calls} · tokens: {result.cost.tokens} · latency: {result.cost.latency_ms} ms
          </p>}
          {advanced && <GraphPath path={result.graph_path} />}
          {result.status === 'answered' && (
            <>
              <h3>Sources</h3>
              <ReferenceList references={result.references} advanced={advanced} />
            </>
          )}
        </div>
      )}
    </section>
  )
}
