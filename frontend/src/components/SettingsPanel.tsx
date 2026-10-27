import { useState } from 'react'
import type { Settings } from '../api'

type Props = {
  settings: Settings | null
  saving: boolean
  error: string | null
  onSave: (settings: Settings) => Promise<void>
}

function validate(s: Settings): string | null {
  if (!Number.isInteger(s.chunk_size) || s.chunk_size <= 0) return 'Chunk size must be a whole number above 0.'
  if (!Number.isInteger(s.overlap_percent) || s.overlap_percent < 0 || s.overlap_percent >= 100)
    return 'Overlap must be between 0 and 99 %.'
  if (!Number.isInteger(s.top_k) || s.top_k < 1) return 'Top-k must be at least 1.'
  return null
}

export function SettingsPanel({ settings, saving, error, onSave }: Props) {
  const [draft, setDraft] = useState<Settings | null>(settings)
  const [localError, setLocalError] = useState<string | null>(null)

  if (!draft || !settings) {
    return (
      <section className="panel" aria-labelledby="settings-title">
        <h2 id="settings-title">Retrieval settings</h2>
        <p className="muted">{error ?? 'Loading settings…'}</p>
      </section>
    )
  }

  const needsReindex =
    draft.chunk_size !== settings.chunk_size || draft.overlap_percent !== settings.overlap_percent
  const changed = needsReindex || draft.top_k !== settings.top_k

  function update(field: keyof Settings, value: string) {
    setDraft((prev) => (prev ? { ...prev, [field]: Number(value) } : prev))
  }

  async function handleSave() {
    if (!draft) return
    const problem = validate(draft)
    setLocalError(problem)
    if (problem) return
    await onSave(draft)
  }

  return (
    <section className="panel" aria-labelledby="settings-title">
      <h2 id="settings-title">Retrieval settings</h2>

      <div className="settings-grid">
        <label>
          <span>Chunk size <span className="muted small">(characters)</span></span>
          <input
            type="number"
            min={1}
            value={draft.chunk_size}
            onChange={(e) => update('chunk_size', e.target.value)}
          />
        </label>
        <label>
          <span>Overlap <span className="muted small">(%)</span></span>
          <input
            type="number"
            min={0}
            max={99}
            value={draft.overlap_percent}
            onChange={(e) => update('overlap_percent', e.target.value)}
          />
        </label>
        <label>
          <span>Top-k <span className="muted small">(chunks)</span></span>
          <input
            type="number"
            min={1}
            value={draft.top_k}
            onChange={(e) => update('top_k', e.target.value)}
          />
        </label>
      </div>

      {needsReindex && (
        <p className="warning">Changing chunk size or overlap re-indexes every document.</p>
      )}

      <button type="button" onClick={handleSave} disabled={!changed || saving}>
        {saving ? (needsReindex ? 'Re-indexing…' : 'Saving…') : 'Save settings'}
      </button>

      {(localError ?? error) && (
        <p className="error-text" role="alert">{localError ?? error}</p>
      )}
    </section>
  )
}
