"""
向量数据库长期记忆模块

使用 ChromaDB 存储对话摘要作为向量记忆。
启动时自动连接，对话结束时用 LLM 提取摘要并存入。

存储路径：./memory_db/（ChromaDB 持久化目录）
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

# 默认持久化目录
DEFAULT_DB_PATH = Path(__file__).parent / "object_db" / "memory_db"


class MemoryStore:
    """
    基于 ChromaDB 的向量记忆存储。

    每条记忆包含：
      - content: 记忆文本内容
      - metadata: {session_id, timestamp, turn_count, topics}
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self._client = None
        self._collection = None

    @property
    def is_available(self) -> bool:
        """检查 ChromaDB 是否可用"""
        try:
            import chromadb  # noqa: F401
            return True
        except ImportError:
            return False

    def connect(self, silent: bool = False) -> bool:
        """
        连接向量数据库。返回是否成功。
        失败时降级为纯文本日志模式。
        """
        try:
            import chromadb
        except ImportError:
            if not silent:
                print("⚠️ chromadb 未安装，长期记忆功能不可用（uv add chromadb）")
            return False

        try:
            self._client = chromadb.PersistentClient(path=str(self.db_path))
            self._collection = self._client.get_or_create_collection(
                name="conversation_memories",
                metadata={"hnsw:space": "cosine"},
            )
            count = self._collection.count()
            if not silent:
                print(f"🧠 长期记忆已连接（{self.db_path}，{count} 条记忆）")
            return True
        except Exception as e:
            if not silent:
                print(f"⚠️ 向量数据库连接失败：{e}")
            return False

    def search(
        self,
        query: str,
        n_results: int = 5,
        session_id: str | None = None,
    ) -> list[dict]:
        """
        语义检索相关记忆。

        返回 [{"content": str, "metadata": dict, "distance": float}, ...]
        """
        if not self._collection:
            return []

        where_filter = None
        if session_id:
            where_filter = {"session_id": session_id}

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, max(1, self._collection.count())),
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
            memories = []
            if results and results["documents"]:
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    memories.append({
                        "content": doc,
                        "metadata": meta or {},
                        "distance": dist,
                    })
            return memories
        except Exception as e:
            print(f"⚠️ 记忆检索失败：{e}")
            return []

    def save(self, content: str, session_id: str, topics: list[str] | None = None):
        """保存一条新记忆"""
        if not self._collection:
            return

        now = datetime.now().isoformat(timespec="seconds")
        memory_id = f"{session_id}_{now}"

        metadata = {
            "session_id": session_id,
            "timestamp": now,
            "topics": json.dumps(topics or [], ensure_ascii=False),
        }

        try:
            self._collection.upsert(
                ids=[memory_id],
                documents=[content],
                metadatas=[metadata],
            )
            print(f"   💾 记忆已保存（{memory_id}）")
        except Exception as e:
            print(f"⚠️ 记忆保存失败：{e}")

    def get_all(self, limit: int = 20) -> list[dict]:
        """获取最近的记忆（按时间倒序）"""
        if not self._collection:
            return []

        try:
            count = self._collection.count()
            if count == 0:
                return []
            results = self._collection.get(
                limit=min(limit, count),
                include=["documents", "metadatas"],
            )
            memories = []
            if results and results["documents"]:
                for doc, meta in zip(results["documents"], results["metadatas"]):
                    memories.append({
                        "content": doc,
                        "metadata": meta or {},
                    })
            return memories
        except Exception as e:
            print(f"⚠️ 获取记忆失败：{e}")
            return []

    def delete_session(self, session_id: str) -> int:
        """删除指定会话的所有记忆，返回删除数量"""
        if not self._collection:
            return 0

        try:
            # 先查出所有属于该 session 的 ID
            count = self._collection.count()
            if count == 0:
                return 0
            results = self._collection.get(
                where={"session_id": session_id},
                include=[],
            )
            if results and results["ids"]:
                self._collection.delete(ids=results["ids"])
                return len(results["ids"])
            return 0
        except Exception as e:
            print(f"⚠️ 删除记忆失败：{e}")
            return 0

    def clear_all(self) -> int:
        """清空所有记忆，返回删除数量"""
        if not self._collection:
            return 0

        try:
            count = self._collection.count()
            client = self._client
            client.delete_collection("conversation_memories")
            self._collection = client.get_or_create_collection(
                name="conversation_memories",
                metadata={"hnsw:space": "cosine"},
            )
            return count
        except Exception as e:
            print(f"⚠️ 清空记忆失败：{e}")
            return 0

    @staticmethod
    def build_summary_prompt(messages: list[dict]) -> str:
        """
        构建让 LLM 提取对话摘要的 prompt。
        摘要将作为向量记忆存入数据库。
        """
        # 提取对话内容（跳过 system 消息，保留核心问答）
        conversation_lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                continue
            if not content or not content.strip():
                continue
            # 截断过长的内容
            content = content.strip()[:500]
            if role == "user":
                conversation_lines.append(f"用户：{content}")
            elif role == "assistant":
                conversation_lines.append(f"助手：{content}")

        conversation_text = "\n".join(conversation_lines)

        return (
            "请从以下对话中提取值得长期记住的关键信息。生成一段简洁的摘要（3-5句话），"
            "包括：\n"
            "1. 用户的核心需求或偏好\n"
            "2. 涉及的产品/区域/指标\n"
            "3. 重要的分析结论或决策\n\n"
            "如果对话只是简单的寒暄或无意义的交互，请回复「无」。\n\n"
            f"对话内容：\n{conversation_text}\n\n"
            "请直接输出摘要文本，不要加额外说明："
        )


def generate_memory_id() -> str:
    """生成唯一的会话 ID"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
