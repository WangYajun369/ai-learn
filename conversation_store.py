"""
SQLite 会话记录存储模块

记录每次 Agent 会话的完整信息：
- 会话元信息（模型、启动时间、状态）
- 用户问题与 Agent 回答
- 工具调用链（工具名、参数、返回结果、耗时）

存储路径：./conversations.db
"""

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime

DEFAULT_DB_PATH = Path(__file__).parent / "object_db" / "conversations.db"


class ConversationStore:
    """SQLite 会话记录存储"""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._session_id: str | None = None

    # ── 数据库连接与初始化 ──

    def connect(self, silent: bool = False) -> bool:
        """连接数据库并建表，返回是否成功"""
        try:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._init_tables()
            if not silent:
                print(f"💬 会话记录已连接（{self.db_path}）")
            return True
        except Exception as e:
            if not silent:
                print(f"⚠️ 会话记录数据库连接失败：{e}")
            return False

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_tables(self):
        """创建表结构"""
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                model       TEXT NOT NULL,
                started_at  TEXT NOT NULL,
                ended_at    TEXT,
                turn_count  INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'active'   -- active / closed
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                role        TEXT NOT NULL,           -- user / assistant
                content     TEXT,
                turn_order  INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                message_id  INTEGER,
                tool_name   TEXT NOT NULL,
                arguments   TEXT,                    -- JSON
                result      TEXT,                    -- 工具返回文本
                duration_ms INTEGER,                 -- 耗时（毫秒）
                created_at  TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (message_id) REFERENCES messages(id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_toolcalls_session ON tool_calls(session_id);
        """)
        self._conn.commit()

    # ── 会话管理 ──

    def create_session(self, model: str) -> str:
        """创建新会话，返回 session_id"""
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO sessions (id, model, started_at, status) VALUES (?, ?, ?, ?)",
            (self._session_id, model, now, "active"),
        )
        self._conn.commit()
        return self._session_id

    def close_session(self):
        """关闭当前会话"""
        if not self._session_id:
            return
        now = datetime.now().isoformat(timespec="seconds")
        # 计算对话轮次
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id=? AND role='user'",
            (self._session_id,),
        ).fetchone()
        self._conn.execute(
            "UPDATE sessions SET ended_at=?, turn_count=?, status='closed' WHERE id=?",
            (now, row["cnt"], self._session_id),
        )
        self._conn.commit()

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def switch_to_session(self, session_id: str):
        """切换到指定会话，后续消息将记录到该会话下"""
        self._session_id = session_id
        # 将会话状态恢复为 active
        self._conn.execute(
            "UPDATE sessions SET status='active', ended_at=NULL WHERE id=?",
            (session_id,),
        )
        self._conn.commit()

    def restore_session_messages(self, session_id: str) -> list[dict]:
        """
        从历史会话中重建消息列表（用于恢复上下文）。
        返回可直接追加到 messages 的 list[dict]。
        不包含 system 消息（由 agent.py 的 base_system_prompt 负责）。
        """
        msgs = self._conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY turn_order",
            (session_id,),
        ).fetchall()

        result = []
        for m in msgs:
            content = m["content"]
            if not content or not content.strip():
                continue
            if m["role"] in ("user", "assistant"):
                result.append({"role": m["role"], "content": content})

        return result

    def delete_session(self, session_id: str) -> int:
        """删除指定会话及其所有消息和工具调用，返回删除的消息数"""
        msg_count = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id=?", (session_id,)
        ).fetchone()["cnt"]
        self._conn.execute("DELETE FROM tool_calls WHERE session_id=?", (session_id,))
        self._conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self._conn.commit()
        # 如果删除的是当前会话，重置 session_id
        if self._session_id == session_id:
            self._session_id = None
        return msg_count

    def clear_all(self) -> int:
        """清空所有会话数据，返回删除的会话数"""
        count = self._conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
        self._conn.execute("DELETE FROM tool_calls")
        self._conn.execute("DELETE FROM messages")
        self._conn.execute("DELETE FROM sessions")
        self._conn.commit()
        self._session_id = None
        return count

    # ── 消息记录 ──

    def save_message(self, role: str, content: str) -> int:
        """保存一条消息（user/assistant），返回 message_id"""
        if not self._session_id:
            return 0
        now = datetime.now().isoformat(timespec="seconds")
        # 计算 turn_order
        row = self._conn.execute(
            "SELECT COALESCE(MAX(turn_order), 0) + 1 as next_order FROM messages WHERE session_id=?",
            (self._session_id,),
        ).fetchone()
        cur = self._conn.execute(
            "INSERT INTO messages (session_id, role, content, turn_order, created_at) VALUES (?, ?, ?, ?, ?)",
            (self._session_id, role, content, row["next_order"], now),
        )
        self._conn.commit()
        return cur.lastrowid

    # ── 工具调用记录 ──

    def save_tool_call(
        self,
        tool_name: str,
        arguments: dict,
        result: str,
        duration_ms: int | None = None,
        message_id: int | None = None,
    ):
        """记录一次工具调用"""
        if not self._session_id:
            return
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO tool_calls (session_id, message_id, tool_name, arguments, result, duration_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._session_id,
                message_id,
                tool_name,
                json.dumps(arguments, ensure_ascii=False),
                result[:5000],  # 截断过长的返回结果
                duration_ms,
                now,
            ),
        )
        self._conn.commit()

    # ── 查询 ──

    def list_sessions(self, limit: int = 10) -> list[dict]:
        """列出最近的会话"""
        rows = self._conn.execute(
            "SELECT id, model, started_at, ended_at, turn_count, status "
            "FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session_detail(self, session_id: str) -> dict | None:
        """获取会话详情（含消息和工具调用链）"""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not row:
            return None

        session = dict(row)

        # 获取所有消息
        messages = self._conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY turn_order",
            (session_id,),
        ).fetchall()

        # 获取所有工具调用
        tool_calls = self._conn.execute(
            "SELECT * FROM tool_calls WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()

        session["messages"] = [dict(m) for m in messages]
        session["tool_calls"] = [dict(t) for t in tool_calls]
        return session

    def get_stats(self) -> dict:
        """获取会话统计"""
        total = self._conn.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
        active = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions WHERE status='active'"
        ).fetchone()["cnt"]
        total_msgs = self._conn.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()["cnt"]
        total_tools = self._conn.execute("SELECT COUNT(*) as cnt FROM tool_calls").fetchone()["cnt"]
        return {
            "total_sessions": total,
            "active_sessions": active,
            "total_messages": total_msgs,
            "total_tool_calls": total_tools,
        }
