"""
通义千问后端 - DashScope SDK
"""

import json
import os
from typing import Generator

from .base import BaseBackend


class QwenBackend(BaseBackend):
    """通义千问 qwen-max，使用 DashScope SDK（functions / function_call 格式）"""

    def __init__(self, model: str = "qwen-max"):
        super().__init__(model)
        from dashscope import Generation
        self._Generation = Generation

    @property
    def api_key(self):
        """延迟获取 API key，确保 dotenv 已加载"""
        return os.getenv("DASHSCOPE_API_KEY")

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

    def chat_stream(self, messages: list, tools: list) -> Generator[tuple[str, bool, dict | None], None, None]:
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
