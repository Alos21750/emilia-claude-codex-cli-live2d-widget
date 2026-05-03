export type SessionState = 'IDLE' | 'THINKING' | 'TOOLING' | 'RESPONDING' | 'WAITING'
export type AgentBrand = string

type SessionRuntimeContext = {
  [key: string]: unknown
  model?: string
  effort?: string
  permission_mode?: string
  approval_policy?: string
  sandbox_mode?: string
  plan_mode?: boolean
  plan_mode_fallback?: boolean
  total_tokens?: number
  model_context_window?: number
  primary_rate_remaining_percent?: number
  secondary_rate_remaining_percent?: number
  persona_id?: string
  persona_name?: string
  persona_content?: string
}

type SessionStateMeta = {
  originator?: string
  cwd?: string
  cwd_basename?: string
  last_event_type?: string
  branch?: string
  context?: SessionRuntimeContext
  inactive?: boolean
}

export interface SessionStateEvent {
  version: '1'
  event: 'session_state'
  session_id: string
  display_name?: string
  state: SessionState
  ts: string
  source: string
  agent_brand?: AgentBrand
  has_real_user_input?: boolean
  meta: SessionStateMeta
}

export interface SessionSnapshotItem {
  session_id: string
  display_name: string
  state: SessionState
  last_seen_at: string
  originator?: string
  cwd?: string
  cwd_basename?: string
  branch?: string
  last_event_type?: string
  agent_brand?: AgentBrand
  has_real_user_input?: boolean
  context?: SessionRuntimeContext
  active?: boolean
  inactive?: boolean
  pending_inactive?: boolean
  summary?: string
  manual_summoned_at?: string
}

export interface SessionHistoryItem {
  session_id: string
  display_name: string
  state: SessionState
  last_seen_at: string
  active: boolean
  originator?: string
  cwd?: string
  cwd_basename?: string
  branch?: string
  last_event_type?: string
  agent_brand?: AgentBrand
  has_real_user_input?: boolean
  context?: SessionRuntimeContext
}

export interface SessionHistoryResponse {
  version: '1'
  generated_at: string
  sessions: SessionHistoryItem[]
}
