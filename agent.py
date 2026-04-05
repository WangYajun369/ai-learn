import asyncio
import os
import json
import sys
import threading
import yaml
import time as _time
from pathlib import Path
from contextlib import AsyncExitStack
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from dotenv import load_dotenv
from prompt_toolkit.shortcuts import PromptSession
from prompt_toolkit.completion import Completer
from prompt_toolkit.document import Document
from memory_store import MemoryStore, generate_memory_id
from conversation_store import ConversationStore

load_dotenv()

# ─────────────────────────────────────────────
#  Skill 加载器（渐进式加载）
# ─────────────────────────────────────────────

class SkillLoader:
    """
    渐进式 Skill 加载器：
      阶段 1：启动时仅加载 name + description（~100 tokens）
      阶段 2：匹配成功后加载完整 SKILL.md（<5000 tokens）
      阶段 3：执行时按需加载 scripts/ 或 references/
    """

    def __init__(self, skills_dir: str = "sales-analysis"):
        self.skills_dir = Path(skills_dir)
        self.skills: list[dict] = []  # 阶段 1 缓存
        self._loaded_skill: dict | None = None  # 阶段 2 缓存

    def load_summaries(self) -> list[dict]:
        """
        阶段 1：扫描 skills_dir，仅提取 SKILL.md 的 YAML 头部信息。
        用于技能路由与快速匹配。
        """
        skill_md = self.skills_dir / "SKILL.md"
        if not skill_md.exists():
            return []

        content = skill_md.read_text(encoding="utf-8")
        # 解析 YAML front matter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1])
                if meta and isinstance(meta, dict):
                    self.skills = [{
                        "name": meta.get("name", ""),
                        "description": meta.get("description", "").strip(),
                        "trigger_keywords": meta.get("trigger_keywords", []),
                    }]
        return self.skills

    def match_skill(self, user_input: str) -> dict | None:
        """根据用户输入匹配技能包，返回匹配的 skill summary"""
        input_lower = user_input.lower()
        for skill in self.skills:
            # 检查触发词
            for kw in skill.get("trigger_keywords", []):
                if kw.lower() in input_lower:
                    return skill
            # 检查 description 关键词
            for word in ["分析", "报告", "销售", "业绩"]:
                if word in input_lower and "销售" in skill.get("description", ""):
                    return skill
        return None

    def load_full_skill(self, skill_name: str) -> str | None:
        """
        阶段 2：加载完整的 SKILL.md 内容。
        仅在技能匹配成功后调用。
        """
        skill_md = self.skills_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        content = skill_md.read_text(encoding="utf-8")
        # 去掉 YAML front matter，只保留指令部分
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content

    def load_reference(self, filename: str) -> str | None:
        """阶段 3：按需加载 references/ 中的文件"""
        ref_path = self.skills_dir / "references" / filename
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8")
        return None

    def get_script_path(self, script_name: str) -> str | None:
        """
        阶段 3：获取 scripts/ 中脚本的路径。
        
        安全性：防止路径遍历攻击，确保脚本路径在 scripts 目录内。
        """
        # 防止路径遍历攻击：拒绝包含 .. / \ 等危险字符
        if not script_name:
            return None
        
        # 检查是否包含路径遍历字符
        dangerous_chars = ["..", "/", "\\", "\x00"]
        if any(char in script_name for char in dangerous_chars):
            print(f"⚠️ 脚本名称包含非法字符：{script_name}")
            return None
        
        # 只允许 .py 文件
        if not script_name.endswith(".py"):
            print(f"⚠️ 只支持 Python 脚本（.py）：{script_name}")
            return None
        
        script_path = self.skills_dir / "scripts" / script_name
        
        # 确保解析后的路径仍在 scripts 目录内（防止符号链接攻击）
        try:
            scripts_dir = (self.skills_dir / "scripts").resolve()
            resolved_path = script_path.resolve()
            
            # 检查是否在 scripts 目录内
            if not str(resolved_path).startswith(str(scripts_dir)):
                print(f"⚠️ 脚本路径不在 scripts 目录内：{script_name}")
                return None
                
        except Exception as e:
            print(f"⚠️ 路径解析失败：{e}")
            return None
        
        if script_path.exists() and script_path.is_file():
            return str(script_path)
        return None


# ─────────────────────────────────────────────
#  模型后端：DashScope（通义千问）
# ─────────────────────────────────────────────

