"""
用户画像持久化模块

用 SQLite 存储跨会话的用户画像，包含：
- preferences：用户偏好（维度、指标、格式等）
- constraints：已确认的约束（时间范围、区域、条件等）
- workflows：归纳出的工作流模式
- stats：进化统计

存储路径：./object_db/user_profile.db
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "object_db" / "user_profile.db"


class UserProfileStore:
    """
    用户画像存储。

    三类画像数据：
      1. preferences — 用户偏好（如「偏好区域维度分析」「关注环比增长率」）
      2. constraints — 已确认约束（如「默认时间范围=Q2」「关注区域=华东+华南」）
      3. workflows — 工作流模式（如「总览→区域拆分→异常检测」）
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self, silent: bool = False) -> bool:
        """连接数据库并建表"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables()
            if not silent:
                stats = self.get_stats()
                print(
                    f"🧬 用户画像已连接（{self.db_path}，"
                    f"{stats['total_items']} 条画像数据）"
                )
            return True
        except Exception as e:
            if not silent:
                print(f"⚠️ 用户画像数据库连接失败：{e}")
            return False

    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_tables(self):
        cur = self._conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS profile_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,          -- preference / constraint / workflow
                content     TEXT NOT NULL,          -- 画像内容文本
                source      TEXT,                   -- 来源说明（哪次对话发现的）
                confidence  REAL DEFAULT 0.5,       -- 置信度 0.0~1.0
                occurrence  INTEGER DEFAULT 1,      -- 出现次数
                first_seen  TEXT NOT NULL,          -- 首次发现时间
                last_seen   TEXT NOT NULL,          -- 最近确认时间
                is_active   INTEGER DEFAULT 1       -- 是否有效（1=有效, 0=已废弃）
            );

            CREATE INDEX IF NOT EXISTS idx_profile_category
                ON profile_items(category, is_active);
        """)
        self._conn.commit()

    # ── 画像数据操作 ──

    def add_item(
        self,
        category: str,
        content: str,
        source: str = "",
        confidence: float = 0.5,
    ) -> int:
        """
        添加一条画像数据（去重：同类别+同内容则合并）。

        Args:
            category: preference / constraint / workflow
            content: 画像内容
            source: 来源描述
            confidence: 置信度

        Returns:
            记录 ID（新增或已存在的）
        """
        if not self._conn:
            return 0

        now = datetime.now().isoformat(timespec="seconds")

        # 去重检查：同类别+同内容 → 合并（提升出现次数和置信度）
        existing = self._conn.execute(
            "SELECT id, occurrence, confidence FROM profile_items "
            "WHERE category=? AND content=? AND is_active=1",
            (category, content),
        ).fetchone()

        if existing:
            new_occurrence = existing["occurrence"] + 1
            new_confidence = min(1.0, existing["confidence"] + 0.1)
            self._conn.execute(
                "UPDATE profile_items SET occurrence=?, confidence=?, last_seen=?, source=? "
                "WHERE id=?",
                (new_occurrence, new_confidence, now, source or None, existing["id"]),
            )
            self._conn.commit()
            return existing["id"]
        else:
            cur = self._conn.execute(
                "INSERT INTO profile_items "
                "(category, content, source, confidence, occurrence, first_seen, last_seen, is_active) "
                "VALUES (?, ?, ?, ?, 1, ?, ?, 1)",
                (category, content, source or None, confidence, now, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_all_active(self) -> list[dict]:
        """获取所有有效的画像数据，按类别分组"""
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT * FROM profile_items WHERE is_active=1 "
            "ORDER BY category, occurrence DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_category(self, category: str) -> list[dict]:
        """获取指定类别的画像数据"""
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT * FROM profile_items WHERE category=? AND is_active=1 "
            "ORDER BY occurrence DESC, confidence DESC",
            (category,),
        ).fetchall()
        return [dict(r) for r in rows]

    def deactivate_item(self, item_id: int) -> bool:
        """软删除一条画像数据"""
        if not self._conn:
            return False
        self._conn.execute(
            "UPDATE profile_items SET is_active=0 WHERE id=?", (item_id,)
        )
        self._conn.commit()
        return True

    def clear_category(self, category: str) -> int:
        """清空指定类别的所有画像"""
        if not self._conn:
            return 0
        cur = self._conn.execute(
            "UPDATE profile_items SET is_active=0 WHERE category=? AND is_active=1",
            (category,),
        )
        self._conn.commit()
        return cur.rowcount

    def clear_all(self) -> int:
        """清空所有画像数据"""
        if not self._conn:
            return 0
        count = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM profile_items WHERE is_active=1"
        ).fetchone()["cnt"]
        self._conn.execute("UPDATE profile_items SET is_active=0 WHERE is_active=1")
        self._conn.commit()
        return count

    # ── 统计 ──

    def get_stats(self) -> dict:
        """获取画像统计"""
        if not self._conn:
            return {"total_items": 0, "preferences": 0, "constraints": 0, "workflows": 0}
        total = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM profile_items WHERE is_active=1"
        ).fetchone()["cnt"]
        prefs = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM profile_items WHERE category='preference' AND is_active=1"
        ).fetchone()["cnt"]
        constrs = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM profile_items WHERE category='constraint' AND is_active=1"
        ).fetchone()["cnt"]
        flows = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM profile_items WHERE category='workflow' AND is_active=1"
        ).fetchone()["cnt"]
        return {
            "total_items": total,
            "preferences": prefs,
            "constraints": constrs,
            "workflows": flows,
        }

    # ── 格式化输出 ──

    def format_for_prompt(self) -> str:
        """
        将用户画像格式化为注入 system prompt 的文本。
        仅包含置信度 >= 0.5 且出现次数 >= 2 的条目（确保稳定性）。
        """
        items = self.get_all_active()
        # 过滤：置信度 >= 0.5 或出现次数 >= 2
        stable_items = [
            i for i in items
            if i["confidence"] >= 0.5 or i["occurrence"] >= 2
        ]
        if not stable_items:
            return ""

        lines = ["【用户画像（由 Agent 学习积累，请参考）】"]

        categories = {
            "preference": "偏好习惯",
            "constraint": "已确认约束",
            "workflow": "工作流模式",
        }
        for cat_key, cat_label in categories.items():
            cat_items = [i for i in stable_items if i["category"] == cat_key]
            if cat_items:
                lines.append(f"\n{cat_label}：")
                for item in cat_items:
                    lines.append(f"  - {item['content']}")

        return "\n".join(lines)

    def format_for_display(self) -> str:
        """格式化画像用于终端展示"""
        items = self.get_all_active()
        if not items:
            return "  （暂无画像数据，Agent 会在对话中自动学习积累）"

        lines = []
        categories = {
            "preference": "🏷️ 偏好习惯",
            "constraint": "📐 已确认约束",
            "workflow": "🔄 工作流模式",
        }
        for cat_key, cat_label in categories.items():
            cat_items = [i for i in items if i["category"] == cat_key]
            if cat_items:
                lines.append(f"\n  {cat_label}：")
                for item in cat_items:
                    conf = f"📊{item['confidence']:.1f}"
                    occ = f"×{item['occurrence']}"
                    lines.append(f"    • [{conf}|{occ}] {item['content']}")
                    if item.get("source"):
                        lines.append(f"      来源：{item['source']}")
        return "\n".join(lines)
