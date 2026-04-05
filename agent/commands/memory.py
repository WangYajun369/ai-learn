"""
记忆管理命令处理器
"""

from memory_store import MemoryStore


class MemoryCommandHandler:
    """处理 /memory 开头的记忆管理命令"""

    def __init__(self, memory_store: MemoryStore, enabled: bool):
        self.memory_store = memory_store
        self.enabled = enabled

    def handle(self, user_input: str) -> bool:
        """
        处理记忆管理命令
        
        Args:
            user_input: 用户输入的命令
            
        Returns:
            True 表示命令已处理，False 表示未匹配
        """
        cmd = user_input.strip().lower()

        if not cmd.startswith("/memory"):
            return False

        parts = cmd.split(maxsplit=1)
        sub_cmd = parts[1] if len(parts) > 1 else ""

        if not self.enabled:
            print("⚠️ 向量数据库未连接，记忆功能不可用")
            return True

        if sub_cmd in ("", "list", "ls"):
            return self._handle_list()

        if sub_cmd.startswith("search "):
            return self._handle_search(user_input)

        if sub_cmd == "clear":
            return self._handle_clear()

        if sub_cmd.startswith("delete "):
            return self._handle_delete(user_input)

        if sub_cmd == "stats":
            return self._handle_stats()

        self._print_help()
        return True

    def _handle_list(self) -> bool:
        """列出所有记忆"""
        all_memories = self.memory_store.get_all(limit=10)
        if not all_memories:
            print("📚 暂无长期记忆")
        else:
            print(f"📚 最近 {len(all_memories)} 条记忆：")
            for i, m in enumerate(all_memories, 1):
                ts = m["metadata"].get("timestamp", "")
                session = m["metadata"].get("session_id", "")
                print(f"   {i}. [{ts}][{session}] {m['content'][:80]}")
        return True

    def _handle_search(self, user_input: str) -> bool:
        """语义搜索记忆"""
        query = user_input.strip()[len("/memory search "):]
        if not query:
            print("用法：/memory search <关键词>")
            return True
        results = self.memory_store.search(query, n_results=5)
        if not results:
            print(f"🔍 未找到与「{query}」相关的记忆")
        else:
            print(f"🔍 与「{query}」相关的记忆（{len(results)} 条）：")
            for i, m in enumerate(results, 1):
                dist = m.get("distance", 0)
                print(f"   {i}. [相似度: {1 - dist:.2f}] {m['content'][:100]}")
        return True

    def _handle_clear(self) -> bool:
        """清空所有记忆"""
        count = self.memory_store.clear_all()
        print(f"🗑️ 已清空 {count} 条记忆")
        return True

    def _handle_delete(self, user_input: str) -> bool:
        """删除指定会话的记忆"""
        session_id = user_input.strip()[len("/memory delete "):].strip()
        if not session_id:
            print("用法：/memory delete <会话ID>")
            return True
        count = self.memory_store.delete_session(session_id)
        if count > 0:
            print(f"🗑️ 已删除会话 [{session_id}] 的 {count} 条记忆")
        else:
            print(f"⚠️ 未找到会话 [{session_id}] 的记忆")
        return True

    def _handle_stats(self) -> bool:
        """统计信息"""
        count = self.memory_store._collection.count() if self.memory_store._collection else 0
        print(f"📊 记忆统计：共 {count} 条记忆，存储于 {self.memory_store.db_path}")
        return True

    def _print_help(self) -> None:
        """打印帮助信息"""
        print("📚 记忆管理命令：")
        print("   /memory list              - 列出最近记忆")
        print("   /memory search <关键词>   - 语义搜索记忆")
        print("   /memory delete <会话ID>   - 删除指定会话的记忆")
        print("   /memory clear             - 清空所有记忆")
        print("   /memory stats             - 查看记忆统计")
