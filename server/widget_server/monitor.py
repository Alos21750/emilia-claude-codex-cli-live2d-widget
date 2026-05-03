import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import WebSocket

from .claude_jsonl import ClaudeJsonlParser
from .codex_jsonl import CodexJsonlParser
from .state import (
    UUID_PATTERN,
    _FileCursor,
    _SessionRecord,
    _basename_from_cwd,
    _env_bool,
    _iso_now,
    _normalize_permission_mode,
    _ts_to_epoch,
)
from .ws import WebSocketManager

logger = logging.getLogger(__name__)


class SessionBridgeService:
    """Bridge Codex and Claude local JSONL events into websocket session-state events."""

    def __init__(self) -> None:
        self.session_dir = Path(os.getenv("CODEX_SESSION_DIR", "~/.codex/sessions")).expanduser()
        self.claude_session_dir = Path(os.getenv("CLAUDE_SESSION_DIR", "~/.claude/projects")).expanduser()
        self.enabled = _env_bool("SESSION_BRIDGE_ENABLED", True)
        self.inactive_ttl_sec = int(os.getenv("SESSION_INACTIVE_TTL_SEC", "600"))

        self.scan_interval_sec = 0.5
        self.min_state_duration_sec = 0.6
        self.idle_after_task_complete_sec = 8.0
        self.initial_read_bytes = 256 * 1024

        self._watch_task: Optional[asyncio.Task] = None
        self._tick_task: Optional[asyncio.Task] = None

        self._files: dict[str, _FileCursor] = {}
        self._claude_files: dict[str, _FileCursor] = {}
        self._sessions: dict[str, _SessionRecord] = {}
        self._sessions_lock = asyncio.Lock()

        self._ws = WebSocketManager()

        self.events_ingested_total = 0
        self.events_dropped_total = 0
        self.latest_event_epoch = 0.0
        self.degraded_reason = ""
        self.source_version = "codex_jsonl.v1"
        self._session_id_pattern = UUID_PATTERN

        self.codex_parser = CodexJsonlParser(self)
        self.claude_parser = ClaudeJsonlParser(self)

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Session bridge disabled by SESSION_BRIDGE_ENABLED")
            return
        if self._watch_task and not self._watch_task.done():
            return
        logger.info("Starting session bridge. codex_dir=%s claude_dir=%s", self.session_dir, self.claude_session_dir)
        self._watch_task = asyncio.create_task(self._watch_loop(), name="session-bridge-watch")
        self._tick_task = asyncio.create_task(self._tick_loop(), name="session-bridge-tick")

    async def stop(self) -> None:
        tasks = [self._watch_task, self._tick_task]
        for task in tasks:
            if task is not None:
                task.cancel()
        for task in tasks:
            if task is None:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Session bridge task stopped with error")
        self._watch_task = None
        self._tick_task = None

        await self._ws.close_all()

    async def register_ws_client(self, ws: WebSocket) -> None:
        await self._ws.register_ws_client(ws)

    async def unregister_ws_client(self, ws: WebSocket) -> None:
        await self._ws.unregister_ws_client(ws)

    async def get_snapshot(self) -> dict[str, Any]:
        now_epoch = time.time()
        async with self._sessions_lock:
            active_sessions = [
                {
                    "session_id": s.session_id,
                    "display_name": s.display_name,
                    "state": s.state,
                    "last_seen_at": s.last_seen_at,
                    "originator": s.originator,
                    "cwd": s.cwd,
                    "cwd_basename": s.cwd_basename,
                    "last_event_type": s.last_event_type,
                    "branch": s.branch,
                    "agent_brand": getattr(s, "agent_brand", "codex"),
                    "has_real_user_input": bool(getattr(s, "has_real_user_input", False)),
                    "context": self._context_payload(s),
                }
                for s in sorted(self._sessions.values(), key=lambda x: x.last_seen_epoch, reverse=True)
                if s.active and (now_epoch - s.last_seen_epoch) < self.inactive_ttl_sec
            ]
        return {
            "version": "1",
            "generated_at": _iso_now(),
            "sessions": active_sessions,
        }

    async def get_history(self, limit: int = 20) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit or 20), 200))
        sessions = self._collect_history_from_files()
        now_epoch = time.time()
        async with self._sessions_lock:
            for s in self._sessions.values():
                if s.session_id not in sessions:
                    sessions[s.session_id] = {
                        "session_id": s.session_id,
                        "display_name": s.display_name,
                        "state": s.state,
                        "last_seen_at": s.last_seen_at,
                        "last_seen_epoch": s.last_seen_epoch,
                        "originator": s.originator,
                        "cwd": s.cwd,
                        "cwd_basename": s.cwd_basename,
                        "last_event_type": s.last_event_type,
                        "branch": s.branch,
                        "agent_brand": getattr(s, "agent_brand", "codex"),
                        "has_real_user_input": bool(getattr(s, "has_real_user_input", False)),
                        "context": self._context_payload(s),
                    }
                else:
                    existing = sessions[s.session_id]
                    if not existing.get("agent_brand"):
                        existing["agent_brand"] = getattr(s, "agent_brand", "codex")
                    if bool(getattr(s, "has_real_user_input", False)):
                        existing["has_real_user_input"] = True
        ordered = sorted(
            sessions.values(),
            key=lambda item: item["last_seen_epoch"],
            reverse=True,
        )[:safe_limit]
        for item in ordered:
            if item.get("branch"):
                continue
            cwd = str(item.get("cwd") or "").strip()
            if not cwd:
                continue
            try:
                completed = subprocess.run(
                    ["git", "-C", cwd, "branch", "--show-current"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except Exception:
                continue
            if completed.returncode == 0:
                item["branch"] = (completed.stdout or "").strip()
        return {
            "version": "1",
            "generated_at": _iso_now(),
            "sessions": [
                {
                    "session_id": item["session_id"],
                    "display_name": item["display_name"],
                    "state": item["state"],
                    "last_seen_at": item["last_seen_at"],
                    "active": (now_epoch - item["last_seen_epoch"]) < self.inactive_ttl_sec,
                    "originator": item.get("originator", "Codex Desktop"),
                    "cwd": item.get("cwd", ""),
                    "cwd_basename": item.get("cwd_basename", ""),
                    "last_event_type": item.get("last_event_type", ""),
                    "branch": item.get("branch", ""),
                    "agent_brand": item.get("agent_brand", "codex"),
                    "has_real_user_input": bool(item.get("has_real_user_input", False)),
                    "context": item.get("context", {}),
                }
                for item in ordered
            ],
        }

    def _collect_history_from_files(self) -> dict[str, dict[str, Any]]:
        if not self.session_dir.exists():
            return {}
        try:
            paths = [path for path in self.session_dir.rglob("*.jsonl") if path.is_file()]
        except PermissionError:
            return {}

        sessions: dict[str, dict[str, Any]] = {}
        for path in paths:
            cursor = _FileCursor(
                path=path,
                offset=0,
                inode=0,
                session_id=self.codex_parser.extract_session_id_from_path(path),
            )
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line in handle:
                        self.codex_parser.collect_history_from_line(line, cursor, sessions)
            except OSError:
                continue
        return sessions

    async def get_health(self) -> dict[str, Any]:
        ws_clients = await self._ws.count()
        async with self._sessions_lock:
            active_count = sum(1 for x in self._sessions.values() if x.active)
        ingest_lag_ms = None
        if self.latest_event_epoch > 0:
            ingest_lag_ms = int((time.time() - self.latest_event_epoch) * 1000)
        return {
            "status": "OK" if not self.degraded_reason else "DEGRADED",
            "enabled": self.enabled,
            "session_dir": str(self.session_dir),
            "source_version": self.source_version,
            "events_ingested_total": self.events_ingested_total,
            "events_dropped_total": self.events_dropped_total,
            "ingest_lag_ms": ingest_lag_ms,
            "ws_clients": ws_clients,
            "session_active_count": active_count,
            "degraded_reason": self.degraded_reason,
        }

    async def _watch_loop(self) -> None:
        while True:
            try:
                await self._scan_once()
                if self.degraded_reason.startswith("scan:"):
                    self.degraded_reason = ""
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.events_dropped_total += 1
                self.degraded_reason = f"scan:{exc}"
                logger.exception("Session bridge scan failed: %s", exc)
            try:
                await self._scan_once_claude()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Claude session scan failed: %s", exc)
            await asyncio.sleep(self.scan_interval_sec)

    async def _tick_loop(self) -> None:
        while True:
            try:
                emitted: list[dict[str, Any]] = []
                now_epoch = time.time()
                now_mono = time.monotonic()

                async with self._sessions_lock:
                    for session in self._sessions.values():
                        if session.pending_state and now_mono >= session.pending_due_mono:
                            previous_state = session.state
                            session.state = session.pending_state
                            session.pending_state = None
                            session.pending_due_mono = 0.0
                            session.last_state_change_mono = now_mono
                            if previous_state != session.state:
                                logger.info("session state: %s %s -> %s", session.session_id, previous_state, session.state)
                            emitted.append(self._build_state_event(session))

                        if session.idle_due_epoch and now_epoch >= session.idle_due_epoch:
                            session.idle_due_epoch = None
                            previous_state = session.state
                            if self.codex_parser._schedule_state_transition(session, "IDLE"):
                                if previous_state != session.state:
                                    logger.info("session state: %s %s -> IDLE", session.session_id, previous_state)
                                emitted.append(self._build_state_event(session))

                        if session.active and (now_epoch - session.last_seen_epoch) >= self.inactive_ttl_sec:
                            session.active = False
                            session.pending_state = None
                            session.idle_due_epoch = None
                            if session.state != "IDLE":
                                session.state = "IDLE"
                                session.last_state_change_mono = now_mono
                            logger.info("session offline: %s", session.session_id)
                            emitted.append(self._build_state_event(session, inactive=True))

                for event in emitted:
                    await self._broadcast(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Session bridge tick loop failed")
            await asyncio.sleep(0.2)

    async def _scan_once(self) -> None:
        if not self.session_dir.exists():
            self.degraded_reason = f"scan:session dir not found ({self.session_dir})"
            return

        try:
            current_paths = {
                str(path): path
                for path in self.session_dir.rglob("*.jsonl")
                if path.is_file()
            }
        except PermissionError as exc:
            self.degraded_reason = f"scan:permission denied ({exc})"
            return

        removed_keys = set(self._files.keys()) - set(current_paths.keys())
        for key in removed_keys:
            self._files.pop(key, None)

        for key, path in current_paths.items():
            try:
                await self.codex_parser.consume_file(path)
            except (OSError, ValueError) as exc:
                self.events_dropped_total += 1
                self.degraded_reason = f"scan:file read failed ({exc})"
                logger.warning("Session bridge read failed: %s (%s)", path, exc)

    async def _scan_once_claude(self) -> None:
        """Scan ~/.claude/projects/**/*.jsonl for Claude Code sessions."""
        if not self.claude_session_dir.exists():
            return
        try:
            current_paths = {
                str(path): path
                for path in self.claude_session_dir.rglob("*.jsonl")
                if path.is_file()
            }
        except PermissionError:
            return

        removed_keys = set(self._claude_files.keys()) - set(current_paths.keys())
        for key in removed_keys:
            self._claude_files.pop(key, None)

        for key, path in current_paths.items():
            try:
                await self.claude_parser.consume_file(path)
            except (OSError, ValueError) as exc:
                logger.warning("Claude session bridge read failed: %s (%s)", path, exc)

        await self._idle_stale_claude_sessions()

    async def _idle_stale_claude_sessions(self) -> None:
        """Force IDLE for Claude sessions stuck in a non-IDLE state with no recent events."""
        now_epoch = time.time()
        stale_threshold = 30.0
        emitted: list[dict[str, Any]] = []
        async with self._sessions_lock:
            for session in self._sessions.values():
                if session.agent_brand != "claude":
                    continue
                if session.state == "IDLE":
                    continue
                if not session.active:
                    continue
                age = now_epoch - session.last_seen_epoch
                if age >= stale_threshold:
                    session.state = "IDLE"
                    session.last_state_change_mono = time.monotonic()
                    session.pending_state = None
                    session.pending_due_mono = 0.0
                    session.last_event_type = "task_complete"
                    emitted.append(self._build_state_event(session))
        for event in emitted:
            await self._broadcast(event)

    def _new_session(self, session_id: str, ts: str) -> _SessionRecord:
        ts_epoch = _ts_to_epoch(ts)
        return _SessionRecord(
            session_id=session_id,
            display_name=f"session-{session_id[:8]}",
            last_seen_at=ts,
            last_seen_epoch=ts_epoch,
            active=(time.time() - ts_epoch) < self.inactive_ttl_sec,
        )

    @staticmethod
    def _context_payload(session: _SessionRecord) -> dict[str, Any]:
        return {
            "model": session.model,
            "effort": session.effort,
            "persona_id": session.persona_id,
            "persona_name": session.persona_name,
            "persona_content": session.persona_content,
            "permission_mode": _normalize_permission_mode(session.permission_mode),
            "approval_policy": session.approval_policy,
            "sandbox_mode": session.sandbox_mode,
            "plan_mode": session.plan_mode,
            "plan_mode_fallback": session.plan_mode_fallback,
            "total_tokens": session.total_tokens,
            "model_context_window": session.model_context_window,
            "primary_rate_remaining_percent": session.primary_rate_remaining_percent,
            "secondary_rate_remaining_percent": session.secondary_rate_remaining_percent,
        }

    def _build_state_event(self, session: _SessionRecord, inactive: bool = False) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "originator": session.originator,
            "cwd": session.cwd,
            "cwd_basename": session.cwd_basename,
            "last_event_type": session.last_event_type,
            "branch": session.branch,
            "context": self._context_payload(session),
        }
        if inactive:
            meta["inactive"] = True

        return {
            "version": "1",
            "event": "session_state",
            "session_id": session.session_id,
            "display_name": session.display_name,
            "state": session.state,
            "ts": session.last_seen_at,
            "source": "claude_jsonl" if getattr(session, "agent_brand", "codex") == "claude" else "codex_jsonl",
            "agent_brand": getattr(session, "agent_brand", "codex"),
            "has_real_user_input": bool(getattr(session, "has_real_user_input", False)),
            "meta": meta,
        }

    async def _broadcast(self, event: dict[str, Any]) -> None:
        await self._ws.broadcast(event)


__all__ = ["SessionBridgeService"]
