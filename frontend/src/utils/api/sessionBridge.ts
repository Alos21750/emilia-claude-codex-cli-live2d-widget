import type { SessionHistoryResponse } from '../../types/sessionState'

import { getDefaultServerUrl } from '../serverUrl'

const DEFAULT_SERVER_URL = getDefaultServerUrl()
const HISTORY_PATH = '/api/session-bridge/history'
const WS_PATH = '/api/session-bridge/ws'

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function resolveHistoryUrl(serverUrl?: string, limit = 20): string {
  const base = trimTrailingSlash(serverUrl || DEFAULT_SERVER_URL)
  const safeLimit = Math.max(1, Math.min(200, Number(limit || 20)))
  return `${base}${HISTORY_PATH}?limit=${safeLimit}`
}

export function resolveBridgeWsUrl(serverUrl?: string, bridgeUrl?: string): string {
  if (bridgeUrl && bridgeUrl.trim()) {
    return bridgeUrl.trim()
  }

  const base = trimTrailingSlash(serverUrl || DEFAULT_SERVER_URL)
  const parsed = new URL(base)
  parsed.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
  parsed.pathname = WS_PATH
  parsed.search = ''
  parsed.hash = ''
  return parsed.toString()
}

export async function fetchSessionBridgeHistory(serverUrl?: string, limit = 20): Promise<SessionHistoryResponse> {
  const response = await fetch(resolveHistoryUrl(serverUrl, limit), {
    method: 'GET',
  })
  if (!response.ok) {
    throw new Error(`failed to fetch history: ${response.status}`)
  }
  return (await response.json()) as SessionHistoryResponse
}
