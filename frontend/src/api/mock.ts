import type { Api, AskResult, DocumentInfo, Reference, Settings } from './types'

// In-memory fake backend, used while the real one is not ready (VITE_USE_MOCK=true).
// Ask behaviour: "notfound" in the question -> not_found, "error" -> error.

const delay = (ms = 500) => new Promise((resolve) => setTimeout(resolve, ms))

let documents: DocumentInfo[] = [
  { id: 'doc000000001', filename: 'password-reset.md', n_chunks: 12, uploaded_at: '2026-10-27T10:00:00Z' },
  { id: 'doc000000002', filename: 'billing-faq.txt', n_chunks: 34, uploaded_at: '2026-10-27T10:05:00Z' },
]

let settings: Settings = { chunk_size: 800, overlap_percent: 10, top_k: 5 }

function fakeReferences(docIds: string[], topK: number): Reference[] {
  const selected = documents.filter((d) => docIds.includes(d.id))
  return selected.slice(0, Math.min(2, topK)).map((doc, i) => ({
    chunk_id: `${doc.id}#000${i}`,
    filename: doc.filename,
    chunk_index: i,
    char_start: i * 720,
    char_end: i * 720 + 800,
    text: `Mock chunk ${i} from ${doc.filename}. In the real app this is the exact text that was sent to the model.`,
    score: 0.82 - i * 0.07,
  }))
}

export const mockApi: Api = {
  async listDocuments() {
    await delay()
    return [...documents]
  },

  async uploadDocument(file) {
    await delay()
    if (!/\.(md|txt)$/i.test(file.name)) throw new Error('Only .md and .txt files are accepted.')
    if (file.size === 0) throw new Error('The file is empty.')
    const doc: DocumentInfo = {
      id: Math.random().toString(16).slice(2, 14).padEnd(12, '0'),
      filename: file.name,
      n_chunks: Math.max(1, Math.ceil(file.size / 720)),
      uploaded_at: new Date().toISOString(),
    }
    documents = [...documents, doc]
    return doc
  },

  async deleteDocument(id) {
    await delay()
    if (!documents.some((d) => d.id === id)) throw new Error('Document not found.')
    documents = documents.filter((d) => d.id !== id)
  },

  async getSettings() {
    await delay()
    return { ...settings }
  },

  async saveSettings(next) {
    await delay(1000)
    settings = { ...next }
    return { ...settings }
  },

  async retrieve(req) {
    await delay()
    return { chunks: fakeReferences(req.doc_ids, req.top_k) }
  },

  async ask(req): Promise<AskResult> {
    await delay()
    const q = req.question.toLowerCase()
    if (q.includes('notfound')) {
      return { status: 'not_found', answer: '', references: [], error: null }
    }
    if (q.includes('error')) {
      return { status: 'error', answer: '', references: [], error: 'Mock error: the model returned invalid JSON.' }
    }
    return {
      status: 'answered',
      answer: 'This is a mock answer. It is built only from the two references below.',
      references: fakeReferences(req.doc_ids, req.top_k),
      error: null,
    }
  },
}