class QwenBackend:
    """通义千问 qwen-max，使用 DashScope SDK（functions / function_call 格式）"""

    def __init__(self, model: str = "qwen-max"):
        from dashscope import Generation
        self._Generation = Generation
        self.model = model
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

    def check(self) -> str | None:
        """检查模型是否可用，返回错误信息或 None"""
        if not self.api_key or "your-" in self.api_key:
            return "未配置 DASHSCOPE_API_KEY，请在 .env 文件中设置有效的 API Key"
        try:
            resp = self._Generation.call(
                model=self.model,
                api_key=self.api_key,
                messages=[{"role": "user", "content": "hi"}],
            )
            if resp.status_code != 200:
                return f"API 返回错误 [{resp.status_code}]：{resp.message}"
        except Exception as e:
            return f"连接失败：{e}"
        return None

    def build_tools(self, mcp_tools) -> list:
        """将 MCP 工具列表转换为 Qwen functions 格式"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            }
            for tool in mcp_tools
        ]

    def chat(self, messages: list, tools: list) -> dict:
        resp = self._Generation.call(
            model=self.model,
            api_key=self.api_key,
            messages=messages,
            functions=tools,
            result_format="message",
        )
        if resp.status_code != 200:
            raise RuntimeError(f"DashScope 调用失败 [{resp.status_code}]：{resp.message}")

        msg = resp.output.choices[0].message
        raw = dict(msg)

        tool_calls = []
        if msg.get("function_call"):
            fc = msg["function_call"]
            tool_calls.append({
                "id": fc.get("id", ""),
                "name": fc["name"],
                "arguments": json.loads(fc["arguments"]),
            })

        return {
            "content": msg.get("content"),
            "tool_calls": tool_calls,
            "raw_message": raw,
        }

    def chat_stream(self, messages: list, tools: list):
        """流式调用，返回 Generator[(content_delta, is_tool_call, tool_call_info)]"""
        stream = self._Generation.call(
            model=self.model,
            api_key=self.api_key,
            messages=messages,
            functions=tools,
            result_format="message",
            stream=True,
            incremental_output=True,
        )

        for chunk in stream:
            # chunk 是 GenerationResponse（dict-like）
            if chunk.status_code and chunk.status_code != 200:
                raise RuntimeError(f"DashScope 流式调用失败 [{chunk.status_code}]：{chunk.message}")

            msg = (chunk.output.choices[0].message
                   if chunk.output and chunk.output.choices else None)
            if not msg:
                continue

            # 工具调用：function_call 信息在最后一个 chunk 中一次性返回
            if msg.get("function_call"):
                fc = msg["function_call"]
                tool_call_info = {
                    "id": fc.get("id", ""),
                    "name": fc["name"],
                    "arguments": json.loads(fc["arguments"]),
                }
                yield (msg.get("content", ""), True, tool_call_info)
            else:
                content_delta = msg.get("content", "") or ""
                if content_delta:
                    yield (content_delta, False, None)

    def make_tool_call_raw_message(self, tool_calls: list, content: str = "") -> dict:
        """将流式收集的 tool_calls 转换为 Qwen 的 raw_message 格式"""
        # Qwen functions 格式：只支持单个 tool_call per message
        tc = tool_calls[0]
        return {
            "role": "assistant",
            "content": content or None,
            "function_call": {
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
            },
        }

    def make_tool_result_message(self, tool_call: dict, result_text: str) -> dict:
        return {
            "role": "function",
            "name": tool_call["name"],
            "content": result_text,
        }


# ─────────────────────────────────────────────
#  模型后端：BigModel（智谱 GLM）
# ─────────────────────────────────────────────

class GLMBackend:
    """智谱 GLM-4.5-Air，使用 zai-sdk（tools / tool_calls 格式，OpenAI 兼容）"""

    def __init__(self, model: str = "glm-4.5-air"):
        from zai import ZhipuAiClient
        self.client = ZhipuAiClient(api_key=os.getenv("BIGMODEL_API_KEY"))
        self.model = model

    def check(self) -> str | None:
        api_key = os.getenv("BIGMODEL_API_KEY")
        if not api_key or "your-" in api_key:
            return "未配置 BIGMODEL_API_KEY，请在 .env 文件中设置有效的 API Key"
        try:
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
            )
        except Exception as e:
            return f"连接失败：{e}"
        return None

    def build_tools(self, mcp_tools) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in mcp_tools
        ]

    @staticmethod
    def _clean_surrogates(o):
        if isinstance(o, str):
            return o.encode("utf-8", errors="replace").decode("utf-8")
        if isinstance(o, dict):
            return {k: GLMBackend._clean_surrogates(v) for k, v in o.items()}
        if isinstance(o, list):
            return [GLMBackend._clean_surrogates(i) for i in o]
        return o

    def chat(self, messages: list, tools: list) -> dict:
        safe_messages = self._clean_surrogates(messages)

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=safe_messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        raw = json.loads(json.dumps(msg.model_dump(), default=str))
        raw = self._clean_surrogates(raw)
        raw = {k: v for k, v in raw.items() if v is not None}

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args_raw = tc.function.arguments
                if isinstance(args_raw, bytes):
                    args_raw = args_raw.decode("utf-8", errors="replace")
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(args_raw),
                })

        return {
            "content": msg.content,
            "tool_calls": tool_calls,
            "raw_message": raw,
        }

    def chat_stream(self, messages: list, tools: list):
        """流式调用，返回 Generator[(content_delta, is_tool_call, tool_call_info)]

        OpenAI 兼容格式中，tool_calls 可能分片返回（name 和 arguments 分开），
        所以在内部累积，最后一个 chunk 统一 yield。
        """
        safe_messages = self._clean_surrogates(messages)

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=safe_messages,
            tools=tools,
            tool_choice="auto",
            stream=True,
        )

        # 累积 tool_calls 的分片
        tc_index_map: dict[int, dict] = {}  # index -> {"id", "name", "arguments"}

        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index if tc_delta.index is not None else 0
                    if idx not in tc_index_map:
                        tc_index_map[idx] = {"id": tc_delta.id or "", "name": "", "arguments": ""}
                    entry = tc_index_map[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        entry["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        args_raw = tc_delta.function.arguments
                        if isinstance(args_raw, bytes):
                            args_raw = args_raw.decode("utf-8", errors="replace")
                        entry["arguments"] += args_raw
            else:
                content_delta = delta.content or ""
                if content_delta:
                    yield (content_delta, False, None)

        # 所有 tool_calls 累积完毕，统一 yield
        for idx in sorted(tc_index_map):
            entry = tc_index_map[idx]
            tool_call_info = {
                "id": entry["id"],
                "name": entry["name"],
                "arguments": json.loads(entry["arguments"]) if entry["arguments"] else {},
            }
            yield ("", True, tool_call_info)

    def make_tool_call_raw_message(self, tool_calls: list, content: str = "") -> dict:
        """将流式收集的 tool_calls 转换为 GLM/OpenAI 的 raw_message 格式"""
        return {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ],
        }

    def make_tool_result_message(self, tool_call: dict, result_text: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result_text,
        }


# ─────────────────────────────────────────────
#  模型后端：Ollama（本地模型）
# ─────────────────────────────────────────────

class OllamaBackend:
    """Ollama 本地模型，使用 OpenAI 兼容接口（tools / tool_calls 格式）"""

    def __init__(self, model: str = "qwen3.5:35b"):
        from openai import OpenAI
        self.client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # Ollama 不需要真实 key
        )
        self.model = model

    def check(self) -> str | None:
        """检查 Ollama 服务是否运行且模型可用"""
        try:
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
        except ConnectionError:
            return "无法连接 Ollama 服务，请确认 ollama serve 已启动（http://localhost:11434）"
        except Exception as e:
            err = str(e)
            if "model" in err.lower() and "not found" in err.lower():
                return f"模型 {self.model} 未找到，请运行 ollama pull {self.model}"
            return f"连接失败：{e}"
        return None

    def build_tools(self, mcp_tools) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in mcp_tools
        ]

    def chat(self, messages: list, tools: list) -> dict:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        raw = json.loads(json.dumps(msg.model_dump(), default=str))
        raw = {k: v for k, v in raw.items() if v is not None}

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                args_raw = tc.function.arguments
                if isinstance(args_raw, bytes):
                    args_raw = args_raw.decode("utf-8", errors="replace")
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(args_raw),
                })

        return {
            "content": msg.content,
            "tool_calls": tool_calls,
            "raw_message": raw,
        }

    def chat_stream(self, messages: list, tools: list):
        """流式调用，返回 Generator[(content_delta, is_tool_call, tool_call_info)]

        OpenAI 兼容格式中，tool_calls 可能分片返回（name 和 arguments 分开），
        所以在内部累积，最后一个 chunk 统一 yield。
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)

        # 累积 tool_calls 的分片
        tc_index_map: dict[int, dict] = {}

        for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index if tc_delta.index is not None else 0
                    if idx not in tc_index_map:
                        tc_index_map[idx] = {"id": tc_delta.id or "", "name": "", "arguments": ""}
                    entry = tc_index_map[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function and tc_delta.function.name:
                        entry["name"] = tc_delta.function.name
                    if tc_delta.function and tc_delta.function.arguments:
                        args_raw = tc_delta.function.arguments
                        if isinstance(args_raw, bytes):
                            args_raw = args_raw.decode("utf-8", errors="replace")
                        entry["arguments"] += args_raw
            else:
                content_delta = delta.content or ""
                if content_delta:
                    yield (content_delta, False, None)

        # 所有 tool_calls 累积完毕，统一 yield
        for idx in sorted(tc_index_map):
            entry = tc_index_map[idx]
            tool_call_info = {
                "id": entry["id"],
                "name": entry["name"],
                "arguments": json.loads(entry["arguments"]) if entry["arguments"] else {},
            }
            yield ("", True, tool_call_info)

    def make_tool_call_raw_message(self, tool_calls: list, content: str = "") -> dict:
        """将流式收集的 tool_calls 转换为 Ollama/OpenAI 的 raw_message 格式"""
        return {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ],
        }

    def make_tool_result_message(self, tool_call: dict, result_text: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result_text,
        }


