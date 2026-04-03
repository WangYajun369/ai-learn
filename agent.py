import asyncio
import os
import json
from contextlib import AsyncExitStack
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from dotenv import load_dotenv
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.shortcuts import PromptSession

load_dotenv()

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
        """
        调用模型，返回统一的中间结构：
          {
            "content": str | None,          # 文本回复（无工具调用时有值）
            "tool_calls": [                 # 工具调用列表（可能为空）
              {"id": ..., "name": ..., "arguments": {...}}
            ],
            "raw_message": dict             # 追加到 messages 的原始消息字典
          }
        """
        resp = self._Generation.call(
            model=self.model,
            api_key=self.api_key,
            messages=messages,
            functions=tools,
            result_format="message",
        )
        if resp.status_code != 200:
            raise RuntimeError(f"DashScope 调用失败 [{resp.status_code}]：{resp.message}")

        msg = resp.output.choices[0].message  # DictMixin（dict 子类）
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
        """构造工具结果消息（Qwen 使用 role=function）"""
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
        """检查模型是否可用，返回错误信息或 None"""
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
        """将 MCP 工具列表转换为 OpenAI-style tools 格式"""
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
        """递归清洗对象树中所有字符串的 surrogate 字符"""
        if isinstance(o, str):
            return o.encode("utf-8", errors="replace").decode("utf-8")
        if isinstance(o, dict):
            return {k: GLMBackend._clean_surrogates(v) for k, v in o.items()}
        if isinstance(o, list):
            return [GLMBackend._clean_surrogates(i) for i in o]
        return o

    def chat(self, messages: list, tools: list) -> dict:
        # 发送前对整个 messages 列表做安全清洗，防止 surrogate 字符导致 httpx 序列化失败
        safe_messages = self._clean_surrogates(messages)

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=safe_messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # 将 message 对象序列化为纯原生 Python dict 并清洗 surrogate 字符
        raw = json.loads(json.dumps(msg.model_dump(), default=str))
        raw = self._clean_surrogates(raw)
        # 去掉值为 None 的多余字段，保持消息列表整洁
        raw = {k: v for k, v in raw.items() if v is not None}

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                # arguments 可能是 str 或 bytes，统一转为 str 再解析
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
        """构造工具结果消息（GLM 使用 role=tool + tool_call_id）"""
        return {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": result_text,
        }


# ─────────────────────────────────────────────
#  Agent 核心（与模型无关）
# ─────────────────────────────────────────────

BACKENDS = {
    "qwen": QwenBackend,
    "glm": GLMBackend,
}

BACKEND_LABELS = {
    "qwen": "通义千问 qwen-max（DashScope）",
    "glm": "智谱 GLM-4.5-Air（BigModel）",
}


async def run_agent(backend_name: str):
    label = BACKEND_LABELS[backend_name]
    print(f"\n🚀 正在启动 MCP Agent（{label}）...")

    backend = BACKENDS[backend_name]()

    # 1. 配置 MCP Server 启动参数
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "server.py"],
        env={"PATH": os.environ["PATH"]},
    )

    async with AsyncExitStack() as stack:
        # 2. 连接 MCP Server（解包 read/write 两个流）
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        # 3. 获取工具列表并转换为对应模型格式
        tools_resp = await session.list_tools()
        print(f"✅ 已加载 {len(tools_resp.tools)} 个工具：")
        for tool in tools_resp.tools:
            desc_first_line = tool.description.split(chr(10))[0]
            print(f"   - {tool.name}：{desc_first_line}")
        tools = backend.build_tools(tools_resp.tools)

        # 3.5 构建系统提示词，告知 Agent 可用能力
        tool_names = [f"- {tool.name}：{tool.description.split(chr(10))[0]}" for tool in tools_resp.tools]
        system_prompt = (
            "你是一个销售数据查询助手。你可以通过工具来帮助用户查询销售信息。\n\n"
            f"你可以使用以下工具：\n{chr(10).join(tool_names)}\n\n"
            '当用户问"有哪些功能"、"你能做什么"时，请介绍以上工具的能力。\n'
            '当用户问"有哪些产品"时，请调用 list_products 工具查询。\n'
            "回复使用中文。"
        )

        # 4. 对话主循环
        messages = [{"role": "system", "content": system_prompt}]
        pt_session = PromptSession()
        while True:
            user_input = await pt_session.prompt_async("\n👤 你：")
            if user_input.lower() in ["exit", "quit"]:
                break

            messages.append({"role": "user", "content": user_input})

            # 5. 内层循环：支持多步工具调用（链式推理）
            while True:
                result = backend.chat(messages, tools)

                # 将模型消息追加到历史
                messages.append(result["raw_message"])

                if result["tool_calls"]:
                    # 有工具调用：逐个执行，追加结果，继续循环
                    for tc in result["tool_calls"]:
                        print(f"🔧 调用工具：{tc['name']}({tc['arguments']})...")

                        tool_resp = await session.call_tool(tc["name"], tc["arguments"])

                        # 提取工具返回文本
                        tool_text = ""
                        for item in tool_resp.content:
                            tool_text += item.text if hasattr(item, "text") else str(item)

                        messages.append(
                            backend.make_tool_result_message(tc, tool_text)
                        )

                    # 继续内层循环，让模型决定是否还需要调用更多工具
                else:
                    # 模型给出最终文本回复，退出内层循环
                    print(f"\n🤖 Agent：{result['content'] or ''}")
                    break


if __name__ == "__main__":
    import pick

    keys = list(BACKENDS.keys())
    options = [pick.Option(BACKEND_LABELS[k], k) for k in keys]
    options.append(pick.Option("退出程序", "__quit__"))

    while True:
        title = "🤖 请选择大模型后端（↑↓ 移动，Enter 确认）："
        selected, _ = pick.pick(options, title, indicator="❯")
        # pick (curses) 退出后终端可能有残留，清一下
        print("\033c", end="", flush=True)
        backend_arg = selected.value

        if backend_arg == "__quit__":
            print("\n👋 再见！")
            break

        # 检查模型可用性
        label = BACKEND_LABELS[backend_arg]
        print(f"\n🔍 正在检查 {label} ...")
        err = BACKENDS[backend_arg]().check()
        if err:
            print(f"❌ 模型不可用：{err}")
            pt_prompt("\n按 Enter 键重新选择...")
            print()
            continue
        print(f"✅ {label} — 当前模型可用")
        break

    if backend_arg == "__quit__":
        import sys
        sys.exit(0)

    asyncio.run(run_agent(backend_arg))
