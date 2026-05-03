import type { SessionSnapshotItem, SessionState } from '../types/sessionState'

export interface SessionHistoryLike {
  session_id: string
  display_name: string
  state: SessionState
  last_seen_at: string
  active: boolean
  has_real_user_input?: boolean
  originator?: string
  cwd?: string
  cwd_basename?: string
  branch?: string
  last_event_type?: string
  context?: SessionSnapshotItem['context']
  inactive?: boolean
  manual_summoned_at?: string
}

function toEpoch(value: string): number {
  const ts = Date.parse(value)
  return Number.isFinite(ts) ? ts : 0
}

function compareByLastSeenDesc(a: SessionHistoryLike, b: SessionHistoryLike): number {
  return toEpoch(b.last_seen_at) - toEpoch(a.last_seen_at)
}

export function getSessionActivityEpoch(session: SessionHistoryLike): number {
  return Math.max(toEpoch(session.last_seen_at), toEpoch(session.manual_summoned_at || ''))
}

export function mergeHistorySessions(
  existing: SessionHistoryLike[],
  incoming: SessionHistoryLike[],
  limit = 20,
): SessionHistoryLike[] {
  const map = new Map<string, SessionHistoryLike>()
  for (const item of existing) {
    map.set(item.session_id, { ...item })
  }
  for (const item of incoming) {
    const current = map.get(item.session_id)
    if (!current) {
      map.set(item.session_id, { ...item })
      continue
    }
    const keep = toEpoch(current.last_seen_at) > toEpoch(item.last_seen_at)
      ? {
          ...current,
          ...item,
          last_seen_at: current.last_seen_at,
          state: current.state,
          active: current.active,
          has_real_user_input: current.has_real_user_input || item.has_real_user_input,
          display_name: current.display_name || item.display_name,
          manual_summoned_at: current.manual_summoned_at || item.manual_summoned_at,
        }
      : {
          ...current,
          ...item,
          has_real_user_input: current.has_real_user_input || item.has_real_user_input,
          manual_summoned_at: current.manual_summoned_at || item.manual_summoned_at,
        }
    map.set(item.session_id, keep)
  }
  return Array.from(map.values())
    .sort(compareByLastSeenDesc)
    .slice(0, Math.max(1, limit))
}
