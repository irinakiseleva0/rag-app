import { useState } from 'react'
import type { ChangeEvent } from 'react'
import { api } from '../api'
import type { DocumentInfo } from '../api'
import { errorMessage } from '../errors'

type Props = {
  documents: DocumentInfo[]
  loading: boolean
  selectedIds: Set<string>
  onToggle: (id: string) => void
  onChanged: () => Promise<void>
}

export function DocumentsPanel({ documents, loading, selectedIds, onToggle, onChanged }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = '' // allow choosing the same file again
    if (!file) return
    if (!/\.(md|txt)$/i.test(file.name)) {
      setError('Only .md and .txt files are accepted.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.uploadDocument(file)
      await onChanged()
    } catch (e) {
      setError(`Upload failed: ${errorMessage(e)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(doc: DocumentInfo) {
    if (!confirm(`Delete "${doc.filename}" and all its chunks?`)) return
    setBusy(true)
    setError(null)
    try {
      await api.deleteDocument(doc.id)
      await onChanged()
    } catch (e) {
      setError(`Delete failed: ${errorMessage(e)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="documents-title">
      <h2 id="documents-title">Documents</h2>

      {loading && <p className="muted">Loading documents…</p>}

      {!loading && documents.length === 0 && (
        <p className="muted">No documents yet. Upload a .md or .txt file to start.</p>
      )}

      {documents.length > 0 && (
        <ul className="doc-list">
          {documents.map((doc) => (
            <li key={doc.id}>
              <label className="doc-check">
                <input
                  type="checkbox"
                  checked={selectedIds.has(doc.id)}
                  onChange={() => onToggle(doc.id)}
                />
                <span className="doc-name">{doc.filename}</span>
                <span className="muted small">{doc.n_chunks} chunks</span>
              </label>
              <button
                type="button"
                className="link-button danger"
                onClick={() => handleDelete(doc)}
                disabled={busy}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      <label className="upload">
        <span>{busy ? 'Working…' : 'Upload a document'}</span>
        <input type="file" accept=".md,.txt" onChange={handleUpload} disabled={busy} />
      </label>

      {error && <p className="error-text" role="alert">{error}</p>}
    </section>
  )
}
