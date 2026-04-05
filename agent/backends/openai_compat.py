"""
OpenAI 兼容后端基类

GLM、Ollama 等使用 tools / tool_calls 格式的后端共享此基类，
消除 chat()、chat_stream()、make_tool_call_raw_message() 等方法的重复代码。
"""

import json
from typing import Generator

from .base import BaseBackend


class OpenAICompatibleBackend(BaseBackend):
    """OpenAI 兼容格式的 LLM 后端基类。

    子类只需实现：
    - client 属性（返回 OpenAI 兼容的 client）
    - _build_create_kwargs() 构造 API 调用参数
    - check() 模型可用性检查
    """

    # 子类可覆盖：是否需要清理 surrogate 字符
    clean_surrogates: bool = True

    @property
    def openai_client(self):
        """子类必须实现，返回 OpenAI 兼容的 client 实例"""
        raise NotImplementedError

    def _build_create_kwargs(self, messages: list, tools: list, *, stream: bool = False) -> dict:
        """构造 API 调用参数，子类可覆盖以添加额外参数"""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
        }
        if stream:
            kwargs["stream"] = True
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return kwargs

    # ── build_tools: OpenAI function 格式 ──

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

    # ── chat: 非流式调用 ──

    def chat(self, messages: list, tools: list) -> dict:
        safe_messages = self._clean(messages)

        kwargs = self._build_create_kwargs(safe_messages, tools, stream=False)
        resp = self.openai_client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        raw = json.loads(json.dumps(msg.model_dump(), default=str))
        raw = self._clean(raw)
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

    # ── chat_stream: 流式调用 ──

    def chat_stream(self, messages: list, tools: list) -> Generator[tuple[str, bool, dict | None], None, None]:
        """
        流式调用，返回 Generator[(content_delta, is_tool_call, tool_call_info)]

        OpenAI 兼容格式中，tool_calls 可能分片返回（name 和 arguments 分开），
        所以在内部累积，最后一个 chunk 统一 yield。
        """
        safe_messages = self._clean(messages)

        kwargs = self._build_create_kwargs(safe_messages, tools, stream=True)
        resp = self.openai_client.chat.completions.create(**kwargs)

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

    # ── 消息格式转换 ──

    def make_tool_call_raw_message(self, tool_calls: list, content: str = "") -> dict:
        """将流式收集的 tool_calls 转换为 OpenAI raw_message 格式"""
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

    # ── 内部工具方法 ──

    def _clean(self, o):
        """清理 surrogate 字符（递归处理 dict/list/str）"""
        if not self.clean_surrogates:
            return o
        if isinstance(o, str):
            return o.encode("utf-8", errors="replace").decode("utf-8")
        if isinstance(o, dict):
            return {k: self._clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [self._clean(i) for i in o]
        return o
