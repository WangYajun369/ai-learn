"""
会话记录命令处理器（增强版）
"""

import json
from pathlib import Path

import pick as _pick

from conversation_store import ConversationStore


class HistoryCommandHandler:
    """处理 /history 开头的会话记录命令"""

    def __init__(self, conv_store: ConversationStore, enabled: bool):
        self.conv_store = conv_store
        self.enabled = enabled
        self._export_dir = Path(__file__).parent.parent.parent / "exports"

    def handle(self, user_input: str) -> str | bool:
        """
        处理会话记录命令
        
        Args:
            user_input: 用户输入的命令
            
        Returns:
            True: 命令已处理
            False: 命令未匹配
            str: 请求恢复该会话的 session_id
        """
        cmd = user_input.strip()

        if not cmd.startswith("/history"):
            return False

        if not self.enabled:
            print("⚠️ 会话记录功能不可用")
            return True

        parts = cmd.split(maxsplit=1)
        sub_cmd = parts[1] if len(parts) > 1 else ""

        if sub_cmd in ("", "list", "ls"):
            return self._handle_list()

        if sub_cmd == "show" or sub_cmd.startswith("show "):
            return self._handle_show(cmd)

        if sub_cmd == "stats":
            return self._handle_stats()

        if sub_cmd == "resume" or sub_cmd.startswith("resume "):
            return self._handle_resume(cmd)

        if sub_cmd == "delete" or sub_cmd.startswith("delete "):
            return self._handle_delete(cmd)

        if sub_cmd == "clear":
            return self._handle_clear()
        
        # 新增：搜索
        if sub_cmd == "search" or sub_cmd.startswith("search "):
            return self._handle_search(cmd)
        
        # 新增：导出
        if sub_cmd == "export" or sub_cmd.startswith("export "):
            return self._handle_export(cmd)
        
        # 新增：按工具搜索
        if sub_cmd == "tools" or sub_cmd.startswith("tools "):
            return self._handle_tools(cmd)

        self._print_help()
        return True

    def _handle_list(self) -> bool:
        """列出最近会话"""
        sessions = self.conv_store.list_sessions(limit=10)
        if not sessions:
            print("💬 暂无历史会话")
        else:
            print(f"💬 最近 {len(sessions)} 个会话：\n")
            for i, s in enumerate(sessions, 1):
                status = "🟢" if s["status"] == "active" else "⚫"
                turns = s.get("turn_count", 0)
                ended = s.get("ended_at", "")
                end_str = f" → {ended}" if ended else ""
                print(f"   {i}. {status} [{s['id']}] {s['model']}")
                print(f"      📅 {s['started_at']}{end_str}  💬 {turns} 轮")
        return True

    def _handle_show(self, cmd: str) -> bool:
        """查看会话详情"""
        sid = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""

        if not sid:
            sessions = self.conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            # 用 pick 选择器让用户上下键选择会话
            options = [
                _pick.Option(
                    f"{s['id']}  {s['model']}  💬{s.get('turn_count', 0)}轮  {s['started_at']}",
                    s["id"],
                )
                for s in sessions
            ]
            options.append(_pick.Option("取消", "__cancel__"))
            try:
                selected, _ = _pick.pick(
                    options,
                    "💬 选择要查看的会话（↑↓ 移动，Enter 确认）：",
                    indicator="❯",
                )
            except KeyboardInterrupt:
                return True
            if selected.value == "__cancel__":
                return True
            sid = selected.value

        detail = self.conv_store.get_session_detail(sid)
        if not detail:
            print(f"❌ 未找到会话 [{sid}]")
            return True

        print(f"\n{'═' * 60}")
        print(f"  会话 [{detail['id']}]  模型：{detail['model']}")
        print(f"  📅 {detail['started_at']} → {detail.get('ended_at', '进行中')}")
        print(f"  💬 {detail.get('turn_count', 0)} 轮对话")
        print(f"{'═' * 60}")

        if detail["messages"]:
            print("\n📝 对话记录：")
            for msg in detail["messages"]:
                role_label = "👤 用户" if msg["role"] == "user" else "🤖 Agent"
                content = msg["content"] or ""
                # 截断过长的内容
                if len(content) > 200:
                    content = content[:200] + "..."
                ts = msg.get("created_at", "")
                ts_str = f"  🕐 {ts}" if ts else ""
                print(f"\n  {role_label}：{content}{ts_str}")

        if detail["tool_calls"]:
            print(f"\n🔧 工具调用链（{len(detail['tool_calls'])} 次）：")
            for tc in detail["tool_calls"]:
                args = tc["arguments"]
                try:
                    args_str = json.dumps(json.loads(args), ensure_ascii=False)
                except (json.JSONDecodeError, TypeError):
                    args_str = str(args)
                if len(args_str) > 80:
                    args_str = args_str[:80] + "..."
                duration = f"  ⏱ {tc['duration_ms']}ms" if tc.get("duration_ms") else ""
                result_preview = (tc["result"] or "")[:100]
                print(f"  → {tc['tool_name']}({args_str}){duration}")
                if result_preview:
                    print(f"    返回：{result_preview}{'...' if len(tc['result'] or '') > 100 else ''}")

        print(f"\n{'═' * 60}\n")
        return True

    def _handle_stats(self) -> bool:
        """查看会话统计"""
        stats = self.conv_store.get_stats()
        print("📊 会话统计：")
        print(f"   总会话数：{stats['total_sessions']}")
        print(f"   未关闭会话：{stats['active_sessions']}")
        print(f"   总消息数：{stats['total_messages']}")
        print(f"   总工具调用：{stats['total_tool_calls']}")
        return True

    def _handle_resume(self, cmd: str) -> str | bool:
        """恢复历史会话"""
        target_sid = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""

        if not target_sid:
            sessions = self.conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            options = [
                _pick.Option(
                    f"{s['id']}  {s['model']}  💬{s.get('turn_count', 0)}轮  {s['started_at']}",
                    s["id"],
                )
                for s in sessions
            ]
            options.append(_pick.Option("取消", "__cancel__"))
            try:
                selected, _ = _pick.pick(
                    options,
                    "🔄 选择要恢复的会话（↑↓ 移动，Enter 确认）：",
                    indicator="❯",
                )
            except KeyboardInterrupt:
                return True
            if selected.value == "__cancel__":
                return True
            target_sid = selected.value

        # 验证会话存在
        detail = self.conv_store.get_session_detail(target_sid)
        if not detail:
            print(f"❌ 未找到会话 [{target_sid}]")
            return True
        # 返回 session_id，由主循环执行恢复
        return target_sid

    def _handle_delete(self, cmd: str) -> bool:
        """删除指定会话"""
        target_sid = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""

        if not target_sid:
            sessions = self.conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            options = [
                _pick.Option(
                    f"{s['id']}  {s['model']}  💬{s.get('turn_count', 0)}轮  {s['started_at']}",
                    s["id"],
                )
                for s in sessions
            ]
            options.append(_pick.Option("取消", "__cancel__"))
            try:
                selected, _ = _pick.pick(
                    options,
                    "🗑️ 选择要删除的会话（↑↓ 移动，Enter 确认）：",
                    indicator="❯",
                )
            except KeyboardInterrupt:
                return True
            if selected.value == "__cancel__":
                return True
            target_sid = selected.value

        msg_count = self.conv_store.delete_session(target_sid)
        print(f"🗑️ 已删除会话 [{target_sid}]（{msg_count} 条消息）")
        return True

    def _handle_clear(self) -> bool:
        """清空所有会话"""
        count = self.conv_store.clear_all()
        print(f"🗑️ 已清空全部 {count} 个会话")
        print("💡 提示：下一条消息将自动创建新会话")
        return True
    
    def _handle_search(self, cmd: str) -> bool:
        """搜索会话"""
        keyword = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""
        
        if not keyword:
            keyword = input("🔍 输入搜索关键词：").strip()
        
        if not keyword:
            print("⚠️ 请输入搜索关键词")
            return True
        
        results = self.conv_store.search_sessions(keyword)
        
        if not results:
            print(f"🔍 未找到包含「{keyword}」的会话")
            return True
        
        print(f"🔍 找到 {len(results)} 个匹配的会话：\n")
        for i, s in enumerate(results[:10], 1):
            status = "🟢" if s["status"] == "active" else "⚫"
            matched = s.get("matched_content", "")[:80]
            if len(matched) >= 80:
                matched += "..."
            print(f"   {i}. {status} [{s['id']}]")
            print(f"      📅 {s['started_at']}  💬 {s.get('turn_count', 0)} 轮")
            print(f"      💬 {matched}")
            print()
        return True
    
    def _handle_export(self, cmd: str) -> bool:
        """导出会话"""
        parts = cmd.split(maxsplit=2)
        sid = parts[2].strip() if len(parts) > 2 else ""
        fmt = "markdown"
        
        # 检查格式参数
        if sid and "=" in sid:
            sid_part, fmt_part = sid.rsplit("=", 1)
            sid = sid_part.strip()
            fmt = fmt_part.strip().lower()
            if fmt not in ("json", "markdown", "md"):
                fmt = "markdown"
        
        if not sid:
            sessions = self.conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            options = [
                _pick.Option(
                    f"{s['id']}  {s['model']}  💬{s.get('turn_count', 0)}轮",
                    s["id"],
                )
                for s in sessions
            ]
            options.append(_pick.Option("取消", "__cancel__"))
            try:
                selected, _ = _pick.pick(
                    options,
                    "📤 选择要导出的会话（↑↓ 移动，Enter 确认）：",
                    indicator="❯",
                )
            except KeyboardInterrupt:
                return True
            if selected.value == "__cancel__":
                return True
            sid = selected.value
        
        # 导出会话
        ext = "json" if fmt == "json" else "md"
        output_path = self._export_dir / f"session_{sid}.{ext}"
        
        success = self.conv_store.export_session_to_file(sid, output_path, fmt)
        
        if success:
            print(f"✅ 会话已导出到：{output_path}")
        else:
            print(f"❌ 导出失败，会话 [{sid}] 不存在")
        return True
    
    def _handle_tools(self, cmd: str) -> bool:
        """搜索使用过指定工具的会话"""
        parts = cmd.split(maxsplit=2)
        tool_name = parts[2].strip() if len(parts) > 2 else ""
        
        if not tool_name:
            tool_name = input("🔧 输入工具名称：").strip()
        
        if not tool_name:
            print("⚠️ 请输入工具名称")
            return True
        
        results = self.conv_store.search_by_tool(tool_name)
        
        if not results:
            print(f"🔧 未找到使用过「{tool_name}」的会话")
            return True
        
        print(f"🔧 找到 {len(results)} 个使用过「{tool_name}」的会话：\n")
        for i, s in enumerate(results[:10], 1):
            print(f"   {i}. [{s['id']}]")
            print(f"      📅 {s['started_at']}  💬 {s.get('turn_count', 0)} 轮")
            print(f"      🔧 使用次数：{s.get('tool_usage_count', 0)}")
            print()
        return True

    def _print_help(self) -> None:
        """打印帮助信息"""
        print("💬 会话记录命令：")
        print("   /history               - 列出最近会话")
        print("   /history show         - 选择并查看会话详情（上下键选择）")
        print("   /history show <ID>     - 查看指定会话详情（含调用链）")
        print("   /history resume        - 恢复历史会话并继续对话")
        print("   /history delete        - 删除指定会话")
        print("   /history clear         - 清空所有历史会话")
        print("   /history stats         - 查看会话统计")
        print("   /history search [关键词] - 搜索会话内容")
        print("   /history export [ID]   - 导出会话（支持 format=json/markdown）")
        print("   /history tools [工具名] - 搜索使用过指定工具的会话")
