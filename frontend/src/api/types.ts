import { z } from 'zod'

// Zod schemas mirror API.md. Every backend response is parsed with one of them,
// so a malformed response becomes a handled error instead of a crash.

export const DocumentInfoSchema = z.object({
  id: z.string(),
  filename: z.string(),
  n_chunks: z.number().int().nonnegative(),
  uploaded_at: z.string(),
})
export const DocumentListSchema = z.array(DocumentInfoSchema)

export const DeleteResultSchema = z.object({ deleted: z.boolean() })

export const SettingsSchema = z.object({
  chunk_size: z.number().int(),
  overlap_percent: z.number().int(),
  top_k: z.number().int(),
})

export const ReferenceSchema = z.object({
  chunk_id: z.string(),
  filename: z.string(),
  chunk_index: z.number().int(),
  char_start: z.number().int(),
  char_end: z.number().int(),
  text: z.string(),
  score: z.number(),
  found_by: z.array(z.object({
    retriever: z.enum(['dense', 'bm25', 'graph']),
    rank: z.number().int().positive(),
  })).default([]),
  rrf_score: z.number().nullable().default(null),
})

export const GraphPathSchema = z.object({
  entities: z.array(z.string()),
  edges: z.array(z.object({
    from: z.string(),
    relation: z.string(),
    to: z.string(),
    chunk_id: z.string(),
  })),
})

const CostSchema = z.object({
  llm_calls: z.number().int().nonnegative().default(0),
  tokens: z.number().int().nonnegative().default(0),
  latency_ms: z.number().int().nonnegative().default(0),
}).default({ llm_calls: 0, tokens: 0, latency_ms: 0 })

export const RetrieveResultSchema = z.object({
  chunks: z.array(ReferenceSchema),
  graph_path: GraphPathSchema.nullable().default(null),
  cost: CostSchema,
})

export const AskResultSchema = z.object({
  status: z.enum(['answered', 'not_found', 'error']),
  answer: z.string(),
  references: z.array(ReferenceSchema),
  error: z.string().nullable(),
  graph_path: GraphPathSchema.nullable().default(null),
  cost: CostSchema,
})

export type DocumentInfo = z.infer<typeof DocumentInfoSchema>
export type Settings = z.infer<typeof SettingsSchema>
export type Reference = z.infer<typeof ReferenceSchema>
export type RetrieveResult = z.infer<typeof RetrieveResultSchema>
export type AskResult = z.infer<typeof AskResultSchema>
export type GraphPath = z.infer<typeof GraphPathSchema>

export type AskRequest = {
  question: string
  doc_ids: string[]
  top_k: number
  retrievers?: { dense: boolean; bm25: boolean; graph: boolean }
  candidates?: number
}

// ---------- Evaluation (V2) ----------
// k values are JSON object keys, so they arrive as strings: "1", "3", "5", "10".

export const EvalSetSchema = z.object({
  name: z.string(),
  n_questions: z.number().int(),
  corpus_files: z.array(z.string()),
  uploaded: z.number().int(),
})
export const EvalSetListSchema = z.array(EvalSetSchema)

const ScoreBlockSchema = z
  .object({ n: z.number().int() })
  .catchall(z.number()) // hit@1 … hit@10, recall@1 … recall@10

export const EvalSummarySchema = z.object({
  overall: ScoreBlockSchema.nullable(),
  by_type: z.record(z.string(), ScoreBlockSchema.nullable()),
  n_unanswerable: z.number().int(),
})

export const EvalRowSchema = z.object({
  id: z.string(),
  type: z.string(),
  answerable: z.boolean(),
  question: z.string(),
  expected_answer: z.string().nullable().optional(),
  first_relevant_rank: z.number().int().nullable(),
  hit: z.record(z.string(), z.boolean()),
  recall: z.record(z.string(), z.number()),
  answer: z
    .object({ status: z.string(), text: z.string().nullable(), references: z.array(z.string()) })
    .optional(),
})

export const EvalRunResultSchema = z.object({
  file: z.string(),
  settings: SettingsSchema,
  summary: EvalSummarySchema,
  rows: z.array(EvalRowSchema),
})

export type EvalSet = z.infer<typeof EvalSetSchema>
export type ScoreBlock = z.infer<typeof ScoreBlockSchema>
export type EvalRow = z.infer<typeof EvalRowSchema>
export type EvalRunResult = z.infer<typeof EvalRunResultSchema>
export type EvalRunRequest = { set_name: string; label: string; answers: boolean }

// ---------- Words analytics (V2) ----------

export const VocabularySchema = z.object({
  n_chunks: z.number().int(),
  n_tokens: z.number().int(),
  n_distinct: z.number().int(),
  words: z.array(
    z.object({ word: z.string(), count: z.number().int(), n_chunks: z.number().int(), stop: z.boolean() }),
  ),
})

const WordChunkSchema = z.object({
  chunk_id: z.string(),
  filename: z.string(),
  chunk_index: z.number().int(),
  count: z.number().int(),
  is_answer: z.boolean(),
  text: z.string().optional(),
})

export const WordDetailSchema = z.object({
  word: z.string(),
  stop: z.boolean(),
  count: z.number().int(),
  n_chunks: z.number().int(),
  chunks: z.array(WordChunkSchema),
})

export const QuestionWordsSchema = z.object({
  question: z.string(),
  n_chunks: z.number().int(),
  answerable: z.boolean().nullable(),
  answer_chunks: z.array(z.object({ chunk_id: z.string(), filename: z.string(), chunk_index: z.number().int() })),
  tokens: z.array(
    z.object({
      word: z.string(),
      stop: z.boolean(),
      count: z.number().int(),
      n_chunks: z.number().int(),
      in_answer_chunks: z.number().int(),
      chunks: z.array(WordChunkSchema),
    }),
  ),
  missing: z.array(z.string()),
})

export const SetQuestionListSchema = z.array(
  z.object({ set_name: z.string(), id: z.string(), type: z.string(), question: z.string() }),
)

export type Vocabulary = z.infer<typeof VocabularySchema>
export type WordDetail = z.infer<typeof WordDetailSchema>
export type QuestionWords = z.infer<typeof QuestionWordsSchema>
export type SetQuestion = z.infer<typeof SetQuestionListSchema>[number]
export type QuestionWordsRequest = {
  doc_ids: string[]
  question: string
  set_name?: string
  question_id?: string
}

// Both the real client and the mock implement this interface.
export interface Api {
  listDocuments(): Promise<DocumentInfo[]>
  uploadDocument(file: File): Promise<DocumentInfo>
  deleteDocument(id: string): Promise<void>
  getSettings(): Promise<Settings>
  saveSettings(settings: Settings): Promise<Settings>
  retrieve(request: AskRequest): Promise<RetrieveResult>
  ask(request: AskRequest): Promise<AskResult>
  listEvalSets(): Promise<EvalSet[]>
  runEval(request: EvalRunRequest): Promise<EvalRunResult>
  vocabulary(docIds: string[]): Promise<Vocabulary>
  wordDetail(word: string, docIds: string[]): Promise<WordDetail>
  questionWords(request: QuestionWordsRequest): Promise<QuestionWords>
  listSetQuestions(): Promise<SetQuestion[]>
}