# ─────────────────────────────────────────────
#  Agent 核心（集成 Skills）
# ─────────────────────────────────────────────

BACKENDS = {
    "qwen": QwenBackend,
    "glm": GLMBackend,
    "ollama": OllamaBackend,
}

BACKEND_LABELS = {
    "qwen": "通义千问 qwen-max（DashScope）",
    "glm": "智谱 GLM-4.5-Air（BigModel）",
    "ollama": "Ollama 本地模型（qwen3.5:35b）",
}


def _print_skill_packages(skill_loader: SkillLoader, skills: list):
    """格式化打印已加载的技能包信息（名称、描述、触发词、脚本、参考文件）"""
    import textwrap
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
        scripts_dir = skill_loader.skills_dir / "scripts"
        refs_dir = skill_loader.skills_dir / "references"
        if scripts_dir.exists():
            py_files = sorted(p.name for p in scripts_dir.glob("*.py") if p.name != "__init__.py")
            if py_files:
                print(f"   │  脚本：{', '.join(py_files)}")
        if refs_dir.exists():
            ref_files = sorted(p.name for p in refs_dir.glob("*") if p.name != "__init__.py" and not p.name.endswith(".pyc"))
            if ref_files:
                print(f"   │  参考：{', '.join(ref_files)}")
        print(f"   └{'─' * (len(s['name']) + 5)}")


