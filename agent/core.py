"""
Agent 核心逻辑 - 对话循环、工具调用、流式输出

重构后的 AgentCore 作为协调器，将职责拆分到专职组件：
- MemoryInjector: 向量记忆 + 用户画像注入/保存
- EvolutionHandler: 进化引擎命令处理
- CommandDispatcher: 斜杠命令定义、补全和分发

增强功能：
- MCP 连接重试机制（指数退避）
- 工具调用缓存（TTL 5分钟）
- 会话导出（JSON/Markdown）
- 会话搜索
"""

import asyncio
import os
import queue
import re
import sys
import threading
import time as _time
from pathlib import Path
from contextlib import AsyncExitStack

from prompt_toolkit.shortcuts import PromptSession

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from memory_store import MemoryStore, generate_memory_id
from conversation_store import ConversationStore

from .skill_loader import SkillLoader
from .backends.base import BaseBackend
from .backends import BACKENDS, BACKEND_LABELS, get_backend, get_backend_label
from .commands.memory import MemoryCommandHandler
from .commands.history import HistoryCommandHandler
from .evolution.engine import EvolutionEngine
from .memory_injector import MemoryInjector
from .evolution_handler import EvolutionHandler
from .command_dispatcher import SlashCommandCompleter, SLASH_COMMANDS
from .retry import MCPSessionManager, RetryError
from .cache import get_tool_cache


