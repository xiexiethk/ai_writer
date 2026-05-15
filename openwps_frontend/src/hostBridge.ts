export interface KnowledgeScope {
  folderId?: string
  folderIds?: string[]
  documentId?: string
  documentIds?: string[]
  folderName?: string
  documentTitle?: string
}

interface HostContext {
  apiBase: string
  knowledgeScope: KnowledgeScope | null
}

declare global {
  interface Window {
    __AI_WRITER_HOST_CONTEXT__?: HostContext
  }
}

const API_BASE = '/openwps/api'

function authToken() {
  try {
    return localStorage.getItem('token')?.trim() || ''
  } catch {
    return ''
  }
}

function appendToken(url: string, token: string) {
  if (!token) return url
  const next = new URL(url, window.location.origin)
  if (!next.searchParams.has('token')) {
    next.searchParams.set('token', token)
  }
  return `${next.pathname}${next.search}${next.hash}`
}

function rewriteApiUrl(input: string) {
  if (input === '/api') return API_BASE
  if (input.startsWith('/api/')) return `${API_BASE}${input.slice(4)}`
  return input
}

function parseMultiParam(params: URLSearchParams, key: string) {
  const values = params.getAll(key)
  if (values.length === 0) return []
  return values
    .flatMap(value => value.split(','))
    .map(value => value.trim())
    .filter(Boolean)
}

function readKnowledgeScopeFromLocation(): KnowledgeScope | null {
  const params = new URLSearchParams(window.location.search)
  const folderId = params.get('folderId')?.trim() || undefined
  const documentId = params.get('documentId')?.trim() || undefined
  const folderIds = parseMultiParam(params, 'folderIds')
  const documentIds = parseMultiParam(params, 'documentIds')
  const folderName = params.get('folderName')?.trim() || undefined
  const documentTitle = params.get('documentTitle')?.trim() || undefined

  if (!folderId && !documentId && folderIds.length === 0 && documentIds.length === 0) {
    return null
  }

  return {
    folderId,
    folderIds,
    documentId,
    documentIds,
    folderName,
    documentTitle,
  }
}

function installFetchBridge() {
  const nativeFetch = window.fetch.bind(window)
  window.fetch = (input, init) => {
    if (typeof input === 'string' || input instanceof URL) {
      const rewritten = rewriteApiUrl(String(input))
      const headers = new Headers(init?.headers || {})
      const token = authToken()
      if (token && rewritten.startsWith(API_BASE)) {
        headers.set('Authorization', `Bearer ${token}`)
      }
      return nativeFetch(rewritten, { ...init, headers })
    }
    return nativeFetch(input, init)
  }
}

function installEventSourceBridge() {
  const NativeEventSource = window.EventSource

  class BridgedEventSource extends NativeEventSource {
    constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
      const rewritten = rewriteApiUrl(String(url))
      const token = authToken()
      super(appendToken(rewritten, token), eventSourceInitDict)
    }
  }

  window.EventSource = BridgedEventSource as typeof EventSource
}

export function installHostBridge() {
  if (window.__AI_WRITER_HOST_CONTEXT__) {
    return window.__AI_WRITER_HOST_CONTEXT__
  }

  installFetchBridge()
  installEventSourceBridge()

  const context: HostContext = {
    apiBase: API_BASE,
    knowledgeScope: readKnowledgeScopeFromLocation(),
  }
  window.__AI_WRITER_HOST_CONTEXT__ = context
  return context
}

export function getHostKnowledgeScope() {
  return window.__AI_WRITER_HOST_CONTEXT__?.knowledgeScope || null
}