async def run_agent(backend_name: str):
    _t0 = _time.perf_counter()
    label = BACKEND_LABELS[backend_name]
    print(f"\n🚀 正在启动 MCP Agent（{label}）...")

    backend = BACKENDS[backend_name]()
    _t1 = _time.perf_counter()
    print(f"   ⏱ 模型后端初始化：{_t1 - _t0:.2f}s")

    # ── 阶段 1：加载 Skill 摘要（~100 tokens）──
    skill_loader = SkillLoader()
    skills = skill_loader.load_summaries()

    # ── 长期记忆：连接向量数据库 ──
    memory_store = MemoryStore()
    memory_enabled = memory_store.connect()
    session_id = generate_memory_id()
    _t2 = _time.perf_counter()
    print(f"   ⏱ 记忆/会话数据库连接：{_t2 - _t1:.2f}s")

    # ── 会话记录：连接 SQLite ──
    conv_store = ConversationStore()
    conv_enabled = conv_store.connect()

    # ── 自动恢复最近一次会话 ──
    conv_session_id = None
    restored_messages = []
    if conv_enabled:
        recent = conv_store.list_sessions(limit=1)
        if recent:
            last_sid = recent[0]["id"]
            last_status = recent[0].get("status", "closed")
            restored_messages = conv_store.restore_session_messages(last_sid)
            
            # 无论是否有消息，都恢复会话（即使上次异常退出）
            conv_session_id = last_sid
            conv_store.switch_to_session(last_sid)
            
            if restored_messages:
                print(f"🔄 检测到上次会话 [{last_sid}]（{last_status}，{len(restored_messages)} 条消息）")
            else:
                print(f"🔄 检测到上次会话 [{last_sid}]（{last_status}，无历史消息）")
        else:
            # 没有历史会话，创建新会话
            conv_session_id = conv_store.create_session(backend_name)
            print(f"🆕 已创建新会话 [{conv_session_id}]")

    # 1. 配置 MCP Server 启动参数
    # 优先使用 .venv 中的 python，省去 uv run 的依赖解析开销（约 0.5-1s）
    _venv_python = Path(__file__).parent / ".venv" / "bin" / "python"
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

    # 追踪本次会话的对话轮次（用于判断是否需要保存记忆）
    turn_count = 0

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
            tools = backend.build_tools(tools_resp.tools)

            # 3.5 打印技能包信息
            _print_skill_packages(skill_loader, skills)
            print(f"   ⏱ 总启动耗时：{_t4 - _t0:.2f}s")

            # 3.6 构建基础系统提示词
            tool_names = [f"- {tool.name}：{tool.description.split(chr(10))[0]}" for tool in tools_resp.tools]
            base_system_prompt = (
                "你是一个销售数据查询助手。你可以通过工具来帮助用户查询销售信息。\n\n"
                f"你可以使用以下工具：\n{chr(10).join(tool_names)}\n\n"
                '当用户问"有哪些功能"、"你能做什么"时，请介绍以上工具的能力。\n'
                '当用户问"有哪些产品"时，请调用 list_products 工具查询。\n'
                "回复使用中文。"
            )

            # 3.7 初始化 system prompt（稍后可能注入记忆）
            messages = [{"role": "system", "content": base_system_prompt}]
            active_skill: dict | None = None  # 当前激活的技能

            # 3.8 恢复上次会话上下文
            if restored_messages:
                messages.extend(restored_messages)
                turn_count = sum(1 for m in restored_messages if m["role"] == "user")
                print(f"   ✅ 已加载 {turn_count} 轮历史对话")
                
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
            elif conv_session_id:
                print("   ℹ️ 当前会话暂无历史消息")
                print("   输入 /new 可创建新会话\n")

            def _inject_memory(user_input: str):
                """根据用户输入检索相关记忆，注入到 system prompt"""
                if not memory_enabled or not memory_store._collection:
                    return
                count = memory_store._collection.count()
                if count == 0:
                    return
                related = memory_store.search(user_input, n_results=3)
                if related:
                    memory_lines = ["以下是相关的历史记忆（供参考）："]
                    for i, m in enumerate(related, 1):
                        ts = m["metadata"].get("timestamp", "")
                        memory_lines.append(f"  {i}. [{ts}] {m['content']}")
                    memory_text = "\n".join(memory_lines)
                    # 在 system prompt 末尾追加记忆
                    current_system = messages[0]["content"]
                    messages[0] = {
                        "role": "system",
                        "content": current_system + "\n\n" + memory_text,
                    }
                    print("   🧠 已检索到相关历史记忆")

            def _save_memory_to_db(silent: bool = False):
                """调用 LLM 生成对话摘要并存入向量数据库"""
                if not memory_enabled or not memory_store._collection:
                    return
                if turn_count < 1:
                    # 对话轮次太少，不保存
                    return

                try:
                    summary_prompt = MemoryStore.build_summary_prompt(messages)
                    # 用一个轻量级调用让 LLM 生成摘要
                    summary_messages = [
                        {"role": "system", "content": "你是信息提取助手。只输出摘要文本，不要加任何前缀后缀。"},
                        {"role": "user", "content": summary_prompt},
                    ]
                    result = backend.chat(summary_messages, [])
                    summary = result.get("content", "").strip()

                    if not summary or summary in ("无", "无。", "没有需要记住的信息。"):
                        return

                    # 提取话题标签
                    topics = _extract_topics(messages)
                    memory_store.save(summary, session_id, topics)
                except Exception as e:
                    if not silent:
                        print(f"   ⚠️ 记忆保存失败：{e}")

            def _extract_topics(msgs: list[dict]) -> list[str]:
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

            # 4. 对话主循环
            # 定义斜杠命令补全（带描述说明）
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
                    if conv_enabled:
                        conv_store.close_session()
                        new_sid = conv_store.create_session(backend_name)
                    else:
                        new_sid = generate_memory_id()
                    messages = [{"role": "system", "content": base_system_prompt}]
                    active_skill = None
                    turn_count = 0
                    session_id = generate_memory_id()
                    print(f"\n🆕 已创建新会话 [{new_sid}]\n")
                    continue

                # ── 帮助命令 ──
                if user_input.strip().lower() in ("/help", "/help ", "/?"):
                    print("\n📖 命令帮助：")
                    print("═" * 60)
                    for cmd, desc in SLASH_COMMANDS:
                        print(f"  {cmd:<20} - {desc}")
                    print("═" * 60)
                    continue

                # ── 记忆管理命令 ──
                handled = _handle_memory_command(user_input, memory_store, memory_enabled)
                if handled:
                    continue

                # ── 会话记录命令 ──
                history_result = _handle_history_command(user_input, conv_store, conv_enabled)
                if history_result is True or history_result is False:
                    if history_result:
                        continue
                elif isinstance(history_result, str):
                    # 返回了 session_id，执行恢复
                    restored = conv_store.restore_session_messages(history_result)
                    if restored:
                        messages.extend(restored)
                        # 统计恢复的用户消息数作为 turn_count
                        turn_count = sum(1 for m in restored if m["role"] == "user")
                        conv_store.switch_to_session(history_result)
                        print(f"\n🔄 已恢复会话 [{history_result}]，共 {turn_count} 轮对话，可继续聊天")
                    else:
                        print(f"⚠️ 会话 [{history_result}] 无可恢复的消息")
                    continue

                if user_input.lower() in ["exit", "quit", "/exit"]:
                    break

                turn_count += 1

                # ── 检索相关记忆并注入 ──
                _inject_memory(user_input)

                messages.append({"role": "user", "content": user_input})

                # ── 记录用户消息 ──
                if conv_enabled:
                    # 确保会话存在（防止清空历史后未创建新会话）
                    if not conv_store.session_id:
                        conv_session_id = conv_store.create_session(backend_name)
                        print(f"🆕 已创建新会话 [{conv_session_id}]")
                    conv_store.save_message("user", user_input)

                # ── 阶段 1→2：技能匹配 ──
                matched = skill_loader.match_skill(user_input) if skills else None
                if matched and active_skill is None:
                    print(f"\n📦 匹配到技能包：{matched['name']}")
                    full_skill = skill_loader.load_full_skill(matched["name"])
                    if full_skill:
                        # ── 阶段 2：加载完整 SKILL.md（<5000 tokens）──
                        active_skill = matched
                        messages[0] = {
                            "role": "system",
                            "content": full_skill,
                        }
                        print("   ✅ 技能指令已加载（完整 SKILL.md）")

                        # 同时加载报告模板作为参考
                        template = skill_loader.load_reference("report_template.md")
                        if template:
                            messages.append({
                                "role": "system",
                                "content": f"以下是你的报告输出模板，请严格按照此格式生成报告：\n\n{template}",
                            })
                            print("   ✅ 报告模板已加载（references/report_template.md）")

                # 5. 内层循环：支持多步工具调用（流式输出）
                while True:
                    # ── 流式调用 LLM，逐 token 实时输出 ──
                    cancelled = threading.Event()
                    _stream_error: list = [None]
                    _stream_chunks: list = []  # 线程安全的 chunk 队列
                    _stream_lock = threading.Lock()
                    _stream_done = threading.Event()

                    def _run_stream():
                        try:
                            _stream_error[0] = None
                            for chunk_tuple in backend.chat_stream(messages, tools):
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
                    import re as _re
                    _strip_line_re = _re.compile(r"\n[ \t]+")

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
                        break

                    if _stream_error[0] is not None:
                        raise _stream_error[0]

                    if first_chunk:
                        # 没有任何输出（模型可能返回空）
                        print("\r" + " " * 30 + "\r", end="", flush=True)
                    else:
                        print()  # 换行

                    # ── 构造 raw_message 存入消息历史 ──
                    if has_tool_call:
                        raw_message = backend.make_tool_call_raw_message(tool_calls, full_content)
                    else:
                        raw_message = {"role": "assistant", "content": full_content}
                    messages.append(raw_message)

                    if tool_calls:
                        for tc in tool_calls:
                            print(f"🔧 调用工具：{tc['name']}({tc['arguments']})...")
                            tool_t0 = __import__("time").perf_counter()

                            tool_resp = await session.call_tool(tc["name"], tc["arguments"])

                            tool_duration = int((__import__("time").perf_counter() - tool_t0) * 1000)

                            tool_text = ""
                            for item in tool_resp.content:
                                tool_text += item.text if hasattr(item, "text") else str(item)

                            # ── 记录工具调用 ──
                            if conv_enabled:
                                conv_store.save_tool_call(
                                    tool_name=tc["name"],
                                    arguments=tc["arguments"],
                                    result=tool_text,
                                    duration_ms=tool_duration,
                                )

                            messages.append(
                                backend.make_tool_result_message(tc, tool_text)
                            )
                    else:
                        # ── 记录助手回复 ──
                        if conv_enabled:
                            conv_store.save_message("assistant", full_content)
                        break

            # ── 退出前保存对话记忆（静默模式，网络错误不打断退出）──
            _save_memory_to_db(silent=True)

            # ── 退出前关闭会话记录 ──
            if conv_enabled and conv_store.session_id:
                conv_store.close_session()
                print(f"💾 会话 [{conv_store.session_id}] 已保存")

    except KeyboardInterrupt:
        pass
    finally:
        print("\n👋 再见！")
        # 使用 os._exit 跳过 ONNX Runtime 的 atexit 清理
        # （ChromaDB 默认嵌入模型退出时会缓慢解压/清理 onnx.tar.gz）
        import os as _os
        _os._exit(0)


