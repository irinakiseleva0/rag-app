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
})

export const RetrieveResultSchema = z.object({
  chunks: z.array(ReferenceSchema),
})

export const AskResultSchema = z.object({
  status: z.enum(['answered', 'not_found', 'error']),
  answer: z.string(),
  references: z.array(ReferenceSchema),
  error: z.string().nullable(),
})

export type DocumentInfo = z.infer<typeof DocumentInfoSchema>
export type Settings = z.infer<typeof SettingsSchema>
export type Reference = z.infer<typeof ReferenceSchema>
export type RetrieveResult = z.infer<typeof RetrieveResultSchema>
export type AskResult = z.infer<typeof AskResultSchema>

export type AskRequest = {
  question: string
  doc_ids: string[]
  top_k: number
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
}
