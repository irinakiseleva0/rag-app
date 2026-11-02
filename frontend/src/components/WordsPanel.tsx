import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api } from '../api'
import type { QuestionWords, SetQuestion, Vocabulary, WordDetail } from '../api'
import { errorMessage } from '../errors'

type Props = { docIds: string[] }

const MAX_ROWS = 200

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Highlights whole-word occurrences (same idea as the backend tokenizer).
function highlight(text: string, word: string): ReactNode[] {
  const re = new RegExp(`(?<![\\p{L}\\p{N}])(${escapeRegExp(word)})(?![\\p{L}\\p{N}])`, 'giu')
  return text.split(re).map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part))
}

function WordChunks({ detail }: { detail: WordDetail }) {
  const [open, setOpen] = useState<string | null>(null)
  if (detail.count === 0) {
    return <p className="error-text">“{detail.word}” does not appear in the selected documents.</p>
  }
  return (
    <div className="result wide">
      <p>
        <strong>{detail.word}</strong>: {detail.count} occurrence{detail.count > 1 ? 's' : ''} in{' '}
        {detail.n_chunks} chunk{detail.n_chunks > 1 ? 's' : ''}
        {detail.stop && <span className="muted small"> (stop word)</span>}
      </p>
      <ol className="references">
        {detail.chunks.map((c) => {
          const isOpen = open === c.chunk_id
          return (
            <li key={c.chunk_id}>
              <button type="button" className="reference-toggle" aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : c.chunk_id)}>
                <span className="ref-file">{c.filename}</span>
                <span className="muted small">chunk {c.chunk_index} · {c.count}×</span>
              </button>
              {isOpen && c.text && <pre className="chunk-text">{highlight(c.text, detail.word)}</pre>}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function WordsPanel({ docIds }: Props) {
  const [mode, setMode] = useState<'corpus' | 'question'>('corpus')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // corpus mode
  const [vocab, setVocab] = useState<Vocabulary | null>(null)
  const [filter, setFilter] = useState('')
  const [hideStop, setHideStop] = useState(true)
  const [wordInput, setWordInput] = useState('')
  const [detail, setDetail] = useState<WordDetail | null>(null)

  // question mode
  const [setQuestions, setSetQuestions] = useState<SetQuestion[]>([])
  const [picked, setPicked] = useState('')
  const [questionText, setQuestionText] = useState('')
  const [analysis, setAnalysis] = useState<QuestionWords | null>(null)

  const docKey = docIds.join(',')
  const noDocs = docIds.length === 0

  const loadVocabulary = useCallback(async () => {
    if (noDocs) return
    setBusy(true)
    setError(null)
    try {
      setVocab(await api.vocabulary(docKey.split(',')))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }, [docKey, noDocs])

  // Initial load. The parent remounts this panel (key) when the selected documents change.
  useEffect(() => {
    if (noDocs) return
    api.vocabulary(docKey.split(',')).then(setVocab).catch((e: unknown) => setError(errorMessage(e)))
  }, [docKey, noDocs])

  useEffect(() => {
    api.listSetQuestions().then(setSetQuestions).catch(() => setSetQuestions([]))
  }, [])

  const rows = useMemo(() => {
    if (!vocab) return []
    const f = filter.trim().toLowerCase()
    return vocab.words.filter((w) => (!hideStop || !w.stop) && (!f || w.word.includes(f)))
  }, [vocab, filter, hideStop])

  async function showWord(word: string) {
    if (noDocs || !word.trim()) return
    setBusy(true)
    setError(null)
    try {
      setDetail(await api.wordDetail(word.trim(), docIds))
      setWordInput(word.trim())
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  function pickQuestion(value: string) {
    setPicked(value)
    const q = setQuestions.find((x) => `${x.set_name}:${x.id}` === value)
    if (q) setQuestionText(q.question)
  }

  async function analyze(event: FormEvent) {
    event.preventDefault()
    if (noDocs) return
    const q = setQuestions.find((x) => `${x.set_name}:${x.id}` === picked)
    setBusy(true)
    setError(null)
    setDetail(null)
    try {
      setAnalysis(await api.questionWords({
        doc_ids: docIds,
        question: questionText,
        ...(q && q.question === questionText ? { set_name: q.set_name, question_id: q.id } : {}),
      }))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="ask" aria-labelledby="words-title">
      <h2 id="words-title">Words</h2>
      <p className="muted small">
        Words of the <strong>selected documents</strong>, counted per chunk with the current chunk
        settings. Lowercase, identifiers like KST-2044 kept whole, no stemming.
      </p>

      <div className="tabs small-tabs" role="tablist" aria-label="Words mode">
        <button type="button" role="tab" aria-selected={mode === 'corpus'} onClick={() => setMode('corpus')}>
          Corpus
        </button>
        <button type="button" role="tab" aria-selected={mode === 'question'} onClick={() => setMode('question')}>
          Question
        </button>
      </div>

      {noDocs && <p className="muted">Select at least one document in the left panel.</p>}
      {error && <div className="result error-box" role="alert"><strong>Error.</strong> {error}</div>}

      {mode === 'corpus' && !noDocs && (
        <>
          <form className="ask-actions" onSubmit={(e) => { e.preventDefault(); void showWord(wordInput) }}>
            <input className="inline-input" placeholder="Word → chunks, e.g. allowlist"
              value={wordInput} onChange={(e) => setWordInput(e.target.value)} />
            <button type="submit" disabled={busy || !wordInput.trim()}>Find chunks</button>
          </form>
          {detail && <WordChunks detail={detail} />}

          <h3>Vocabulary</h3>
          {vocab ? (
            <>
              <p className="muted small">
                {vocab.n_distinct} distinct words · {vocab.n_tokens} occurrences · {vocab.n_chunks} chunks
              </p>
              <div className="ask-actions">
                <input className="inline-input" placeholder="Filter words" value={filter}
                  onChange={(e) => setFilter(e.target.value)} />
                <label className="check">
                  <input type="checkbox" checked={hideStop} onChange={(e) => setHideStop(e.target.checked)} />
                  Hide stop words
                </label>
                <button type="button" className="link-button" onClick={() => void loadVocabulary()}>Refresh</button>
              </div>
              <div className="table-scroll vocab">
                <table className="scores">
                  <thead>
                    <tr><th scope="col">Word</th><th scope="col">Count</th><th scope="col">Chunks</th></tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, MAX_ROWS).map((w) => (
                      <tr key={w.word}>
                        <th scope="row">
                          <button type="button" className="link-button" onClick={() => void showWord(w.word)}>
                            {w.word}
                          </button>
                        </th>
                        <td>{w.count}</td>
                        <td>{w.n_chunks}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rows.length > MAX_ROWS && (
                <p className="muted small">Showing {MAX_ROWS} of {rows.length}. Use the filter to find a word.</p>
              )}
            </>
          ) : (
            <p className="muted">{error ? '' : 'Loading vocabulary…'}</p>
          )}
        </>
      )}

      {mode === 'question' && !noDocs && (
        <>
          <form onSubmit={analyze} className="eval-form">
            <label>
              Pick a question from a set (optional)
              <select value={picked} onChange={(e) => pickQuestion(e.target.value)}>
                <option value="">—</option>
                {setQuestions.map((q) => (
                  <option key={`${q.set_name}:${q.id}`} value={`${q.set_name}:${q.id}`}>
                    {q.set_name} {q.id} ({q.type}) — {q.question}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Question
              <textarea rows={2} value={questionText} onChange={(e) => setQuestionText(e.target.value)} />
            </label>
            <div className="ask-actions">
              <button type="submit" disabled={busy || !questionText.trim()}>Analyze words</button>
              <span className="muted small">
                A question picked from a set also shows the chunks that hold its answer.
              </span>
            </div>
          </form>

          {analysis && (
            <div className="result wide">
              {analysis.answerable !== null && (
                <p className="small">
                  Chunks holding the answer:{' '}
                  {analysis.answer_chunks.length
                    ? analysis.answer_chunks.map((c) => `${c.filename} #${c.chunk_index}`).join(', ')
                    : analysis.answerable ? 'none found in the selected documents' : 'none (unanswerable question)'}
                </p>
              )}
              {analysis.missing.length > 0 && (
                <p className="error-text">
                  Not in the corpus at all: <strong>{analysis.missing.join(', ')}</strong>
                </p>
              )}
              <div className="table-scroll">
                <table className="scores">
                  <thead>
                    <tr>
                      <th scope="col">Word</th>
                      <th scope="col">Count</th>
                      <th scope="col">Chunks (of {analysis.n_chunks})</th>
                      {analysis.answerable !== null && <th scope="col">In answer chunks</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.tokens.map((t) => (
                      <tr key={t.word} className={t.stop ? 'stop-row' : ''}>
                        <th scope="row">
                          {t.count > 0 ? (
                            <button type="button" className="link-button" onClick={() => void showWord(t.word)}>
                              {t.word}
                            </button>
                          ) : (
                            <span className="miss">{t.word}</span>
                          )}
                          {t.stop && <span className="muted small"> stop</span>}
                        </th>
                        <td className={t.count === 0 ? 'miss' : ''}>{t.count}</td>
                        <td>{t.n_chunks}</td>
                        {analysis.answerable !== null && (
                          <td>
                            {analysis.answer_chunks.length ? `${t.in_answer_chunks} / ${analysis.answer_chunks.length}` : '—'}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {detail && <WordChunks detail={detail} />}
            </div>
          )}
        </>
      )}
    </section>
  )
}