def _handle_memory_command(user_input: str, memory_store: MemoryStore, enabled: bool) -> bool:
    """
    处理以 /memory 开头的记忆管理命令。
    返回 True 表示命令已处理（不进入主对话流程）。
    """
    cmd = user_input.strip().lower()

    if not cmd.startswith("/memory"):
        return False

    parts = cmd.split(maxsplit=1)
    sub_cmd = parts[1] if len(parts) > 1 else ""

    if not enabled:
        print("⚠️ 向量数据库未连接，记忆功能不可用")
        return True

    if sub_cmd in ("", "list", "ls"):
        # 列出所有记忆
        all_memories = memory_store.get_all(limit=10)
        if not all_memories:
            print("📚 暂无长期记忆")
        else:
            print(f"📚 最近 {len(all_memories)} 条记忆：")
            for i, m in enumerate(all_memories, 1):
                ts = m["metadata"].get("timestamp", "")
                session = m["metadata"].get("session_id", "")
                print(f"   {i}. [{ts}][{session}] {m['content'][:80]}")
        return True

    if sub_cmd.startswith("search "):
        # 语义搜索记忆
        query = user_input.strip()[len("/memory search "):]
        if not query:
            print("用法：/memory search <关键词>")
            return True
        results = memory_store.search(query, n_results=5)
        if not results:
            print(f"🔍 未找到与「{query}」相关的记忆")
        else:
            print(f"🔍 与「{query}」相关的记忆（{len(results)} 条）：")
            for i, m in enumerate(results, 1):
                dist = m.get("distance", 0)
                print(f"   {i}. [相似度: {1 - dist:.2f}] {m['content'][:100]}")
        return True

    if sub_cmd == "clear":
        # 清空所有记忆
        count = memory_store.clear_all()
        print(f"🗑️ 已清空 {count} 条记忆")
        return True

    if sub_cmd.startswith("delete "):
        # 删除指定会话的记忆
        session_id = user_input.strip()[len("/memory delete "):].strip()
        if not session_id:
            print("用法：/memory delete <会话ID>")
            return True
        count = memory_store.delete_session(session_id)
        if count > 0:
            print(f"🗑️ 已删除会话 [{session_id}] 的 {count} 条记忆")
        else:
            print(f"⚠️ 未找到会话 [{session_id}] 的记忆")
        return True

    if sub_cmd == "stats":
        # 统计信息
        count = memory_store._collection.count() if memory_store._collection else 0
        print(f"📊 记忆统计：共 {count} 条记忆，存储于 {memory_store.db_path}")
        return True

    print("📚 记忆管理命令：")
    print("   /memory list              - 列出最近记忆")
    print("   /memory search <关键词>   - 语义搜索记忆")
    print("   /memory delete <会话ID>   - 删除指定会话的记忆")
    print("   /memory clear             - 清空所有记忆")
    print("   /memory stats             - 查看记忆统计")
    return True