class AgentCore:
    """Agent 核心协调器，管理对话主循环和各子组件"""

    def __init__(
        self,
        backend: BaseBackend,
        skill_loader: SkillLoader,
        memory_store: MemoryStore,
        conv_store: ConversationStore,
    ):
        self.backend = backend
        self.backend_name = ""  # 当前模型名称，切换时更新
        self.skill_loader = skill_loader
        self.memory_store = memory_store
        self.conv_store = conv_store

        # 对话状态
        self.conv_enabled = False
        self.conv_session_id = ""
        self.session_id = ""
        self.turn_count = 0
        self.messages: list[dict] = []
        self.active_skill: dict | None = None
        self.base_system_prompt = ""

        # 子组件（initialize 时创建）
        self.memory_injector: MemoryInjector | None = None
        self.evo_handler: EvolutionHandler | None = None
        self._memory_cmd_handler: MemoryCommandHandler | None = None
        self._history_cmd_handler: HistoryCommandHandler | None = None
        self.evolution: EvolutionEngine | None = None

    async def initialize(self) -> bool:
        """初始化 Agent，连接数据库和创建子组件"""
        # 创建记忆注入器
        self.memory_injector = MemoryInjector(self.memory_store)
        self.memory_injector.memory_enabled = self.memory_store.connect()
        self.session_id = generate_memory_id()

        # 连接会话记录数据库
        self.conv_enabled = self.conv_store.connect()

        # 初始化进化引擎
        self.evolution = EvolutionEngine()
        self.evolution.connect(silent=True)
        self.memory_injector.evolution = self.evolution

        # 创建进化命令处理器
        self.evo_handler = EvolutionHandler(self.evolution)

        # 初始化命令处理器
        self._memory_cmd_handler = MemoryCommandHandler(
            self.memory_store, self.memory_injector.memory_enabled
        )
        self._history_cmd_handler = HistoryCommandHandler(self.conv_store, self.conv_enabled)

        return True

    # ── 会话恢复 ──

    def restore_or_create_session(self, backend_name: str) -> list[dict]:
        """恢复最近一次会话或创建新会话"""
        restored_messages = []

        if self.conv_enabled:
            recent = self.conv_store.list_sessions(limit=1)
            if recent:
                last_sid = recent[0]["id"]
                last_status = recent[0].get("status", "closed")
                restored_messages = self.conv_store.restore_session_messages(last_sid)

                self.conv_session_id = last_sid
                self.conv_store.switch_to_session(last_sid)

                if restored_messages:
                    print(f"🔄 检测到上次会话 [{last_sid}]（{last_status}，{len(restored_messages)} 条消息）")
                else:
                    print(f"🔄 检测到上次会话 [{last_sid}]（{last_status}，无历史消息）")
            else:
                self.conv_session_id = self.conv_store.create_session(backend_name)
                print(f"🆕 已创建新会话 [{self.conv_session_id}]")

        return restored_messages

    # ── 系统提示词 ──

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

    # ── 显示信息 ──

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

        print("\n" + "═" * 60, flush=True)
        print("📜 历史对话记录", flush=True)
        print("═" * 60, flush=True)
        for msg in restored_messages:
            role = msg["role"]
            content = msg["content"]
            ts = msg.get("created_at", "")
            ts_str = f"  🕐 {ts}" if ts else ""
            if role == "user":
                print(f"\n👤 用户：{content}{ts_str}", flush=True)
            elif role == "assistant":
                print(f"\n🤖 Agent：{content}{ts_str}", flush=True)
            if role == "assistant":
                print("\n" + "-" * 47, flush=True)
        print("═" * 60, flush=True)
        print("   输入 /new 可创建新会话\n", flush=True)

    # ── 技能匹配 ──

    def try_match_skill(self, user_input: str) -> bool:
        """尝试匹配并加载技能"""
        matched = self.skill_loader.match_skill(user_input) if self.skill_loader.skills else None
        if matched and self.active_skill is None:
            print(f"\n📦 匹配到技能包：{matched['name']}")
            full_skill = self.skill_loader.load_full_skill(matched["name"])
            if full_skill:
                self.active_skill = matched
                self.messages[0] = {"role": "system", "content": full_skill}
                print("   ✅ 技能指令已加载（完整 SKILL.md）")

                template = self.skill_loader.load_reference("report_template.md")
                if template:
                    self.messages.append({
                        "role": "system",
                        "content": f"以下是你的报告输出模板，请严格按照此格式生成报告：\n\n{template}",
                    })
                    print("   ✅ 报告模板已加载（references/report_template.md）")
            return True
        return False

    # ── 会话管理命令 ──

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

    def handle_model_switch(self, user_input: str, backend_name: str) -> str | None:
        """
        处理 /model 命令切换大模型。

        Returns:
            None: 命令已处理，继续当前会话
            str: 新的 backend_name（需要切换模型）
        """
        # 解析命令参数
        parts = user_input.strip().split()
        target_model = parts[1] if len(parts) > 1 else None

        # 无参数：显示当前模型和可用模型
        if target_model is None:
            current_label = BACKEND_LABELS.get(backend_name, backend_name)
            print(f"\n🔄 当前模型：{current_label}")
            print("\n📋 可用模型：")
            for name, label in BACKEND_LABELS.items():
                marker = " ◀ (当前)" if name == backend_name else ""
                print(f"   - {name:<10} {label}{marker}")
            print("\n💡 输入 /model <名称> 切换，如：/model glm")
            return None

        # 有参数：检查目标模型
        if target_model not in BACKENDS:
            print(f"\n❌ 未知模型：{target_model}")
            print("可用模型：" + ", ".join(BACKENDS.keys()))
            return None

        # 相同模型
        if target_model == backend_name:
            print(f"\nℹ️ 已经是 {BACKEND_LABELS.get(target_model, target_model)}")
            return None

        # 切换模型
        print(f"\n🔄 正在切换到 {BACKEND_LABELS.get(target_model, target_model)}...")
        return target_model

    # ── 流式响应处理 ──

    async def process_streaming_response(self, tools: list) -> tuple[str, list[dict], bool]:
        """
        处理流式响应，使用 queue.Queue 实现线程安全的 chunk 传递

        Returns:
            (full_content, tool_calls, has_tool_call)
        """
        _SENTINEL = object()
        cancelled = threading.Event()
        chunk_queue: queue.Queue = queue.Queue()
        error_holder: list = [None]

        def _run_stream():
            try:
                for chunk_tuple in self.backend.chat_stream(self.messages, tools):
                    if cancelled.is_set():
                        break
                    chunk_queue.put(chunk_tuple)
                chunk_queue.put(_SENTINEL)
            except Exception as e:
                error_holder[0] = e
                chunk_queue.put(_SENTINEL)

        chat_thread = threading.Thread(target=_run_stream, daemon=True)
        print("   ⏳ 思考中…", end="", flush=True)
        chat_thread.start()

        full_content = ""
        tool_calls = []
        has_tool_call = False
        first_chunk = True
        _strip_line_re = re.compile(r"\n[ \t]+")

        try:
            while True:
                try:
                    item = chunk_queue.get(timeout=0.05)
                except queue.Empty:
                    continue

                if item is _SENTINEL:
                    break

                content_delta, is_tc, tc_info = item
                if first_chunk:
                    print("\r" + " " * 30 + "\r", end="", flush=True)
                    print("🤖 Agent：", end="", flush=True)
                    first_chunk = False
                    content_delta = content_delta.lstrip("\n")

                full_content += content_delta
                display_delta = _strip_line_re.sub("\n", content_delta)

                if is_tc:
                    has_tool_call = True
                    tool_calls.append(tc_info)
                    if display_delta:
                        sys.stdout.write(display_delta)
                        sys.stdout.flush()
                else:
                    sys.stdout.write(display_delta)
                    sys.stdout.flush()

        except KeyboardInterrupt:
            cancelled.set()
            print("\r   ⛔ 已取消回答")
            raise

        if error_holder[0] is not None:
            raise error_holder[0]

        if first_chunk:
            print("\r" + " " * 30 + "\r", end="", flush=True)
        else:
            print()

        return full_content, tool_calls, has_tool_call

    # ── 对话主循环 ──

    async def run_conversation_loop(self, session, tools: list, backend_name: str) -> str | None:
        """主对话循环"""
        pt_session = PromptSession(completer=SlashCommandCompleter())
        mcp_manager = self._mcp_manager  # 从 run() 传入的会话管理器

        while True:
            try:
                user_input = await pt_session.prompt_async("\n👤 你：")
            except (KeyboardInterrupt, EOFError):
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # ── 会话管理命令 ──
            if user_input.strip().lower() in ("/new", "/new "):
                self.handle_new_session(backend_name)
                continue

            if user_input.strip().lower() in ("/help", "/help ", "/?"):
                self.handle_help()
                continue

            # ── 模型切换命令 ──
            if user_input.strip().lower().startswith("/model"):
                new_backend = self.handle_model_switch(user_input, backend_name)
                if new_backend:
                    # 需要切换模型，返回新模型名称让 run() 重新初始化
                    return new_backend
                continue

            # ── 进化命令 ──
            if user_input.strip().lower() in ("/evolve", "/evolve "):
                self.evo_handler.handle_evolve(self.messages, self.turn_count, self.backend)
                continue

            if user_input.strip().lower() == "/profile":
                self.evo_handler.handle_show_profile()
                continue
            if user_input.strip().lower() == "/profile clear":
                self.evo_handler.handle_clear_profile()
                continue

            if user_input.strip().lower() == "/hypothesis":
                self.evo_handler.handle_show_hypotheses()
                continue
            if user_input.strip().lower() == "/hypothesis clear":
                self.evo_handler.handle_clear_hypotheses()
                continue

            # ── 记忆/会话命令 ──
            cmd_result = self._dispatch_subsystem_command(user_input)
            if cmd_result is not None:
                if isinstance(cmd_result, str):
                    self._restore_session(cmd_result)
                continue

            # ── 退出 ──
            if user_input.lower() in ["exit", "quit", "/exit"]:
                break

            # ── 正常对话流程 ──
            self.turn_count += 1

            # 检查用户对假设的确认/拒绝
            if self.evo_handler.enabled:
                confirm_result = self.evo_handler.check_confirmation(user_input)
                if confirm_result:
                    print(f"\n🧬 {confirm_result}\n")

            # 检索相关记忆、画像、假设提示（统一注入到 system prompt）
            self.memory_injector.inject(user_input, self.messages)

            self.messages.append({"role": "user", "content": user_input})

            # 记录用户消息
            if self.conv_enabled:
                if not self.conv_store.session_id:
                    self.conv_session_id = self.conv_store.create_session(backend_name)
                    print(f"🆕 已创建新会话 [{self.conv_session_id}]")
                self.conv_store.save_message("user", user_input)

            # 技能匹配
            self.try_match_skill(user_input)

            # 内层循环：支持多步工具调用
            while True:
                try:
                    full_content, tool_calls, has_tool_call = await self.process_streaming_response(tools)
                except KeyboardInterrupt:
                    break

                if has_tool_call:
                    raw_message = self.backend.make_tool_call_raw_message(tool_calls, full_content)
                else:
                    raw_message = {"role": "assistant", "content": full_content}
                self.messages.append(raw_message)

                if tool_calls:
                    for tc in tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["arguments"]
                        
                        # 检查缓存
                        tool_cache = get_tool_cache()
                        cached_result = tool_cache.get(tool_name, tool_args)
                        
                        if cached_result is not None:
                            tool_text = cached_result
                            tool_duration = 0  # 缓存命中，不计耗时
                            print(f"📦 [{tool_name}] 缓存命中")
                        else:
                            print(f"🔧 调用工具：{tool_name}({tool_args})...")
                            tool_t0 = _time.perf_counter()
                            
                            # 带重试的工具调用
                            try:
                                tool_resp = await mcp_manager.call_tool_with_retry(tool_name, tool_args)
                            except RetryError as e:
                                print(f"⚠️ 工具调用重试耗尽：{e}")
                                tool_text = f"工具调用失败：{e}"
                                tool_duration = int((_time.perf_counter() - tool_t0) * 1000)
                            else:
                                tool_duration = int((_time.perf_counter() - tool_t0) * 1000)
                                tool_text = ""
                                for item in tool_resp.content:
                                    tool_text += item.text if hasattr(item, "text") else str(item)
                                
                                # 缓存结果
                                tool_cache.set(tool_name, tool_args, tool_text)

                        if self.conv_enabled:
                            self.conv_store.save_tool_call(
                                tool_name=tool_name,
                                arguments=tool_args,
                                result=tool_text,
                                duration_ms=tool_duration,
                            )

                        self.messages.append(
                            self.backend.make_tool_result_message(tc, tool_text)
                        )
                else:
                    if self.conv_enabled:
                        self.conv_store.save_message("assistant", full_content)
                    break

            # 对话后：进化观察（异步，不阻塞）
            if self.evo_handler.enabled and full_content:
                threading.Thread(
                    target=self.evo_handler.background_observe,
                    args=(user_input, full_content, self.backend),
                    daemon=True,
                ).start()

    def _dispatch_subsystem_command(self, user_input: str) -> bool | str | None:
        """
        分发 /memory 和 /history 子系统命令。

        Returns:
            None: 未匹配（非命令输入）
            True: 命令已处理
            str: session_id（恢复会话）
        """
        cmd = user_input.strip()

        # /memory 子命令
        if cmd.startswith("/memory") and self._memory_cmd_handler:
            return self._memory_cmd_handler.handle(user_input)

        # /history 子命令
        if cmd.startswith("/history") and self._history_cmd_handler:
            result = self._history_cmd_handler.handle(user_input)
            if result is False:
                return None
            return result

        return None

    def _restore_session(self, session_id: str) -> None:
        """恢复历史会话"""
        restored = self.conv_store.restore_session_messages(session_id)
        if restored:
            self.messages.extend(restored)
            self.turn_count = sum(1 for m in restored if m["role"] == "user")
            self.conv_store.switch_to_session(session_id)
            print(f"\n🔄 已恢复会话 [{session_id}]，共 {self.turn_count} 轮对话，可继续聊天")
        else:
            print(f"⚠️ 会话 [{session_id}] 无可恢复的消息")

    # ── 主入口 ──

    def _get_server_params(self) -> StdioServerParameters:
        """获取 MCP Server 连接参数"""
        venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
        if venv_python.exists():
            server_cmd = str(venv_python)
            server_args = ["server.py"]
        else:
            server_cmd = "uv"
            server_args = ["run", "server.py"]
        return StdioServerParameters(
            command=server_cmd,
            args=server_args,
            env={"PATH": os.environ["PATH"]},
        )

    async def run(self, backend_name: str) -> str | None:
        """运行 Agent 主流程

        Returns:
            str: 如果需要切换模型，返回新的 backend_name
            None: 正常退出
        """
        t0 = _time.perf_counter()
        label = self.backend.__class__.__name__.replace("Backend", "")
        print(f"\n🚀 正在启动 MCP Agent（{label}）...")

        t1 = _time.perf_counter()
        print(f"   ⏱ 模型后端初始化：{t1 - t0:.2f}s")

        # 加载 Skill 摘要
        self.skill_loader.load_summaries()

        # 初始化
        await self.initialize()
        t2 = _time.perf_counter()
        print(f"   ⏱ 记忆/会话数据库连接：{t2 - t1:.2f}s")

        # 打印进化引擎状态
        if self.evolution and self.evolution.enabled:
            evo_stats = self.evolution.get_full_stats()
            print(
                f"🧬 进化引擎：画像 {evo_stats['profile']['total_items']} 条，"
                f"假设 {evo_stats['hypotheses']['pending']} 条待确认"
            )

        # 打印缓存状态
        tool_cache = get_tool_cache()
        if tool_cache.enabled:
            print(f"📦 工具缓存：已启用（TTL {tool_cache._cache._ttl}s）")

        # 恢复上次会话
        restored_messages = self.restore_or_create_session(backend_name)

        # 配置 MCP Server
        server_params = self._get_server_params()

        # 初始化 MCP 会话管理器（带重试）
        self._mcp_manager = MCPSessionManager()
        self._exit_stack = AsyncExitStack()

        try:
            t3 = _time.perf_counter()

            # 带重试的连接（独立 exit_stack 管理重试过程中的临时资源）
            async def _do_connect():
                tmp_stack = AsyncExitStack()
                try:
                    read_stream, write_stream = await tmp_stack.enter_async_context(
                        stdio_client(server_params)
                    )
                    session = ClientSession(read_stream, write_stream)
                    # ClientSession 必须作为上下文管理器使用，才会启动
                    # _receive_loop 后台任务来接收服务端响应
                    await tmp_stack.enter_async_context(session)
                    await session.initialize()
                    # 成功：将资源转移到主 exit_stack
                    # 注意：tmp_stack 的清理回调会随 aclose() 执行，
                    # 但我们通过 pop_all 将回调转移到主栈
                    return session, tmp_stack
                except Exception:
                    await tmp_stack.aclose()
                    raise

            print("   🔄 正在连接 MCP Server（带重试机制）...")
            session, tmp_stack = await self._mcp_manager.connect_with_retry(_do_connect)
            # 成功后将临时栈的资源合并到主栈
            self._exit_stack = tmp_stack

            tools_resp = await session.list_tools()
            t4 = _time.perf_counter()
            print(f"   ⏱ MCP Server 连接 + 工具加载：{t4 - t3:.2f}s")
            print(f"✅ 已加载 {len(tools_resp.tools)} 个工具：")
            for tool in tools_resp.tools:
                desc_first_line = tool.description.split(chr(10))[0]
                print(f"   - {tool.name}：{desc_first_line}")
            tools = self.backend.build_tools(tools_resp.tools)

            self.print_skill_packages()
            print(f"   ⏱ 总启动耗时：{t4 - t0:.2f}s")

            self.setup_system_prompt(tools_resp)

            if restored_messages:
                self.messages.extend(restored_messages)
            self.print_restored_history(restored_messages)

            # 运行对话循环，返回值可能是新的 backend_name
            result = await self.run_conversation_loop(session, tools, backend_name)

            # 退出前保存
            self.memory_injector.save(self.messages, self.turn_count, self.backend, silent=True)

            if self.evolution:
                self.evolution.close()

            if self.conv_enabled and self.conv_store.session_id:
                self.conv_store.close_session()
                print(f"💾 会话 [{self.conv_store.session_id}] 已保存")

            # 打印缓存统计
            cache_stats = tool_cache.stats
            if cache_stats.total_requests > 0:
                print(f"📊 缓存统计：命中 {cache_stats.hits}，未命中 {cache_stats.misses}，命中率 {cache_stats.hit_rate:.1%}")

            print("\n👋 再见！")

            # 返回结果（可能是新的 backend_name）
            return result

        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"\n❌ 连接失败：{e}")
            print("   提示：请确保 server.py 可以正常运行")
        finally:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass

        return None
