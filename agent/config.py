"""
统一配置管理模块

支持 YAML 配置 + 环境变量覆盖：
- 优先级：环境变量 > YAML 配置 > 默认值
- API 密钥优先从 keyring 读取（安全），fallback 到 .env
- 支持配置文件热重载
"""

import os
import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# 服务标识
SERVICE_NAME = "mcp-agent"


@dataclass
class APIKeys:
    """API 密钥配置"""
    dashscope: Optional[str] = None      # 通义千问
    bigmodel: Optional[str] = None       # 智谱 GLM
    ollama_base_url: str = "http://localhost:11434"  # Ollama 地址

    @classmethod
    def load(cls) -> "APIKeys":
        """从 keyring 或环境变量加载密钥"""
        keys = cls()
        
        # 优先从 keyring 读取
        if KEYRING_AVAILABLE:
            keys.dashscope = keyring.get_password(SERVICE_NAME, "DASHSCOPE_API_KEY")
            keys.bigmodel = keyring.get_password(SERVICE_NAME, "BIGMODEL_API_KEY")
            keys.ollama_base_url = keyring.get_password(SERVICE_NAME, "OLLAMA_BASE_URL") or keys.ollama_base_url
        
        # 环境变量覆盖
        keys.dashscope = os.environ.get("DASHSCOPE_API_KEY", keys.dashscope)
        keys.bigmodel = os.environ.get("BIGMODEL_API_KEY", keys.bigmodel)
        keys.ollama_base_url = os.environ.get("OLLAMA_BASE_URL", keys.ollama_base_url)
        
        return keys
    
    @classmethod
    def save(cls, dashscope: Optional[str] = None, bigmodel: Optional[str] = None, ollama_base_url: Optional[str] = None) -> None:
        """保存密钥到 keyring（安全存储）"""
        if not KEYRING_AVAILABLE:
            print("⚠️ keyring 不可用，请使用环境变量或 .env 文件")
            return
        
        if dashscope:
            keyring.set_password(SERVICE_NAME, "DASHSCOPE_API_KEY", dashscope)
        if bigmodel:
            keyring.set_password(SERVICE_NAME, "BIGMODEL_API_KEY", bigmodel)
        if ollama_base_url:
            keyring.set_password(SERVICE_NAME, "OLLAMA_BASE_URL", ollama_base_url)
        
        print("✅ 密钥已安全保存到 keyring")


@dataclass
class DatabaseConfig:
    """数据库配置"""
    sales_db: Path = field(default_factory=lambda: Path(__file__).parent.parent / "object_db" / "sales.db")
    memory_db: Path = field(default_factory=lambda: Path(__file__).parent.parent / "object_db" / "memory_db")
    conversations_db: Path = field(default_factory=lambda: Path(__file__).parent.parent / "object_db" / "conversations.db")
    user_profile_db: Path = field(default_factory=lambda: Path(__file__).parent.parent / "object_db" / "user_profile.db")
    
    # 连接池配置
    pool_size: int = 5
    pool_timeout: int = 30
    
    @classmethod
    def from_dict(cls, data: dict) -> "DatabaseConfig":
        """从字典创建配置"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                if key.endswith("_db") and isinstance(value, str):
                    value = Path(value)
                setattr(config, key, value)
        return config


@dataclass
class MCPServerConfig:
    """MCP Server 配置"""
    retry_max_attempts: int = 3          # 最大重试次数
    retry_base_delay: float = 1.0         # 基础延迟（秒）
    retry_max_delay: float = 10.0         # 最大延迟（秒）
    timeout: float = 30.0                 # 连接超时（秒）
    
    @classmethod
    def from_dict(cls, data: dict) -> "MCPServerConfig":
        """从字典创建配置"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


@dataclass
class CacheConfig:
    """缓存配置"""
    enabled: bool = True
    ttl_seconds: int = 300               # 5分钟 TTL
    max_size: int = 1000                 # 最大缓存条目数
    
    @classmethod
    def from_dict(cls, data: dict) -> "CacheConfig":
        """从字典创建配置"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


@dataclass
class AgentConfig:
    """Agent 完整配置"""
    api_keys: APIKeys = field(default_factory=APIKeys.load)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    mcp_server: MCPServerConfig = field(default_factory=MCPServerConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    
    # 会话配置
    session_export_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "exports")
    max_history_display: int = 10
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AgentConfig":
        """加载完整配置"""
        config = cls()
        
        # 尝试加载 YAML 配置
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        
        if config_path.exists():
            try:
                import yaml
                with open(config_path, "r", encoding="utf-8") as f:
                    yaml_config = yaml.safe_load(f) or {}
                
                if "database" in yaml_config:
                    config.database = DatabaseConfig.from_dict(yaml_config["database"])
                if "mcp_server" in yaml_config:
                    config.mcp_server = MCPServerConfig.from_dict(yaml_config["mcp_server"])
                if "cache" in yaml_config:
                    config.cache = CacheConfig.from_dict(yaml_config["cache"])
                if "session" in yaml_config:
                    if "export_dir" in yaml_config["session"]:
                        config.session_export_dir = Path(yaml_config["session"]["export_dir"])
                    if "max_history_display" in yaml_config["session"]:
                        config.max_history_display = yaml_config["session"]["max_history_display"]
            except ImportError:
                print("⚠️ pyyaml 未安装，忽略 YAML 配置")
            except Exception as e:
                print(f"⚠️ 加载 YAML 配置失败：{e}")
        
        # 重新加载 API keys（环境变量可能已更新）
        config.api_keys = APIKeys.load()
        
        return config


# 全局配置实例
_config: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """获取全局配置实例（单例）"""
    global _config
    if _config is None:
        _config = AgentConfig.load()
    return _config


def reload_config(config_path: Optional[Path] = None) -> AgentConfig:
    """重新加载配置"""
    global _config
    _config = AgentConfig.load(config_path)
    return _config


def save_api_keys(dashscope: Optional[str] = None, bigmodel: Optional[str] = None, ollama_base_url: Optional[str] = None) -> None:
    """保存 API 密钥到 keyring"""
    APIKeys.save(dashscope, bigmodel, ollama_base_url)
    # 清除缓存的配置
    global _config
    _config = None
