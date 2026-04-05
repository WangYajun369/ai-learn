"""
Ollama 本地模型后端 - OpenAI 兼容接口
"""

import json
from typing import Generator

from .base import BaseBackend


class OllamaBackend(BaseBackend):
    """Ollama 本地模型，使用 OpenAI 兼容接口（tools / tool_calls 格式）"""

    def __init__(self, model: str = "qwen3.5:35b"):
        super().__init__(model)
        from openai import OpenAI
        self.client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # Ollama 不需要真实 key
        )

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

    def chat_stream(self, messages: list, tools: list) -> Generator[tuple[str, bool, dict | None], None, None]:
        """
        流式调用，返回 Generator[(content_delta, is_tool_call, tool_call_info)]

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
