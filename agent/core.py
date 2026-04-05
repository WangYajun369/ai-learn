"""
Agent 核心逻辑 - 对话循环、工具调用、流式输出
"""

import asyncio
import os
import re
import sys
import threading
import time as _time
from pathlib import Path
from contextlib import AsyncExitStack

from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.completion import Completer
from prompt_toolkit.document import Document
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from memory_store import MemoryStore, generate_memory_id
from conversation_store import ConversationStore

from .skill_loader import SkillLoader
from .backends.base import BaseBackend
from .commands.memory import MemoryCommandHandler
from .commands.history import HistoryCommandHandler


# 斜杠命令定义
SLASH_COMMANDS = [
    ("/new", "创建新会话"),
    ("/memory list", "列出最近 10 条记忆"),
    ("/memory search", "语义搜索记忆（需跟关键词）"),
    ("/memory delete", "删除指定会话的记忆"),
    ("/memory clear", "清空所有记忆"),
    ("/memory stats", "查看记忆统计"),
    ("/history", "列出最近的会话记录"),
    ("/history show", "选择并查看会话详情（上下键选择）"),
    ("/history resume", "恢复历史会话并继续对话（上下键选择）"),
    ("/history delete", "删除指定会话（上下键选择）"),
    ("/history clear", "清空所有历史会话"),
    ("/history stats", "查看会话统计"),
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


class AgentCore:
    """Agent 核心类，管理对话循环、工具调用和状态"""

    def __init__(
        self,
        backend: BaseBackend,
        skill_loader: SkillLoader,
        memory_store: MemoryStore,
        conv_store: ConversationStore,
    ):
        self.backend = backend
        self.skill_loader = skill_loader
        self.memory_store = memory_store
        self.conv_store = conv_store

        self.memory_enabled = False
        self.conv_enabled = False
        self.session_id = ""
        self.conv_session_id = ""
        self.turn_count = 0
        self.messages: list[dict] = []
        self.active_skill: dict | None = None
        self.base_system_prompt = ""

        # 命令处理器
        self.memory_handler: MemoryCommandHandler | None = None
        self.history_handler: HistoryCommandHandler | None = None

    async def initialize(self) -> bool:
        """初始化 Agent，连接数据库和加载配置"""
        # 连接记忆数据库
        self.memory_enabled = self.memory_store.connect()
        self.session_id = generate_memory_id()

        # 连接会话记录数据库
        self.conv_enabled = self.conv_store.connect()

        # 初始化命令处理器
        self.memory_handler = MemoryCommandHandler(self.memory_store, self.memory_enabled)
        self.history_handler = HistoryCommandHandler(self.conv_store, self.conv_enabled)

        return True

    def restore_or_create_session(self, backend_name: str) -> list[dict]:
        """恢复最近一次会话或创建新会话"""
        restored_messages = []

        if self.conv_enabled:
            recent = self.conv_store.list_sessions(limit=1)
            if recent:
                last_sid = recent[0]["id"]
                last_status = recent[0].get("status", "closed")
                restored_messages = self.conv_store.restore_session_messages(last_sid)

                # 无论是否有消息，都恢复会话（即使上次异常退出）
                self.conv_session_id = last_sid
                self.conv_store.switch_to_session(last_sid)

                if restored_messages:
                    print(f"🔄 检测到上次会话 [{last_sid}]（{last_status}，{len(restored_messages)} 条消息）")
                else:
                    print(f"🔄 检测到上次会话 [{last_sid}]（{last_status}，无历史消息）")
            else:
                # 没有历史会话，创建新会话
                self.conv_session_id = self.conv_store.create_session(backend_name)
                print(f"🆕 已创建新会话 [{self.conv_session_id}]")

        return restored_messages

    def setup_system_prompt(self, tools_resp) -> None:
        """设置系统提示词"""
        tool_names = [f"- {tool.name}：{tool.description.split(chr(10))[0]}" for tool in tools_resp.tools]
        self.base_system_prompt = (
            "你是一个销售数据查询助手。你可以通过工具来帮助用户查询销售信息。\n\n"
            f"你可以使用以下工具：\n{chr(10).join(tool_names)}\n\n"
            '当用户问"有哪些功能"、"你能做什么"时，请介绍以上工具的能力。\n'
            '当用户问"有哪些产品"时，请调用 list_products 工具查询。\n'
            "回复使用中文。"
        )
        self.messages = [{"role": "system", "content": self.base_system_prompt}]

    def print_skill_packages(self) -> None:
        """打印已加载的技能包信息"""
        import textwrap

        skills = self.skill_loader.skills
        if not skills:
            print("⚠️ 未找到技能包，将以基础模式运行")
            return

        print(f"\n📦 已加载 {len(skills)} 个技能包：")
        for s in skills:
            print(f"\n   ┌─ {s['name']}")
            desc = " ".join(s["description"].strip().splitlines())
            for line in textwrap.wrap(desc, width=56, initial_indent="   │  ", subsequent_indent="   │  "):
                print(line)
            if s.get("trigger_keywords"):
                kw_str = ", ".join(s["trigger_keywords"])
                print(f"   │  触发词：{kw_str}")
            # 列出附带的脚本和参考文件
            scripts_dir = self.skill_loader.skills_dir / "scripts"
            refs_dir = self.skill_loader.skills_dir / "references"
            if scripts_dir.exists():
                py_files = sorted(p.name for p in scripts_dir.glob("*.py") if p.name != "__init__.py")
                if py_files:
                    print(f"   │  脚本：{', '.join(py_files)}")
            if refs_dir.exists():
                ref_files = sorted(p.name for p in refs_dir.glob("*") if p.name != "__init__.py" and not p.name.endswith(".pyc"))
                if ref_files:
                    print(f"   │  参考：{', '.join(ref_files)}")
            print(f"   └{'─' * (len(s['name']) + 5)}")

    def print_restored_history(self, restored_messages: list[dict]) -> None:
        """打印恢复的历史对话"""
        if not restored_messages:
            if self.conv_session_id:
                print("   ℹ️ 当前会话暂无历史消息")
                print("   输入 /new 可创建新会话\n")
            return

        self.turn_count = sum(1 for m in restored_messages if m["role"] == "user")
        print(f"   ✅ 已加载 {self.turn_count} 轮历史对话")

        # 打印历史对话内容
        print("\n" + "═" * 60, flush=True)
        print("📜 历史对话记录", flush=True)
        print("═" * 60, flush=True)
        for i, msg in enumerate(restored_messages):
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                print(f"\n👤 用户：{content}", flush=True)
            elif role == "assistant":
                print(f"\n🤖 Agent：{content}", flush=True)
            # 每轮对话（用户+助手）后加分隔线
            if role == "assistant":
                print("\n" + "-" * 47, flush=True)
        print("═" * 60, flush=True)
        print("   输入 /new 可创建新会话\n", flush=True)

    def inject_memory(self, user_input: str) -> None:
        """根据用户输入检索相关记忆，注入到 system prompt"""
        if not self.memory_enabled or not self.memory_store._collection:
            return
        count = self.memory_store._collection.count()
        if count == 0:
            return
        related = self.memory_store.search(user_input, n_results=3)
        if related:
            memory_lines = ["以下是相关的历史记忆（供参考）："]
            for i, m in enumerate(related, 1):
                ts = m["metadata"].get("timestamp", "")
                memory_lines.append(f"  {i}. [{ts}] {m['content']}")
            memory_text = "\n".join(memory_lines)
            # 在 system prompt 末尾追加记忆
            current_system = self.messages[0]["content"]
            self.messages[0] = {
                "role": "system",
                "content": current_system + "\n\n" + memory_text,
            }
            print("   🧠 已检索到相关历史记忆")

    def save_memory(self, silent: bool = False) -> None:
        """调用 LLM 生成对话摘要并存入向量数据库"""
        if not self.memory_enabled or not self.memory_store._collection:
            return
        if self.turn_count < 1:
            # 对话轮次太少，不保存
            return

        try:
            summary_prompt = MemoryStore.build_summary_prompt(self.messages)
            # 用一个轻量级调用让 LLM 生成摘要
            summary_messages = [
                {"role": "system", "content": "你是信息提取助手。只输出摘要文本，不要加任何前缀后缀。"},
                {"role": "user", "content": summary_prompt},
            ]
            result = self.backend.chat(summary_messages, [])
            summary = result.get("content", "").strip()

            if not summary or summary in ("无", "无。", "没有需要记住的信息。"):
                return

            # 提取话题标签
            topics = self._extract_topics(self.messages)
            self.memory_store.save(summary, self.session_id, topics)
        except Exception as e:
            if not silent:
                print(f"   ⚠️ 记忆保存失败：{e}")

    def _extract_topics(self, msgs: list[dict]) -> list[str]:
        """从对话中提取简单的话题标签"""
        topics = set()
        for msg in msgs:
            content = msg.get("content", "")
            for keyword in [
                "华东", "华北", "华南", "AI 助手", "数据分析",
                "增长", "异常", "销售额", "客户管理", "智能客服",
            ]:
                if keyword in content:
                    topics.add(keyword)
        return sorted(topics)

    def handle_new_session(self, backend_name: str) -> None:
        """处理 /new 命令创建新会话"""
        if self.conv_enabled:
            self.conv_store.close_session()
            new_sid = self.conv_store.create_session(backend_name)
        else:
            new_sid = generate_memory_id()
        self.messages = [{"role": "system", "content": self.base_system_prompt}]
        self.active_skill = None
        self.turn_count = 0
        self.session_id = generate_memory_id()
        print(f"\n🆕 已创建新会话 [{new_sid}]\n")

    def handle_help(self) -> None:
        """处理 /help 命令"""
        print("\n📖 命令帮助：")
        print("═" * 60)
        for cmd, desc in SLASH_COMMANDS:
            print(f"  {cmd:<20} - {desc}")
        print("═" * 60)

    def try_match_skill(self, user_input: str) -> bool:
        """尝试匹配并加载技能"""
        matched = self.skill_loader.match_skill(user_input) if self.skill_loader.skills else None
        if matched and self.active_skill is None:
            print(f"\n📦 匹配到技能包：{matched['name']}")
            full_skill = self.skill_loader.load_full_skill(matched["name"])
            if full_skill:
                # 阶段 2：加载完整 SKILL.md（<5000 tokens）
                self.active_skill = matched
                self.messages[0] = {
                    "role": "system",
                    "content": full_skill,
                }
                print("   ✅ 技能指令已加载（完整 SKILL.md）")

                # 同时加载报告模板作为参考
                template = self.skill_loader.load_reference("report_template.md")
                if template:
                    self.messages.append({
                        "role": "system",
                        "content": f"以下是你的报告输出模板，请严格按照此格式生成报告：\n\n{template}",
                    })
                    print("   ✅ 报告模板已加载（references/report_template.md）")
            return True
        return False

    async def process_streaming_response(self, tools: list) -> tuple[str, list[dict], bool]:
        """
        处理流式响应
        
        Returns:
            (full_content, tool_calls, has_tool_call)
        """
        cancelled = threading.Event()
        _stream_error: list = [None]
        _stream_chunks: list = []  # 线程安全的 chunk 队列
        _stream_lock = threading.Lock()
        _stream_done = threading.Event()

        def _run_stream():
            try:
                _stream_error[0] = None
                for chunk_tuple in self.backend.chat_stream(self.messages, tools):
                    if cancelled.is_set():
                        break
                    with _stream_lock:
                        _stream_chunks.append(chunk_tuple)
                    _stream_done.set()  # 有数据了，通知主线程开始打印
                _stream_done.set()  # 流结束
            except Exception as e:
                _stream_error[0] = e
                _stream_done.set()

        chat_thread = threading.Thread(target=_run_stream, daemon=True)
        print("   ⏳ 思考中…", end="", flush=True)
        chat_thread.start()

        # 主线程：等待首个 chunk 到达 + 实时打印
        full_content = ""
        tool_calls = []
        has_tool_call = False
        _printed_index = 0  # 已打印到的 chunk 位置
        first_chunk = True

        # 去掉每行开头的空白，防止模型输出中累积的缩进空格
        _strip_line_re = re.compile(r"\n[ \t]+")

        try:
            while True:
                # 等待有新数据或流结束
                if not _stream_done.wait(timeout=0.05):
                    # 超时，检查线程是否已结束且无新数据
                    if not chat_thread.is_alive():
                        # 线程已结束，再检查是否还有未打印的数据
                        with _stream_lock:
                            if _printed_index >= len(_stream_chunks):
                                # 确实没有更多数据了，退出
                                break
                    continue

                # 打印所有新到达的 chunks
                while True:
                    with _stream_lock:
                        if _printed_index >= len(_stream_chunks):
                            break
                        chunk_tuple = _stream_chunks[_printed_index]
                        _printed_index += 1

                    content_delta, is_tc, tc_info = chunk_tuple
                    if first_chunk:
                        # 清除"思考中"提示，打印 Agent 标记
                        print("\r" + " " * 30 + "\r", end="", flush=True)
                        print("🤖 Agent：", end="", flush=True)
                        first_chunk = False
                        # 去掉开头换行，避免 Agent 标记后空一行
                        content_delta = content_delta.lstrip("\n")

                    # 记录原始内容
                    full_content += content_delta

                    # 显示时去掉每行开头的累积空格
                    display_delta = _strip_line_re.sub("\n", content_delta)

                    # 直接输出（确保 flush）
                    if is_tc:
                        has_tool_call = True
                        tool_calls.append(tc_info)
                        if display_delta:
                            sys.stdout.write(display_delta)
                            sys.stdout.flush()
                    else:
                        sys.stdout.write(display_delta)
                        sys.stdout.flush()

                # 检查是否有错误
                if _stream_error[0] is not None:
                    break

                # 如果线程已结束且 _stream_done 被设置，说明流已完成
                if not chat_thread.is_alive() and _stream_done.is_set():
                    # 再次确认没有未打印的数据
                    with _stream_lock:
                        if _printed_index >= len(_stream_chunks):
                            break

        except KeyboardInterrupt:
            # 用户按 Ctrl+C 取消
            cancelled.set()
            print("\r   ⛔ 已取消回答")
            raise

        if _stream_error[0] is not None:
            raise _stream_error[0]

        if first_chunk:
            # 没有任何输出（模型可能返回空）
            print("\r" + " " * 30 + "\r", end="", flush=True)
        else:
            print()  # 换行

        return full_content, tool_calls, has_tool_call

    async def run_conversation_loop(self, session, tools: list, backend_name: str) -> None:
        """主对话循环"""
        pt_session = PromptSession(completer=SlashCommandCompleter())

        while True:
            try:
                user_input = await pt_session.prompt_async("\n👤 你：")
            except (KeyboardInterrupt, EOFError):
                break

            user_input = user_input.strip()

            if not user_input:
                continue

            # ── 新会话命令 ──
            if user_input.strip().lower() in ("/new", "/new "):
                self.handle_new_session(backend_name)
                continue

            # ── 帮助命令 ──
            if user_input.strip().lower() in ("/help", "/help ", "/?"):
                self.handle_help()
                continue

            # ── 记忆管理命令 ──
            if self.memory_handler and self.memory_handler.handle(user_input):
                continue

            # ── 会话记录命令 ──
            history_result = self.history_handler.handle(user_input) if self.history_handler else False
            if history_result is True or history_result is False:
                if history_result:
                    continue
            elif isinstance(history_result, str):
                # 返回了 session_id，执行恢复
                restored = self.conv_store.restore_session_messages(history_result)
                if restored:
                    self.messages.extend(restored)
                    # 统计恢复的用户消息数作为 turn_count
                    self.turn_count = sum(1 for m in restored if m["role"] == "user")
                    self.conv_store.switch_to_session(history_result)
                    print(f"\n🔄 已恢复会话 [{history_result}]，共 {self.turn_count} 轮对话，可继续聊天")
                else:
                    print(f"⚠️ 会话 [{history_result}] 无可恢复的消息")
                continue

            if user_input.lower() in ["exit", "quit", "/exit"]:
                break

            self.turn_count += 1

            # ── 检索相关记忆并注入 ──
            self.inject_memory(user_input)

            self.messages.append({"role": "user", "content": user_input})

            # ── 记录用户消息 ──
            if self.conv_enabled:
                # 确保会话存在（防止清空历史后未创建新会话）
                if not self.conv_store.session_id:
                    self.conv_session_id = self.conv_store.create_session(backend_name)
                    print(f"🆕 已创建新会话 [{self.conv_session_id}]")
                self.conv_store.save_message("user", user_input)

            # ── 阶段 1→2：技能匹配 ──
            self.try_match_skill(user_input)

            # 5. 内层循环：支持多步工具调用（流式输出）
            while True:
                try:
                    full_content, tool_calls, has_tool_call = await self.process_streaming_response(tools)
                except KeyboardInterrupt:
                    break

                # ── 构造 raw_message 存入消息历史 ──
                if has_tool_call:
                    raw_message = self.backend.make_tool_call_raw_message(tool_calls, full_content)
                else:
                    raw_message = {"role": "assistant", "content": full_content}
                self.messages.append(raw_message)

                if tool_calls:
                    for tc in tool_calls:
                        print(f"🔧 调用工具：{tc['name']}({tc['arguments']})...")
                        tool_t0 = _time.perf_counter()

                        tool_resp = await session.call_tool(tc["name"], tc["arguments"])

                        tool_duration = int((_time.perf_counter() - tool_t0) * 1000)

                        tool_text = ""
                        for item in tool_resp.content:
                            tool_text += item.text if hasattr(item, "text") else str(item)

                        # ── 记录工具调用 ──
                        if self.conv_enabled:
                            self.conv_store.save_tool_call(
                                tool_name=tc["name"],
                                arguments=tc["arguments"],
                                result=tool_text,
                                duration_ms=tool_duration,
                            )

                        self.messages.append(
                            self.backend.make_tool_result_message(tc, tool_text)
                        )
                else:
                    # ── 记录助手回复 ──
                    if self.conv_enabled:
                        self.conv_store.save_message("assistant", full_content)
                    break

    async def run(self, backend_name: str) -> None:
        """运行 Agent 主流程"""
        _t0 = _time.perf_counter()
        label = self.backend.__class__.__name__.replace("Backend", "")
        print(f"\n🚀 正在启动 MCP Agent（{label}）...")

        _t1 = _time.perf_counter()
        print(f"   ⏱ 模型后端初始化：{_t1 - _t0:.2f}s")

        # ── 阶段 1：加载 Skill 摘要（~100 tokens）──
        self.skill_loader.load_summaries()

        # ── 初始化 Agent ──
        await self.initialize()
        _t2 = _time.perf_counter()
        print(f"   ⏱ 记忆/会话数据库连接：{_t2 - _t1:.2f}s")

        # ── 自动恢复最近一次会话 ──
        restored_messages = self.restore_or_create_session(backend_name)

        # 1. 配置 MCP Server 启动参数
        # 优先使用 .venv 中的 python，省去 uv run 的依赖解析开销（约 0.5-1s）
        _venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
        if _venv_python.exists():
            server_cmd = str(_venv_python)
            server_args = ["server.py"]
        else:
            server_cmd = "uv"
            server_args = ["run", "server.py"]

        server_params = StdioServerParameters(
            command=server_cmd,
            args=server_args,
            env={"PATH": os.environ["PATH"]},
        )

        try:
            async with AsyncExitStack() as stack:
                # 2. 连接 MCP Server
                _t3 = _time.perf_counter()
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(server_params)
                )
                session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()

                # 3. 获取工具列表
                tools_resp = await session.list_tools()
                _t4 = _time.perf_counter()
                print(f"   ⏱ MCP Server 连接 + 工具加载：{_t4 - _t3:.2f}s")
                print(f"✅ 已加载 {len(tools_resp.tools)} 个工具：")
                for tool in tools_resp.tools:
                    desc_first_line = tool.description.split(chr(10))[0]
                    print(f"   - {tool.name}：{desc_first_line}")
                tools = self.backend.build_tools(tools_resp.tools)

                # 3.5 打印技能包信息
                self.print_skill_packages()
                print(f"   ⏱ 总启动耗时：{_t4 - _t0:.2f}s")

                # 3.6 构建基础系统提示词
                self.setup_system_prompt(tools_resp)

                # 3.8 恢复上次会话上下文
                if restored_messages:
                    self.messages.extend(restored_messages)
                self.print_restored_history(restored_messages)

                # 4. 对话主循环
                await self.run_conversation_loop(session, tools, backend_name)

            # ── 退出前保存对话记忆（静默模式，网络错误不打断退出）──
            self.save_memory(silent=True)

            # ── 退出前关闭会话记录 ──
            if self.conv_enabled and self.conv_store.session_id:
                self.conv_store.close_session()
                print(f"💾 会话 [{self.conv_store.session_id}] 已保存")

        except KeyboardInterrupt:
            pass
        finally:
            print("\n👋 再见！")
            # 使用 os._exit 跳过 ONNX Runtime 的 atexit 清理
            # （ChromaDB 默认嵌入模型退出时会缓慢解压/清理 onnx.tar.gz）
            import os as _os
            _os._exit(0)
