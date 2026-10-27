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

// Both the real client and the mock implement this interface.
export interface Api {
  listDocuments(): Promise<DocumentInfo[]>
  uploadDocument(file: File): Promise<DocumentInfo>
  deleteDocument(id: string): Promise<void>
  getSettings(): Promise<Settings>
  saveSettings(settings: Settings): Promise<Settings>
  retrieve(request: AskRequest): Promise<RetrieveResult>
  ask(request: AskRequest): Promise<AskResult>
}
