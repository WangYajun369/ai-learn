"""
命令分发器 - 负责斜杠命令的补全和分发
"""

from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.completion import Completer
from prompt_toolkit.document import Document

from .commands.memory import MemoryCommandHandler
from .commands.history import HistoryCommandHandler
from .evolution_handler import EvolutionHandler


# 斜杠命令定义
SLASH_COMMANDS = [
    ("/new", "创建新会话"),
    ("/evolve", "🧬 主动总结归纳（深度分析用户画像）"),
    ("/profile", "🧬 查看当前用户画像"),
    ("/profile clear", "清空用户画像"),
    ("/hypothesis", "💡 查看待确认假设"),
    ("/hypothesis clear", "清空所有假设"),
    ("/memory list", "列出最近 10 条记忆"),
    ("/memory search", "语义搜索记忆（需跟关键词）"),
    ("/memory delete", "删除指定会话的记忆"),
    ("/memory clear", "清空所有记忆"),
    ("/memory stats", "查看记忆统计"),
    ("/history", "列出最近的会话记录"),
    ("/history show", "选择并查看会话详情"),
    ("/history resume", "恢复历史会话并继续对话"),
    ("/history delete", "删除指定会话"),
    ("/history clear", "清空所有历史会话"),
    ("/history stats", "查看会话统计"),
    ("/history search", "搜索会话内容（需跟关键词）"),
    ("/history export", "导出会话（支持 JSON/Markdown）"),
    ("/history tools", "搜索使用过指定工具的会话"),
    ("/model", "🔄 切换大模型（直接跟模型名如 qwen/glm/ollama）"),
    ("/help", "显示所有命令帮助"),
    ("/exit", "退出程序"),
]


class SlashCommandCompleter(Completer):
    """斜杠命令补全器"""

    def get_completions(self, document: Document, complete_event):
        text_before_cursor = document.text_before_cursor.lstrip()
        if not text_before_cursor.startswith("/"):
            return
        from prompt_toolkit.completion import Completion
        word = text_before_cursor.lower()
        for cmd, desc in SLASH_COMMANDS:
            if cmd.lower().startswith(word):
                yield Completion(
                    cmd,
                    start_position=-len(text_before_cursor),
                    display=cmd,
                    display_meta=desc,
                )


class CommandDispatcher:
    """
    命令分发器，集中处理所有斜杠命令。

    Returns:
        None: 命令已处理
        "continue": 正常继续对话流程（命令处理完毕但仍需继续）
        "input": user_input 是普通对话输入（非命令）
        str: 返回 session_id（恢复会话）
    """

    def __init__(
        self,
        memory_handler: MemoryCommandHandler | None,
        history_handler: HistoryCommandHandler | None,
        evo_handler: EvolutionHandler | None,
    ):
        self.memory_handler = memory_handler
        self.history_handler = history_handler
        self.evo_handler = evo_handler

    def dispatch(self, user_input: str, context: dict) -> str | None:
        """
        分发用户输入到对应的命令处理器。

        Args:
            user_input: 用户输入
            context: 上下文信息（backend_name, messages, turn_count, backend, etc.）

        Returns:
            None: 命令已处理，主循环应 continue
            "normal_input": 非命令输入，继续正常对话流程
            str: session_id（恢复会话）
        """
        cmd = user_input.strip().lower()

        # /new
        if cmd in ("/new", "/new "):
            return None  # 由 AgentCore 处理

        # /help
        if cmd in ("/help", "/help ", "/?"):
            return None

        # /evolve
        if cmd in ("/evolve", "/evolve "):
            return None

        # /profile
        if cmd == "/profile":
            return None
        if cmd == "/profile clear":
            return None

        # /hypothesis
        if cmd == "/hypothesis":
            return None
        if cmd == "/hypothesis clear":
            return None

        # /memory 子命令
        if self.memory_handler and self.memory_handler.handle(user_input):
            return None

        # /history 子命令
        if self.history_handler:
            history_result = self.history_handler.handle(user_input)
            if history_result is True:
                return None
            elif isinstance(history_result, str):
                return history_result  # session_id

        # exit
        if cmd in ["exit", "quit", "/exit"]:
            return None

        # /model - 由 AgentCore 处理模型切换
        if cmd.startswith("/model"):
            return None

        return "normal_input"
