import { useState } from 'react'
import type { Reference } from '../api'

export function ReferenceList({ references }: { references: Reference[] }) {
  const [openId, setOpenId] = useState<string | null>(null)

  if (references.length === 0) {
    return <p className="muted">The answer has no references.</p>
  }

  return (
    <ol className="references">
      {references.map((ref, i) => {
        const open = openId === ref.chunk_id
        return (
          <li key={ref.chunk_id}>
            <button
              type="button"
              className="reference-toggle"
              aria-expanded={open}
              onClick={() => setOpenId(open ? null : ref.chunk_id)}
            >
              <span className="ref-number">[{i + 1}]</span>
              <span className="ref-file">{ref.filename}</span>
              <span className="muted small">
                chunk {ref.chunk_index}, characters {ref.char_start}–{ref.char_end}, similarity{' '}
                {ref.score.toFixed(2)}
              </span>
            </button>
            {open && <pre className="chunk-text">{ref.text}</pre>}
          </li>
        )
      })}
    </ol>
  )
}
