"""
记忆注入模块 - 负责向量记忆和用户画像的检索/注入/保存
"""

import logging

from memory_store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryInjector:
    """管理向量记忆和用户画像的注入、保存"""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store
        self.memory_enabled = False
        self.session_id = ""
        self.evolution = None  # 由 AgentCore 注入

    # 话题关键词常量
    TOPIC_KEYWORDS = [
        "华东", "华北", "华南", "AI 助手", "数据分析",
        "增长", "异常", "销售额", "客户管理", "智能客服",
    ]

    def inject(self, user_input: str, messages: list[dict]) -> None:
        """
        根据用户输入检索相关记忆、用户画像和待确认假设，注入到 messages[0] system prompt。

        Args:
            user_input: 用户本轮输入
            messages: 当前消息列表（会被原地修改）
        """
        additions = []

        # ── 注入向量记忆 ──
        if self.memory_enabled and self.memory_store._collection:
            count = self.memory_store._collection.count()
            if count > 0:
                related = self.memory_store.search(user_input, n_results=3)
                if related:
                    memory_lines = ["以下是相关的历史记忆（供参考）："]
                    for i, m in enumerate(related, 1):
                        ts = m["metadata"].get("timestamp", "")
                        memory_lines.append(f"  {i}. [{ts}] {m['content']}")
                    additions.append("\n".join(memory_lines))
                    logger.info("检索到 %d 条相关历史记忆", len(related))

        # ── 注入用户画像 ──
        if self.evolution and self.evolution.enabled:
            profile_text = self.evolution.get_profile_for_prompt()
            if profile_text:
                additions.append(profile_text)
                logger.info("已注入用户画像")

        # ── 注入待确认假设（让 LLM 在回复中自然提示用户） ──
        if self.evolution and self.evolution.enabled:
            hypothesis_hint = self.evolution.get_hypothesis_hint(user_input)
            if hypothesis_hint:
                prompt_instruction = (
                    "在回答完用户的问题后，请温和地追加以下提示。"
                    "不要让它干扰你的正常回答：\n"
                    + hypothesis_hint
                )
                additions.append(prompt_instruction)

        # 批量追加到 system prompt（避免多次字符串拼接）
        if additions:
            current_system = messages[0]["content"]
            messages[0] = {
                "role": "system",
                "content": current_system + "\n\n" + "\n\n".join(additions),
            }

    def save(self, messages: list[dict], turn_count: int, backend, silent: bool = False) -> None:
        """
        调用 LLM 生成对话摘要并存入向量数据库

        Args:
            messages: 当前消息列表
            turn_count: 对话轮次
            backend: LLM 后端
            silent: 是否静默
        """
        if not self.memory_enabled or not self.memory_store._collection:
            return
        if turn_count < 1:
            return

        try:
            summary_prompt = MemoryStore.build_summary_prompt(messages)
            if not summary_prompt.strip():
                return
            summary_messages = [
                {"role": "system", "content": "你是信息提取助手。只输出摘要文本，不要加任何前缀后缀。"},
                {"role": "user", "content": summary_prompt},
            ]
            result = backend.chat(summary_messages, [])
            summary = (result.get("content") or "").strip()

            if not summary or summary in ("无", "无。", "没有需要记住的信息。"):
                return

            topics = self._extract_topics(messages)
            self.memory_store.save(summary, self.session_id, topics)
        except Exception as e:
            logger.warning("记忆保存失败：%s", e)

    def _extract_topics(self, msgs: list[dict]) -> list[str]:
        """从对话中提取简单的话题标签"""
        topics = set()
        for msg in msgs:
            content = msg.get("content") or ""
            for keyword in self.TOPIC_KEYWORDS:
                if keyword in content:
                    topics.add(keyword)
        return sorted(topics)
