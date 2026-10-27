import { mockApi } from './mock'
import { realApi } from './client'
import type { Api } from './types'

export const useMock = import.meta.env.VITE_USE_MOCK === 'true'

export const api: Api = useMock ? mockApi : realApi

export * from './types'
