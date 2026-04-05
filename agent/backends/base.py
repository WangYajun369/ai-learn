"""
模型后端抽象基类
"""

from abc import ABC, abstractmethod
from typing import Generator


class BaseBackend(ABC):
    """LLM 后端抽象基类，定义统一接口"""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def check(self) -> str | None:
        """
        检查模型是否可用
        
        Returns:
            返回错误信息或 None（可用）
        """
        pass

    @abstractmethod
    def build_tools(self, mcp_tools) -> list:
        """
        将 MCP 工具列表转换为后端特定的格式
        
        Args:
            mcp_tools: MCP 工具列表
            
        Returns:
            后端特定的工具定义列表
        """
        pass

    @abstractmethod
    def chat(self, messages: list, tools: list) -> dict:
        """
        非流式聊天调用
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            
        Returns:
            包含 content, tool_calls, raw_message 的字典
        """
        pass

    @abstractmethod
    def chat_stream(self, messages: list, tools: list) -> Generator[tuple[str, bool, dict | None], None, None]:
        """
        流式聊天调用
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            
        Yields:
            (content_delta, is_tool_call, tool_call_info)
        """
        pass

    @abstractmethod
    def make_tool_call_raw_message(self, tool_calls: list, content: str = "") -> dict:
        """
        将工具调用转换为后端特定的 raw_message 格式
        
        Args:
            tool_calls: 工具调用列表
            content: 内容文本
            
        Returns:
            后端特定的消息字典
        """
        pass

    @abstractmethod
    def make_tool_result_message(self, tool_call: dict, result_text: str) -> dict:
        """
        将工具调用结果转换为后端特定的消息格式
        
        Args:
            tool_call: 工具调用信息
            result_text: 工具返回结果文本
            
        Returns:
            后端特定的消息字典
        """
        pass
