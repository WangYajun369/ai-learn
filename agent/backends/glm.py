"""
智谱 GLM 后端 - zai-sdk
"""

import json
import os
from typing import Generator

from .base import BaseBackend


class GLMBackend(BaseBackend):
    """智谱 GLM-4.5-Air，使用 zai-sdk（tools / tool_calls 格式，OpenAI 兼容）"""

    def __init__(self, model: str = "glm-4.5-air"):
        super().__init__(model)
        self._client = None

    @property
    def client(self):
        """延迟初始化客户端"""
        if self._client is None:
            from zai import ZhipuAiClient
            self._client = ZhipuAiClient(api_key=os.getenv("BIGMODEL_API_KEY"))
        return self._client

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

    def chat_stream(self, messages: list, tools: list) -> Generator[tuple[str, bool, dict | None], None, None]:
        """
        流式调用，返回 Generator[(content_delta, is_tool_call, tool_call_info)]

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
