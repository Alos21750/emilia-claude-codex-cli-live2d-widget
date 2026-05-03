const DEFAULT_LOCAL_BACKEND_HOST = import.meta.env.VITE_BACKEND_HOST || '127.0.0.1'
const DEFAULT_LOCAL_BACKEND_PORT = import.meta.env.VITE_BACKEND_PORT || '8000'
const DEFAULT_LOCAL_SERVER_URL = `http://${DEFAULT_LOCAL_BACKEND_HOST}:${DEFAULT_LOCAL_BACKEND_PORT}`

/**
 * Auto-detect the default server URL.
 * - Local dev (localhost/127.0.0.1): explicit backend origin from root .env
 * - Remote mode (Cloudflare Tunnel etc.): empty string = relative paths (same origin)
 */
export function getDefaultServerUrl(): string {
  if (typeof window === 'undefined') return DEFAULT_LOCAL_SERVER_URL
  const { hostname } = window.location
  if (window.location.protocol === 'file:') {
    return DEFAULT_LOCAL_SERVER_URL
  }
  if (hostname === '127.0.0.1' || hostname === 'localhost') {
    return DEFAULT_LOCAL_SERVER_URL
  }
  return ''
}
