import type { Api, AskRequest, AskResult, DocumentInfo, EvalRunResult, GraphPath, Reference, Settings } from './types'

// In-memory fake backend, used while the real one is not ready (VITE_USE_MOCK=true).
// Ask behaviour: "notfound" in the question -> not_found, "error" -> error.

const delay = (ms = 500) => new Promise((resolve) => setTimeout(resolve, ms))

let documents: DocumentInfo[] = [
  { id: 'doc000000001', filename: 'password-reset.md', n_chunks: 12, uploaded_at: '2026-10-27T10:00:00Z' },
  { id: 'doc000000002', filename: 'billing-faq.txt', n_chunks: 34, uploaded_at: '2026-10-27T10:05:00Z' },
]

let settings: Settings = { chunk_size: 800, overlap_percent: 10, top_k: 5 }

function fakeReferences(req: AskRequest): Reference[] {
  const retrievers = req.retrievers ?? { dense: true, bm25: false, graph: false }
  const enabled = (['dense', 'bm25', 'graph'] as const).filter((name) => retrievers[name])
  if (enabled.length === 0) throw new Error('At least one retriever must be on.')
  const selected = documents.filter((d) => req.doc_ids.length === 0 || req.doc_ids.includes(d.id))
  return selected.slice(0, Math.min(2, req.top_k, req.candidates ?? 20)).map((doc, i) => ({
    chunk_id: `${doc.id}#000${i}`,
    filename: doc.filename,
    chunk_index: i,
    char_start: i * 720,
    char_end: i * 720 + 800,
    text: `Mock chunk ${i} from ${doc.filename}. In the real app this is the exact text that was sent to the model.`,
    score: 0.82 - i * 0.07,
    found_by: enabled.map((retriever) => ({ retriever, rank: i + 1 })),
    rrf_score: Number((enabled.length / (60 + i + 1)).toFixed(5)),
  }))
}

