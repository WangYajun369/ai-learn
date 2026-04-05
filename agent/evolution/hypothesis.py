"""
假设管理模块

管理"待确认约束"队列：
- Observer 发现用户遗漏约束后，生成假设
- 下次相关对话时，Agent 主动温和提示
- 用户确认 → 转为已确认约束
- 用户否认 → 标记为已拒绝，不再提示

假设生命周期：pending → confirmed / rejected
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "object_db" / "user_profile.db"


class HypothesisStore:
    """
    假设约束队列管理。

    每条假设包含：
      - hypothesis: 假设内容（如「用户默认关注最近一个季度的数据」）
      - context: 发现该假设时的对话上下文摘要
      - status: pending / confirmed / rejected
      - trigger_keywords: 触发提示的关键词列表
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self, silent: bool = False) -> bool:
        """连接数据库并建表（复用 user_profile.db）"""
        try:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables()
            if not silent:
                stats = self.get_stats()
                print(f"💡 假设队列已连接（{stats['pending']} 条待确认假设）")
            return True
        except Exception as e:
            if not silent:
                print(f"⚠️ 假设队列连接失败：{e}")
            return False

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_tables(self):
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS hypotheses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hypothesis  TEXT NOT NULL,          -- 假设内容
                context     TEXT,                   -- 发现时的上下文
                status      TEXT DEFAULT 'pending', -- pending / confirmed / rejected
                trigger_keywords TEXT,              -- JSON: 触发关键词列表
                suggested_times INTEGER DEFAULT 0,  -- 已提示次数
                max_suggestions INTEGER DEFAULT 3,  -- 最大提示次数
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL,
                resolved_at TEXT                    -- 确认/拒绝的时间
            );

            CREATE INDEX IF NOT EXISTS idx_hypotheses_status
                ON hypotheses(status);
        """)
        self._conn.commit()

    # ── 假设操作 ──

    def add_hypothesis(
        self,
        hypothesis: str,
        context: str = "",
        trigger_keywords: list[str] | None = None,
    ) -> int:
        """
        添加一条新假设（去重检查）。

        Args:
            hypothesis: 假设内容
            context: 发现时的上下文
            trigger_keywords: 触发提示的关键词列表

        Returns:
            假设 ID，如果已存在则返回已有 ID
        """
        if not self._conn:
            return 0

        # 去重：相同假设内容且仍为 pending 的不重复添加
        existing = self._conn.execute(
            "SELECT id FROM hypotheses WHERE hypothesis=? AND status='pending'",
            (hypothesis,),
        ).fetchone()
        if existing:
            return existing["id"]

        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO hypotheses "
            "(hypothesis, context, status, trigger_keywords, first_seen, last_seen) "
            "VALUES (?, ?, 'pending', ?, ?, ?)",
            (
                hypothesis,
                context or None,
                json.dumps(trigger_keywords or [], ensure_ascii=False),
                now,
                now,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def confirm_hypothesis(self, hypothesis_id: int) -> bool:
        """确认一条假设（转为已确认）"""
        if not self._conn:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE hypotheses SET status='confirmed', resolved_at=? WHERE id=?",
            (now, hypothesis_id),
        )
        self._conn.commit()
        return True

    def confirm_by_content(self, hypothesis_text: str) -> bool:
        """通过假设内容确认"""
        if not self._conn:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE hypotheses SET status='confirmed', resolved_at=? "
            "WHERE hypothesis=? AND status='pending'",
            (now, hypothesis_text),
        )
        self._conn.commit()
        return True

    def reject_hypothesis(self, hypothesis_id: int) -> bool:
        """拒绝一条假设"""
        if not self._conn:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE hypotheses SET status='rejected', resolved_at=? WHERE id=?",
            (now, hypothesis_id),
        )
        self._conn.commit()
        return True

    def reject_by_content(self, hypothesis_text: str) -> bool:
        """通过假设内容拒绝"""
        if not self._conn:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE hypotheses SET status='rejected', resolved_at=? "
            "WHERE hypothesis=? AND status='pending'",
            (now, hypothesis_text),
        )
        self._conn.commit()
        return True

    # ── 查询 ──

    def get_pending(self, limit: int = 10) -> list[dict]:
        """获取待确认的假设列表"""
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT * FROM hypotheses WHERE status='pending' "
            "AND suggested_times < max_suggestions "
            "ORDER BY first_seen ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def find_triggered(self, user_input: str, limit: int = 3) -> list[dict]:
        """
        根据用户输入匹配触发的假设。

        检查 pending 状态的假设，其 trigger_keywords 是否出现在用户输入中。
        返回匹配的假设列表（按相关度排序）。
        """
        if not self._conn:
            return []

        pending = self._conn.execute(
            "SELECT * FROM hypotheses WHERE status='pending' "
            "AND suggested_times < max_suggestions",
        ).fetchall()

        triggered = []
        for row in pending:
            item = dict(row)
            keywords = []
            try:
                keywords = json.loads(item.get("trigger_keywords", "[]"))
            except (json.JSONDecodeError, TypeError):
                pass

            if not keywords:
                # 没有关键词的假设，用假设内容本身做模糊匹配
                keywords = [item["hypothesis"][:10]]

            match_count = sum(1 for kw in keywords if kw in user_input)
            if match_count > 0:
                item["_match_score"] = match_count
                triggered.append(item)

        # 按匹配分数排序
        triggered.sort(key=lambda x: x["_match_score"], reverse=True)
        return triggered[:limit]

    def get_all(self, status: str | None = None, limit: int = 20) -> list[dict]:
        """获取假设列表"""
        if not self._conn:
            return []
        if status:
            rows = self._conn.execute(
                "SELECT * FROM hypotheses WHERE status=? ORDER BY first_seen DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM hypotheses ORDER BY first_seen DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── 提示次数管理 ──

    def increment_suggestion(self, hypothesis_id: int) -> bool:
        """增加假设的提示次数"""
        if not self._conn:
            return False
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE hypotheses SET suggested_times=suggested_times+1, last_seen=? WHERE id=?",
            (now, hypothesis_id),
        )
        self._conn.commit()
        return True

    # ── 统计 ──

    def get_stats(self) -> dict:
        if not self._conn:
            return {"pending": 0, "confirmed": 0, "rejected": 0, "total": 0}
        pending = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM hypotheses WHERE status='pending'"
        ).fetchone()["cnt"]
        confirmed = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM hypotheses WHERE status='confirmed'"
        ).fetchone()["cnt"]
        rejected = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM hypotheses WHERE status='rejected'"
        ).fetchone()["cnt"]
        return {
            "pending": pending,
            "confirmed": confirmed,
            "rejected": rejected,
            "total": pending + confirmed + rejected,
        }

    # ── 格式化输出 ──

    def format_pending_for_prompt(self, user_input: str) -> str | None:
        """
        根据用户输入，检查是否有相关的待确认假设需要提示。
        返回格式化的提示文本，或 None（无需提示）。
        """
        triggered = self.find_triggered(user_input)
        if not triggered:
            return None

        lines = []
        for item in triggered:
            remaining = item["max_suggestions"] - item["suggested_times"]
            lines.append(
                f"💡 观察到您可能的需求：{item['hypothesis']}。"
                f"是否将此设为默认约束？（回复「是」确认，「否」取消，或忽略）"
            )
            # 更新提示次数
            self.increment_suggestion(item["id"])

        return "\n".join(lines) if lines else None

    def format_for_display(self) -> str:
        """格式化假设列表用于终端展示"""
        all_items = self.get_all()
        if not all_items:
            return "  （暂无假设记录）"

        status_labels = {
            "pending": "⏳ 待确认",
            "confirmed": "✅ 已确认",
            "rejected": "❌ 已拒绝",
        }
        lines = []
        for item in all_items:
            status = item["status"]
            label = status_labels.get(status, status)
            suggested = f"（已提示 {item['suggested_times']}/{item['max_suggestions']} 次）"
            lines.append(f"\n  {label} {suggested}")
            lines.append(f"    • {item['hypothesis']}")
            if item.get("context"):
                lines.append(f"      上下文：{item['context'][:60]}")
        return "\n".join(lines)