def _handle_history_command(user_input: str, conv_store: ConversationStore, enabled: bool) -> str | bool:
    """
    处理 /history 开头的会话记录命令。
    返回 True 表示命令已处理。
    返回 session_id 字符串表示请求恢复该会话（由调用方处理）。
    返回 False 表示未匹配。
    """
    cmd = user_input.strip()

    if not cmd.startswith("/history"):
        return False

    if not enabled:
        print("⚠️ 会话记录功能不可用")
        return True

    parts = cmd.split(maxsplit=1)
    sub_cmd = parts[1] if len(parts) > 1 else ""

    if sub_cmd in ("", "list", "ls"):
        # 列出最近会话
        sessions = conv_store.list_sessions(limit=10)
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

    if sub_cmd == "show" or sub_cmd.startswith("show "):
        # 查看：如果没带 ID，用 pick 选择器列出最近会话供选择
        sid = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""

        if not sid:
            sessions = conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            # 用 pick 选择器让用户上下键选择会话
            import pick as _pick
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
        detail = conv_store.get_session_detail(sid)
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
                print(f"\n  {role_label}：{content}")

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

    if sub_cmd == "stats":
        stats = conv_store.get_stats()
        print("📊 会话统计：")
        print(f"   总会话数：{stats['total_sessions']}")
        print(f"   未关闭会话：{stats['active_sessions']}")
        print(f"   总消息数：{stats['total_messages']}")
        print(f"   总工具调用：{stats['total_tool_calls']}")
        return True

    if sub_cmd == "resume" or sub_cmd.startswith("resume "):
        # 恢复历史会话：用 pick 选择器让用户选择
        target_sid = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""

        if not target_sid:
            sessions = conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            import pick as _pick
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
        detail = conv_store.get_session_detail(target_sid)
        if not detail:
            print(f"❌ 未找到会话 [{target_sid}]")
            return True
        # 返回 session_id，由主循环执行恢复
        return target_sid

    if sub_cmd == "delete" or sub_cmd.startswith("delete "):
        # 删除指定会话
        target_sid = cmd.split(maxsplit=2)[2].strip() if len(cmd.split(maxsplit=2)) > 2 else ""

        if not target_sid:
            sessions = conv_store.list_sessions(limit=10)
            if not sessions:
                print("💬 暂无历史会话")
                return True
            import pick as _pick
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

        msg_count = conv_store.delete_session(target_sid)
        print(f"🗑️ 已删除会话 [{target_sid}]（{msg_count} 条消息）")
        return True

    if sub_cmd == "clear":
        # 清空所有会话
        count = conv_store.clear_all()
        print(f"🗑️ 已清空全部 {count} 个会话")
        print("💡 提示：下一条消息将自动创建新会话")
        return True

    print("💬 会话记录命令：")
    print("   /history            - 列出最近会话")
    print("   /history show       - 选择并查看会话详情（上下键选择）")
    print("   /history show <ID>  - 查看指定会话详情（含调用链）")
    print("   /history resume     - 恢复历史会话并继续对话（上下键选择）")
    print("   /history delete     - 删除指定会话（上下键选择）")
    print("   /history clear      - 清空所有历史会话")
    print("   /history stats      - 查看会话统计")
    return True