function fakeGraphPath(req: AskRequest, references: Reference[]): GraphPath | null {
  if (!req.retrievers?.graph) return null
  const entity = req.question.match(/\bKST-\d+\b/i)?.[0]
    ?? req.question.match(/\b(password|billing)\b/i)?.[0]
  if (!entity || references.length === 0) return { entities: [], edges: [] }
  return {
    entities: [entity],
    edges: [{ from: entity, relation: 'APPLIES_TO', to: 'Mock support', chunk_id: references[0].chunk_id }],
  }
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
    const chunks = fakeReferences(req)
    return { trace_id: 'mock-trace', chunks, graph_path: fakeGraphPath(req, chunks),
      cost: { llm_calls: 0, tokens: 0, latency_ms: 500 } }
  },

  async ask(req): Promise<AskResult> {
    await delay()
    const q = req.question.toLowerCase()
    const references = fakeReferences(req)
    const metadata = {
      trace_id: 'mock-trace',
      graph_path: fakeGraphPath(req, references),
      cost: { llm_calls: 1, tokens: 240, latency_ms: 500 },
    }
    if (q.includes('notfound')) {
      return { status: 'not_found', answer: '', references: [], error: null, ...metadata }
    }
    if (q.includes('error')) {
      return { status: 'error', answer: '', references: [], error: 'Mock error: the model returned invalid JSON.', ...metadata }
    }
    return {
      status: 'answered',
      answer: 'This is a mock answer. It is built only from the two references below.',
      references,
      error: null,
      ...metadata,
    }
  },

  async getTrace(id) {
    await delay()
    const candidates = [
      { chunk_id: 'doc000000001#0000', rank: 1 },
      { chunk_id: 'doc000000002#0001', rank: 2 },
    ]
    return {
      id, kind: 'question', started_at: new Date().toISOString(),
      duration_ms: 500, status: 'answered',
      input: { question: 'How do I reset my password?', doc_ids: [], top_k: 2,
        retrievers: { dense: true, bm25: true, graph: true }, candidates: 20 },
      spans: [
        { name: 'dense', duration_ms: 75, attributes: { candidates } },
        { name: 'bm25', duration_ms: 10, attributes: { candidates } },
        { name: 'graph', duration_ms: 25,
          attributes: { candidates, entities: ['Password reset', 'Account access'], edges_count: 1 } },
        { name: 'rrf', duration_ms: 2, attributes: { top_k: 2,
          results: candidates.map(({ chunk_id, rank }) => ({ chunk_id,
            rrf_score: Number((3 / (60 + rank)).toFixed(5)),
            found_by: ['dense', 'bm25', 'graph'].map((retriever) => ({ retriever, rank })),
          })) } },
        { name: 'llm', duration_ms: 380, attributes: {
          model: 'gemini-3.1-flash-lite-preview', chunks_sent: candidates.map((c) => c.chunk_id),
          tokens: 240, status: 'answered', error: null,
        } },
      ],
      totals: { llm_calls: 1, tokens: 240 },
    }
  },

  async listEvalSets() {
    await delay()
    return [
      { name: 'kestrel', n_questions: 10, corpus_files: ['product-guide.md'], uploaded: 5 },
      { name: 'courses', n_questions: 22, corpus_files: ['ai-systems-c6-rag.md'], uploaded: 0 },
    ]
  },

  async runEval(req): Promise<EvalRunResult> {
    await delay(1200)
    const block = (n: number, base: number) => ({
      n,
      'hit@1': base, 'hit@3': base + 0.1, 'hit@5': base + 0.15, 'hit@10': 1,
      'recall@1': base - 0.1, 'recall@3': base, 'recall@5': base + 0.1, 'recall@10': 1,
    })
    return {
      file: `eval/results/mock-${req.set_name}-${req.label}.json`,
      settings: { ...settings },
      summary: {
        overall: block(8, 0.62),
        by_type: { exact_identifier: block(2, 0.5), two_hop: block(1, 0) },
        n_unanswerable: 2,
      },
      rows: [
        {
          id: 'q01', type: 'exact_identifier', answerable: true,
          question: 'What does error KST-2044 mean?', first_relevant_rank: 7,
          hit: { '1': false, '3': false, '5': false, '10': true },
          recall: { '1': 0, '3': 0, '5': 0, '10': 1 },
          ...(req.answers ? { answer: { status: 'not_found', text: null, references: [] } } : {}),
        },
        {
          id: 'q09', type: 'not_in_corpus', answerable: false,
          question: 'Is there a Kestrel mobile app for iPhone?', first_relevant_rank: null,
          hit: {}, recall: {},
        },
      ],
    }
  },

  async vocabulary() {
    await delay()
    return {
      n_chunks: 46, n_tokens: 5200, n_distinct: 3,
      words: [
        { word: 'the', count: 300, n_chunks: 46, stop: true },
        { word: 'kst-2044', count: 3, n_chunks: 2, stop: false },
        { word: 'allowlist', count: 4, n_chunks: 2, stop: false },
      ],
    }
  },

  async wordDetail(word) {
    await delay()
    return {
      word: word.toLowerCase(), stop: false, count: 3, n_chunks: 1,
      chunks: [{ chunk_id: 'doc#0004', filename: 'support-runbook-errors.md', chunk_index: 4,
                 count: 3, is_answer: false, text: `Mock chunk mentioning ${word} three times.` }],
    }
  },

  async questionWords(req) {
    await delay()
    return {
      question: req.question || 'I lost my phone and I can\u2019t log in anymore.',
      n_chunks: 46, answerable: true,
      answer_chunks: [{ chunk_id: 'doc#0006', filename: 'product-guide.md', chunk_index: 6 }],
      tokens: [
        { word: 'lost', stop: false, count: 1, n_chunks: 1, in_answer_chunks: 0, chunks: [] },
        { word: 'phone', stop: false, count: 0, n_chunks: 0, in_answer_chunks: 0, chunks: [] },
      ],
      missing: ['phone'],
    }
  },

  async listSetQuestions() {
    await delay()
    return [{ set_name: 'kestrel', id: 'q05', type: 'vocabulary', question: 'I lost my phone and I can\u2019t log in anymore. What can I do?' }]
  },
}
