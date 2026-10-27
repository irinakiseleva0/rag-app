import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { AskResult } from '../api'
import { errorMessage } from '../errors'
import { ReferenceList } from './ReferenceList'

type Props = {
  selectedIds: string[]
  topK: number | null
}

export function AskPanel({ selectedIds, topK }: Props) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResult | null>(null)
  const [error, setError] = useState<string | null>(null)

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
      const res = await api.ask({ question: question.trim(), doc_ids: selectedIds, top_k: topK })
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

      {result?.status === 'error' && (
        <div className="result error-box" role="alert">
          <strong>The answer could not be produced.</strong> {result.error ?? 'Unknown error.'}
        </div>
      )}

      {result?.status === 'not_found' && (
        <div className="result neutral-box">
          The selected documents do not contain an answer to this question.
        </div>
      )}

      {result?.status === 'answered' && (
        <div className="result">
          <p className="answer">{result.answer}</p>
          <h3>References</h3>
          <ReferenceList references={result.references} />
        </div>
      )}
    </section>
  )
}
