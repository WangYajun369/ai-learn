"""
智谱 GLM 后端 - zai-sdk（OpenAI 兼容）
"""

import os

from .openai_compat import OpenAICompatibleBackend


class GLMBackend(OpenAICompatibleBackend):
    """智谱 GLM-4.5-Air，使用 zai-sdk（OpenAI 兼容格式）"""

    clean_surrogates = True

    def __init__(self, model: str = "glm-4.5-air"):
        super().__init__(model)
        self._client = None

    @property
    def openai_client(self):
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
            self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
            )
        except Exception as e:
            return f"连接失败：{e}"
        return None
