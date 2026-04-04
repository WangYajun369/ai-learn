import asyncio
import os
import json
import yaml
from pathlib import Path
from contextlib import AsyncExitStack
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from dotenv import load_dotenv
from prompt_toolkit.shortcuts import PromptSession

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
        """阶段 3：获取 scripts/ 中脚本的路径"""
        script_path = self.skills_dir / "scripts" / script_name
        if script_path.exists():
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
}

BACKEND_LABELS = {
    "qwen": "通义千问 qwen-max（DashScope）",
    "glm": "智谱 GLM-4.5-Air（BigModel）",
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
    label = BACKEND_LABELS[backend_name]
    print(f"\n🚀 正在启动 MCP Agent（{label}）...")

    backend = BACKENDS[backend_name]()

    # ── 阶段 1：加载 Skill 摘要（~100 tokens）──
    skill_loader = SkillLoader()
    skills = skill_loader.load_summaries()

    # 1. 配置 MCP Server 启动参数
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "server.py"],
        env={"PATH": os.environ["PATH"]},
    )

    try:
        async with AsyncExitStack() as stack:
            # 2. 连接 MCP Server
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(server_params)
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            # 3. 获取工具列表
            tools_resp = await session.list_tools()
            print(f"✅ 已加载 {len(tools_resp.tools)} 个工具：")
            for tool in tools_resp.tools:
                desc_first_line = tool.description.split(chr(10))[0]
                print(f"   - {tool.name}：{desc_first_line}")
            tools = backend.build_tools(tools_resp.tools)

            # 3.5 打印技能包信息
            _print_skill_packages(skill_loader, skills)

            # 3.6 构建基础系统提示词
            tool_names = [f"- {tool.name}：{tool.description.split(chr(10))[0]}" for tool in tools_resp.tools]
            base_system_prompt = (
                "你是一个销售数据查询助手。你可以通过工具来帮助用户查询销售信息。\n\n"
                f"你可以使用以下工具：\n{chr(10).join(tool_names)}\n\n"
                '当用户问"有哪些功能"、"你能做什么"时，请介绍以上工具的能力。\n'
                '当用户问"有哪些产品"时，请调用 list_products 工具查询。\n'
                "回复使用中文。"
            )

            # 4. 对话主循环
            messages = [{"role": "system", "content": base_system_prompt}]
            active_skill: dict | None = None  # 当前激活的技能

            pt_session = PromptSession()
            while True:
                try:
                    user_input = await pt_session.prompt_async("\n👤 你：")
                except (KeyboardInterrupt, EOFError):
                    break
                if user_input.lower() in ["exit", "quit"]:
                    break

                messages.append({"role": "user", "content": user_input})

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

                # 5. 内层循环：支持多步工具调用
                while True:
                    result = backend.chat(messages, tools)
                    messages.append(result["raw_message"])

                    if result["tool_calls"]:
                        for tc in result["tool_calls"]:
                            print(f"🔧 调用工具：{tc['name']}({tc['arguments']})...")

                            tool_resp = await session.call_tool(tc["name"], tc["arguments"])

                            tool_text = ""
                            for item in tool_resp.content:
                                tool_text += item.text if hasattr(item, "text") else str(item)

                            messages.append(
                                backend.make_tool_result_message(tc, tool_text)
                            )
                    else:
                        print(f"\n🤖 Agent：{result['content'] or ''}")
                        break
    except KeyboardInterrupt:
        pass
    finally:
        print("\n👋 再见！")


if __name__ == "__main__":
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
