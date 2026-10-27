import type { ZodType } from 'zod'
import {
  AskResultSchema,
  DeleteResultSchema,
  DocumentInfoSchema,
  DocumentListSchema,
  RetrieveResultSchema,
  SettingsSchema,
} from './types'
import type { Api } from './types'

const BASE_URL: string = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

async function request<T>(path: string, schema: ZodType<T>, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, init)
  } catch {
    throw new Error(`Cannot reach the backend at ${BASE_URL}. Is it running?`)
  }

  const body: unknown = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(readDetail(body) ?? `Request failed with HTTP ${response.status}.`)
  }

  const parsed = schema.safeParse(body)
  if (!parsed.success) {
    console.error('Invalid response for', path, parsed.error)
    throw new Error('The server response was invalid.')
  }
  return parsed.data
}

// FastAPI errors look like {"detail": "..."}; validation errors use a list.
function readDetail(body: unknown): string | null {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return 'The request was rejected by the server (invalid input).'
  }
  return null
}

function jsonInit(method: string, data: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }
}

export const realApi: Api = {
  listDocuments: () => request('/documents', DocumentListSchema),

  uploadDocument: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/documents', DocumentInfoSchema, { method: 'POST', body: form })
  },

  deleteDocument: async (id) => {
    await request(`/documents/${encodeURIComponent(id)}`, DeleteResultSchema, { method: 'DELETE' })
  },

  getSettings: () => request('/settings', SettingsSchema),

  saveSettings: (settings) => request('/settings', SettingsSchema, jsonInit('PUT', settings)),

  retrieve: (body) => request('/retrieve', RetrieveResultSchema, jsonInit('POST', body)),

  ask: (body) => request('/ask', AskResultSchema, jsonInit('POST', body)),
}
