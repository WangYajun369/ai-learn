"""
Agent 模块 - MCP + Skills 销售分析 Agent 核心实现

增强功能：
- MCP 连接重试机制（agent/retry.py）
- 数据库连接池（agent/db_pool.py）
- 工具调用缓存（agent/cache.py）
- 统一配置管理（agent/config.py）
"""

from .skill_loader import SkillLoader
from .core import AgentCore
from .backends import QwenBackend, GLMBackend, OllamaBackend, get_backend
from .config import get_config, save_api_keys, AgentConfig
from .cache import get_tool_cache, clear_tool_cache
from .db_pool import get_db_pool, close_db_pool

__all__ = [
    "SkillLoader",
    "AgentCore",
    "QwenBackend",
    "GLMBackend",
    "OllamaBackend",
    "get_backend",
    "get_config",
    "save_api_keys",
    "AgentConfig",
    "get_tool_cache",
    "clear_tool_cache",
    "get_db_pool",
    "close_db_pool",
]
