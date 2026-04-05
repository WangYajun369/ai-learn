"""
MCP 连接重试模块

提供：
- 指数退避重试机制
- 连接健康检查
- 自动重连
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from .config import get_config

T = TypeVar("T")


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass 
class MCPRetryConfig(RetryConfig):
    """MCP 专用重试配置"""
    retryable_errors: tuple = (
        "Connection refused",
        "Connection reset",
        "Timeout",
        "Temporary failure",
    )
    
    @classmethod
    def from_config(cls) -> "MCPRetryConfig":
        cfg = get_config()
        return cls(
            max_attempts=cfg.mcp_server.retry_max_attempts,
            base_delay=cfg.mcp_server.retry_base_delay,
            max_delay=cfg.mcp_server.retry_max_delay,
        )


class RetryError(Exception):
    """重试耗尽异常"""
    def __init__(self, message: str, attempts: int, last_error: Exception):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """计算延迟时间（指数退避 + 抖动）"""
    import random
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    delay = min(delay, config.max_delay)
    if config.jitter:
        delay += random.uniform(-delay * 0.25, delay * 0.25)
    return max(0, delay)


async def retry_async(
    func: Callable[..., T],
    config: Optional[RetryConfig] = None,
    retry_on: Optional[Callable[[Exception], bool]] = None,
    *args,
    **kwargs,
) -> T:
    """异步重试函数"""
    if config is None:
        config = RetryConfig()
    
    last_error: Optional[Exception] = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            last_error = e
            should_retry = False
            
            if retry_on:
                should_retry = retry_on(e)
            elif attempt < config.max_attempts:
                error_msg = str(e)
                for pattern in getattr(config, "retryable_errors", []):
                    if pattern.lower() in error_msg.lower():
                        should_retry = True
                        break
            
            if not should_retry or attempt == config.max_attempts:
                raise RetryError(
                    f"重试耗尽（{attempt}/{config.max_attempts}）：{e}",
                    attempts=attempt,
                    last_error=e,
                ) from e
            
            delay = calculate_delay(attempt, config)
            await asyncio.sleep(delay)
    
    raise RetryError(f"重试耗尽：{last_error}", attempts=config.max_attempts, last_error=last_error or Exception("Unknown"))


def retry_sync(
    func: Callable[..., T],
    config: Optional[RetryConfig] = None,
    retry_on: Optional[Callable[[Exception], bool]] = None,
    *args,
    **kwargs,
) -> T:
    """同步重试函数"""
    if config is None:
        config = RetryConfig()
    
    last_error: Optional[Exception] = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            should_retry = False
            
            if retry_on:
                should_retry = retry_on(e)
            elif attempt < config.max_attempts:
                error_msg = str(e)
                for pattern in getattr(config, "retryable_errors", []):
                    if pattern.lower() in error_msg.lower():
                        should_retry = True
                        break
            
            if not should_retry or attempt == config.max_attempts:
                raise RetryError(
                    f"重试耗尽（{attempt}/{config.max_attempts}）：{e}",
                    attempts=attempt,
                    last_error=e,
                ) from e
            
            delay = calculate_delay(attempt, config)
            time.sleep(delay)
    
    raise RetryError(f"重试耗尽：{last_error}", attempts=config.max_attempts, last_error=last_error or Exception("Unknown"))


class MCPSessionManager:
    """MCP 会话管理器（带重试机制）"""
    
    def __init__(self, config: Optional[MCPRetryConfig] = None):
        self._config = config or MCPRetryConfig.from_config()
        self._session = None
        self._connected = False
        self._last_health_check = 0.0
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None
    
    async def connect_with_retry(self, connect_func) -> Any:
        """带重试的连接

        connect_func 应返回 (session, resource_stack) 元组，
        其中 session 是 ClientSession，resource_stack 是生命周期管理对象。
        本方法将 session 存入 self._session 以供 call_tool_with_retry 使用，
        同时将完整元组返回给调用方。
        """
        result = await retry_async(connect_func, config=self._config)
        # connect_func 返回 (session, ...) 元组，只取 session 存入
        self._session = result[0] if isinstance(result, tuple) else result
        self._connected = True
        self._last_health_check = time.time()
        return result
    
    async def call_tool_with_retry(self, tool_name: str, arguments: dict) -> Any:
        """带重试的工具调用"""
        if not self.is_connected:
            raise ConnectionError("MCP 会话未连接")
        
        async def _call():
            return await self._session.call_tool(tool_name, arguments)
        
        return await retry_async(_call, config=self._config)
    
    async def disconnect(self) -> None:
        """断开连接"""
        self._session = None
        self._connected = False


_global_mcp_manager: Optional[MCPSessionManager] = None


def get_mcp_manager() -> MCPSessionManager:
    """获取全局 MCP 会话管理器"""
    global _global_mcp_manager
    if _global_mcp_manager is None:
        _global_mcp_manager = MCPSessionManager()
    return _global_mcp_manager
