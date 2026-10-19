"""Sessions, State, Memory, Artifacts, and Context management for ADK applications."""

from __future__ import annotations

import copy
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class SessionNotFoundError(KeyError):
    """Raised when appending events or mutating state on a non-existent session (ADK v2.9.0+ semantics)."""


@dataclass
class SessionEvent:
    """Represents an immutable conversational or state delta event within a Session."""

    invocation_id: str
    author: str
    role: str
    text: str
    state_delta: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SessionRecord:
    """Isolated session container scoped by (app_name, user_id, session_id)."""

    app_name: str
    user_id: str
    session_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    events: List[SessionEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LocalSessionService:
    """ADK-compatible local session service supporting In-Memory and SQLite persistence, rewind, and migration."""

    def __init__(self, sqlite_path: Optional[Path] = None) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self.sqlite_path = sqlite_path
        if self.sqlite_path:
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        assert self.sqlite_path is not None
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.sqlite_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS adk_sessions (
                    composite_key TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _key(app_name: str, user_id: str, session_id: str) -> str:
        for label, val in (("app_name", app_name), ("user_id", user_id), ("session_id", session_id)):
            if not val or "/" in val or ".." in val:
                raise ValueError(f"Invalid {label}: '{val}'. Must be non-empty and free of path traversal segments.")
        return f"{app_name}:{user_id}:{session_id.strip()}"

    def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: Optional[str] = None,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        sid = (session_id or f"sess-{uuid.uuid4().hex[:10]}").strip()
        key = self._key(app_name, user_id, sid)
        rec = SessionRecord(
            app_name=app_name,
            user_id=user_id,
            session_id=sid,
            state=copy.deepcopy(initial_state or {}),
        )
        self._sessions[key] = rec
        self._persist_if_needed(key, rec)
        return copy.deepcopy(rec)

    def get_session(self, *, app_name: str, user_id: str, session_id: str) -> SessionRecord:
        key = self._key(app_name, user_id, session_id)
        if key not in self._sessions and self.sqlite_path:
            with sqlite3.connect(str(self.sqlite_path)) as conn:
                row = conn.execute(
                    "SELECT payload_json FROM adk_sessions WHERE composite_key = ?", (key,)
                ).fetchone()
                if row:
                    data = json.loads(row[0])
                    events = [SessionEvent(**e) for e in data.get("events", [])]
                    self._sessions[key] = SessionRecord(
                        app_name=data["app_name"],
                        user_id=data["user_id"],
                        session_id=data["session_id"],
                        state=data.get("state", {}),
                        events=events,
                        created_at=data.get("created_at", ""),
                    )
        if key not in self._sessions:
            raise SessionNotFoundError(f"Session not found for key '{key}'")
        return copy.deepcopy(self._sessions[key])

    def append_event(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        event: SessionEvent,
    ) -> SessionRecord:
        """Append event to session; raises SessionNotFoundError if session does not exist (ADK v2.9.0+)."""
        key = self._key(app_name, user_id, session_id)
        if key not in self._sessions:
            _ = self.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        rec = self._sessions[key]
        rec.events.append(copy.deepcopy(event))
        if event.state_delta:
            rec.state.update(copy.deepcopy(event.state_delta))
        self._persist_if_needed(key, rec)
        return copy.deepcopy(rec)

    def rewind_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        target_invocation_id: str,
    ) -> SessionRecord:
        """Rewind session history prior to target_invocation_id and recompute state."""
        key = self._key(app_name, user_id, session_id)
        rec = self._sessions.get(key)
        if not rec:
            raise SessionNotFoundError(f"Session not found for key '{key}'")
        kept_events: List[SessionEvent] = []
        recomputed_state: Dict[str, Any] = {}
        for ev in rec.events:
            if ev.invocation_id == target_invocation_id:
                break
            kept_events.append(ev)
            recomputed_state.update(copy.deepcopy(ev.state_delta))
        rec.events = kept_events
        rec.state = recomputed_state
        self._persist_if_needed(key, rec)
        return copy.deepcopy(rec)

    def compact_context(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        keep_recent_turns: int = 4,
    ) -> Dict[str, Any]:
        """Summarize older conversational events while excluding credential-request events (ADK v2.11.0+)."""
        rec = self.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
        safe_events = [
            e for e in rec.events if "credential_request" not in e.text.lower()
        ]
        if len(safe_events) <= keep_recent_turns:
            return {
                "compacted": False,
                "summary": "",
                "retained_events": len(safe_events),
            }
        older = safe_events[:-keep_recent_turns]
        summary_text = " | ".join(f"{e.author}: {e.text[:60]}" for e in older)
        return {
            "compacted": True,
            "summarized_event_count": len(older),
            "retained_events": keep_recent_turns,
            "summary": f"[Compacted History ({len(older)} events)]: {summary_text}",
        }

    def _persist_if_needed(self, key: str, rec: SessionRecord) -> None:
        if not self.sqlite_path:
            return
        payload = {
            "app_name": rec.app_name,
            "user_id": rec.user_id,
            "session_id": rec.session_id,
            "state": rec.state,
            "events": [e.__dict__ for e in rec.events],
            "created_at": rec.created_at,
        }
        with sqlite3.connect(str(self.sqlite_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO adk_sessions
                (composite_key, app_name, user_id, session_id, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    rec.app_name,
                    rec.user_id,
                    rec.session_id,
                    json.dumps(payload, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


class SQLiteMemoryService:
    """Local SQLite MemoryService (`sqlite://`) separate from session storage (ADK v2.11.0+ semantics)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS adk_memories (
                    memory_id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def ingest_session(self, session: SessionRecord, topic: str = "general") -> int:
        """Extract durable long-term memories from a completed session."""
        inserted = 0
        with sqlite3.connect(str(self.db_path)) as conn:
            for ev in session.events:
                if ev.text.strip():
                    mem_id = f"mem-{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        """
                        INSERT INTO adk_memories (memory_id, app_name, user_id, topic, content, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            mem_id,
                            session.app_name,
                            session.user_id,
                            topic,
                            ev.text.strip(),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    inserted += 1
        return inserted

    def search_memories(self, *, app_name: str, user_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search long-term memories isolated by app_name and user_id where all query terms match."""
        terms = [t.lower() for t in query.split() if t.strip()]
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                """
                SELECT memory_id, topic, content, created_at
                FROM adk_memories
                WHERE app_name = ? AND user_id = ?
                ORDER BY created_at DESC
                """,
                (app_name, user_id),
            ).fetchall()
        matches: List[Dict[str, Any]] = []
        for mem_id, topic, content, created_at in rows:
            haystack = f"{topic} {content}".lower()
            if not terms or all(t in haystack for t in terms):
                matches.append(
                    {
                        "memory_id": mem_id,
                        "topic": topic,
                        "content": content,
                        "created_at": created_at,
                    }
                )
                if len(matches) >= limit:
                    break
        return matches


class IsolatedArtifactService:
    """ADK ArtifactService with strict user/app/session scoping, versioning, and caller-mutation isolation (ADK v2.12.0)."""

    def __init__(self) -> None:
        self._store: Dict[str, List[Dict[str, Any]]] = {}

    @staticmethod
    def _validate_filename(filename: str) -> str:
        if not filename or ".." in filename or filename.startswith("/") or "\\" in filename:
            raise ValueError(f"Invalid artifact filename '{filename}': path traversal segments are prohibited.")
        return filename

    def _scope_key(self, *, app_name: str, user_id: str, session_id: str, filename: str) -> str:
        clean_name = self._validate_filename(filename)
        if clean_name.startswith("user:"):
            return f"{app_name}:{user_id}:user_scope:{clean_name}"
        return f"{app_name}:{user_id}:{session_id}:{clean_name}"

    def save_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        data: bytes,
        mime_type: str = "application/octet-stream",
    ) -> int:
        """Save a new immutable version of an artifact and return its 0-indexed version number."""
        key = self._scope_key(app_name=app_name, user_id=user_id, session_id=session_id, filename=filename)
        versions = self._store.setdefault(key, [])
        version_num = len(versions)
        versions.append(
            {
                "version": version_num,
                "data": bytes(data),
                "mime_type": mime_type,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return version_num

    def load_artifact(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        filename: str,
        version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load an artifact version; returns None for negative versions (ADK v2.11.0 fix) or missing keys."""
        if version is not None and version < 0:
            return None
        key = self._scope_key(app_name=app_name, user_id=user_id, session_id=session_id, filename=filename)
        versions = self._store.get(key)
        if not versions:
            return None
        idx = version if version is not None else (len(versions) - 1)
        if idx >= len(versions):
            return None
        return copy.deepcopy(versions[idx])
