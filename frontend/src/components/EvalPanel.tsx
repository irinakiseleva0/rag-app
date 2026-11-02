import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { EvalRunResult, EvalSet, ScoreBlock } from '../api'
import { errorMessage } from '../errors'

const KS = ['1', '3', '5', '10']

function pct(v: number | undefined) {
  return v === undefined ? '–' : v.toFixed(2)
}

function ScoreRow({ name, block }: { name: string; block: ScoreBlock | null }) {
  if (!block) return null
  return (
    <tr>
      <th scope="row">{name}</th>
      <td>{block.n}</td>
      {KS.map((k) => <td key={`h${k}`}>{pct(block[`hit@${k}`])}</td>)}
      {KS.map((k) => <td key={`r${k}`}>{pct(block[`recall@${k}`])}</td>)}
    </tr>
  )
}

export function EvalPanel() {
  const [sets, setSets] = useState<EvalSet[]>([])
  const [setName, setSetName] = useState('kestrel')
  const [label, setLabel] = useState('ui')
  const [answers, setAnswers] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<EvalRunResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listEvalSets().then(setSets).catch((e: unknown) => setError(errorMessage(e)))
  }, [])

  const current = sets.find((s) => s.name === setName)
  const labelOk = /^[A-Za-z0-9._-]{1,40}$/.test(label)
  const blockedReason = !current
    ? 'Loading question sets…'
    : current.uploaded === 0
      ? `Upload the ${current.name} documents first (${current.corpus_files.length} files).`
      : !labelOk
        ? 'Label: letters, digits, dot, dash or underscore only (max 40).'
        : null

  async function handleRun(event: FormEvent) {
    event.preventDefault()
    if (blockedReason) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.runEval({ set_name: setName, label, answers }))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <section className="ask" aria-labelledby="eval-title">
      <h2 id="eval-title">Retrieval evaluation</h2>
      <p className="muted small">
        Runs every question of a set against the current settings. A chunk is relevant if it comes
        from the expected file and contains the evidence quote. Unanswerable questions are left out
        of the scores. Results are saved in <code>eval/results/</code>.
      </p>

      <form onSubmit={handleRun} className="eval-form">
        <label>
          Question set
          <select value={setName} onChange={(e) => setSetName(e.target.value)} disabled={running}>
            {sets.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name} — {s.n_questions} questions, {s.uploaded}/{s.corpus_files.length} files uploaded
              </option>
            ))}
          </select>
        </label>
        <label>
          Configuration label
          <input value={label} onChange={(e) => setLabel(e.target.value)} disabled={running} />
        </label>
        <label className="check">
          <input type="checkbox" checked={answers} onChange={(e) => setAnswers(e.target.checked)} disabled={running} />
          Also generate answers (calls the LLM once per question: slower, uses quota)
        </label>
        <div className="ask-actions">
          <button type="submit" disabled={running || !!blockedReason}>
            {running ? 'Running…' : 'Run evaluation'}
          </button>
          {blockedReason && <span className="muted small">{blockedReason}</span>}
        </div>
      </form>

      {error && (
        <div className="result error-box" role="alert">
          <strong>Evaluation failed.</strong> {error}
        </div>
      )}

      {result && (
        <div className="result wide">
          <p className="muted small">
            Saved to <code>{result.file}</code> · chunk size {result.settings.chunk_size}, overlap{' '}
            {result.settings.overlap_percent}%, top-k {result.settings.top_k}
          </p>
          <div className="table-scroll">
            <table className="scores">
              <thead>
                <tr>
                  <th scope="col">Type</th>
                  <th scope="col">n</th>
                  {KS.map((k) => <th scope="col" key={`h${k}`}>Hit@{k}</th>)}
                  {KS.map((k) => <th scope="col" key={`r${k}`}>Rec@{k}</th>)}
                </tr>
              </thead>
              <tbody>
                <ScoreRow name="overall" block={result.summary.overall} />
                {Object.entries(result.summary.by_type).map(([t, b]) => (
                  <ScoreRow key={t} name={t} block={b} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">
            Unanswerable questions left out: {result.summary.n_unanswerable}
          </p>

          <h3>Per question</h3>
          <div className="table-scroll">
            <table className="scores">
              <thead>
                <tr>
                  <th scope="col">id</th>
                  <th scope="col">Type</th>
                  <th scope="col">First relevant rank</th>
                  {KS.map((k) => <th scope="col" key={k}>@{k}</th>)}
                  {answers && <th scope="col">Answer</th>}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.id} title={r.question}>
                    <th scope="row">{r.id}</th>
                    <td>{r.type}</td>
                    <td>{r.answerable ? (r.first_relevant_rank ?? 'not in top 10') : '—'}</td>
                    {KS.map((k) => (
                      <td key={k} className={r.answerable ? (r.hit[k] ? 'hit' : 'miss') : ''}>
                        {r.answerable ? (r.hit[k] ? '✓' : '✗') : ''}
                      </td>
                    ))}
                    {answers && (
                      <td className="answer-cell">
                        <strong>{r.answer?.status}</strong> {r.answer?.text}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {answers && (
            <p className="muted small">Grade the answers by hand in the saved file (grade, grade_note).</p>
          )}
        </div>
      )}
    </section>
  )
}
