"""
模型后端模块 - 支持多种 LLM 后端
"""

from .base import BaseBackend
from .openai_compat import OpenAICompatibleBackend
from .qwen import QwenBackend
from .glm import GLMBackend
from .ollama import OllamaBackend

# 后端注册表
BACKENDS = {
    "qwen": QwenBackend,
    "glm": GLMBackend,
    "ollama": OllamaBackend,
}

BACKEND_LABELS = {
    "qwen": "通义千问 qwen-max（DashScope）",
    "glm": "智谱 GLM-4.5-Air（BigModel）",
    "ollama": "Ollama 本地模型（qwen3.5:35b）",
}


def get_backend(name: str):
    """获取指定名称的后端类"""
    return BACKENDS.get(name)


def get_backend_label(name: str) -> str:
    """获取后端的显示名称"""
    return BACKEND_LABELS.get(name, name)


def list_backends() -> list[str]:
    """列出所有可用的后端名称"""
    return list(BACKENDS.keys())


__all__ = [
    "BaseBackend",
    "OpenAICompatibleBackend",
    "QwenBackend",
    "GLMBackend",
    "OllamaBackend",
    "BACKENDS",
    "BACKEND_LABELS",
    "get_backend",
    "get_backend_label",
    "list_backends",
]
