"""
Ollama 本地模型后端 - OpenAI 兼容接口
"""

from .openai_compat import OpenAICompatibleBackend


class OllamaBackend(OpenAICompatibleBackend):
    """Ollama 本地模型，使用 OpenAI 兼容接口（tools / tool_calls 格式）"""

    clean_surrogates = False

    def __init__(self, model: str = "qwen3.5:35b"):
        super().__init__(model)
        from openai import OpenAI
        self._client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # Ollama 不需要真实 key
        )

    @property
    def openai_client(self):
        return self._client

    def check(self) -> str | None:
        """检查 Ollama 服务是否运行且模型可用"""
        try:
            self.openai_client.chat.completions.create(
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