def _legacy_repl_entry():
    """纯终端 REPL 入口（默认启动模式）"""
    import pick
    import sys

    try:
        keys = list(BACKENDS.keys())
        options = [pick.Option(BACKEND_LABELS[k], k) for k in keys]
        options.append(pick.Option("退出程序", "__quit__"))

        while True:
            title = "🤖 请选择大模型后端（↑↓ 移动，Enter 确认）："
            selected, _ = pick.pick(options, title, indicator="❯")
            print("\033c", end="", flush=True)
            backend_arg = selected.value

            if backend_arg == "__quit__":
                break

            label = BACKEND_LABELS[backend_arg]
            print(f"\n🔍 正在检查 {label} ...")
            err = BACKENDS[backend_arg]().check()
            if err:
                print(f"❌ 模型不可用：{err}")
                from prompt_toolkit import prompt as pt_prompt
                pt_prompt("\n按 Enter 键重新选择...")
                print()
                continue
            print(f"✅ {label} — 当前模型可用")
            break
    except KeyboardInterrupt:
        print("\n👋 再见！")
        sys.exit(0)

    if backend_arg == "__quit__":
        print("\n👋 再见！")
        sys.exit(0)

    asyncio.run(run_agent(backend_arg))


if __name__ == "__main__":
    import sys

    # 默认启动纯终端 REPL（简洁、无额外样式依赖）
    _legacy_repl_entry()
    sys.exit(0)
