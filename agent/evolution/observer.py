"""
对话观察器模块

每轮对话结束后，分析用户行为并提取三类信号：
- preferences：用户偏好
- missing_constraints：用户遗漏的约束
- workflow_patterns：工作流模式

观察结果返回结构化数据，供 EvolutionEngine 处理。
"""

import json


class Observation:
    """单次观察结果"""

    def __init__(
        self,
        preferences: list[str] | None = None,
        missing_constraints: list[str] | None = None,
        workflow_patterns: list[str] | None = None,
        summary: str = "",
    ):
        self.preferences = preferences or []
        self.missing_constraints = missing_constraints or []
        self.workflow_patterns = workflow_patterns or []
        self.summary = summary

    def has_signals(self) -> bool:
        return bool(self.preferences or self.missing_constraints or self.workflow_patterns)

    def to_dict(self) -> dict:
        return {
            "preferences": self.preferences,
            "missing_constraints": self.missing_constraints,
            "workflow_patterns": self.workflow_patterns,
            "summary": self.summary,
        }


class Observer:
    """
    对话观察器。

    通过 LLM 分析每轮对话，提取用户行为信号。
    """

    @staticmethod
    def build_observation_prompt(
        user_input: str,
        assistant_reply: str,
        existing_constraints: list[str] | None = None,
        existing_preferences: list[str] | None = None,
    ) -> str:
        """
        构建让 LLM 分析对话的 prompt。

        Args:
            user_input: 用户本轮输入
            assistant_reply: Agent 本轮回复
            existing_constraints: 已有约束列表（避免重复提示）
            existing_preferences: 已有偏好列表（避免重复发现）

        Returns:
            发给 LLM 的 prompt 字符串
        """
        constraints_hint = ""
        if existing_constraints:
            constraints_hint = (
                "\n\n当前已确认的用户约束（不要重复提出）：\n"
                + "\n".join(f"  - {c}" for c in existing_constraints)
            )

        preferences_hint = ""
        if existing_preferences:
            preferences_hint = (
                "\n\n当前已知的用户偏好（不要重复发现）：\n"
                + "\n".join(f"  - {p}" for p in existing_preferences)
            )

        return (
            "你是一个对话分析专家。请分析以下一轮用户-Agent 对话，提取三类信号。\n\n"
            "## 三类信号\n\n"
            "### 1. preferences（用户偏好）\n"
            "用户展现出什么样的偏好？例如：\n"
            '  - "按区域分析" → 偏好区域维度\n'
            '  - "看环比增长" → 偏好增长率指标\n'
            '  - "用表格展示" → 偏好表格格式\n'
            "仅输出确凿的信号，不要猜测。\n\n"
            "### 2. missing_constraints（遗漏的约束）\n"
            "用户的提问中明显缺少哪些约束条件？例如：\n"
            '  - 查销售数据但没说时间范围\n'
            '  - 查产品数据但没指定哪个产品\n'
            '  - 做比较分析但没说明比较维度\n'
            "仅列出 1-3 条最明显的遗漏，不要过度发散。\n"
            "如果用户的问题已经足够明确，返回空列表。\n\n"
            "### 3. workflow_patterns（工作流模式）\n"
            "用户的提问顺序是否展现出规律性的工作流？例如：\n"
            '  - "先看总览，再按区域拆分" → 总览→拆分的工作流\n'
            "仅在有明确模式时才输出。\n\n"
            f"{constraints_hint}{preferences_hint}\n\n"
            "## 对话内容\n\n"
            f"用户：{user_input[:1000]}\n\n"
            f"Agent：{assistant_reply[:1000]}\n\n"
            "## 输出格式\n\n"
            "请严格按以下 JSON 格式输出，不要加额外说明：\n"
            "{\n"
            '  "preferences": ["偏好1", "偏好2"],\n'
            '  "missing_constraints": ["遗漏的约束1", "遗漏的约束2"],\n'
            '  "workflow_patterns": ["工作流模式1"],\n'
            '  "summary": "一句话总结这轮对话的核心"\n'
            "}\n\n"
            "注意：\n"
            "- 如果某个类别没有信号，返回空列表 []\n"
            "- missing_constraints 只在用户确实遗漏时才填写\n"
            "- 不要输出已存在的约束或偏好\n"
            "- summary 控制在 30 字以内"
        )

    @staticmethod
    def parse_observation(llm_output: str) -> Observation:
        """
        解析 LLM 输出为 Observation 对象。

        容错处理：如果 LLM 输出不是合法 JSON，尝试提取 JSON 块。
        """
        text = llm_output.strip()

        # 尝试提取 JSON（可能被 markdown 代码块包裹）
        if "```" in text:
            # 提取 ```json ... ``` 或 ``` ... ``` 块
            import re
            json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            if json_match:
                text = json_match.group(1).strip()

        # 去掉可能的前缀（找到第一个出现的 JSON 起始字符并截断）
        first_json_char = min(
            (i for i, c in enumerate(text) if c in "{["),
            default=0,
        )
        if first_json_char > 0:
            text = text[first_json_char:]

        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return Observation()

            return Observation(
                preferences=_ensure_list(data.get("preferences")),
                missing_constraints=_ensure_list(data.get("missing_constraints")),
                workflow_patterns=_ensure_list(data.get("workflow_patterns")),
                summary=str(data.get("summary", "")),
            )
        except (json.JSONDecodeError, TypeError):
            return Observation()

    @staticmethod
    def build_evolve_prompt(messages: list[dict]) -> str:
        """
        构建 /evolve 命令的综合分析 prompt。
        基于整个会话历史进行深度分析。
        """
        conversation_lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system" or not content.strip():
                continue
            content = content.strip()[:800]
            if role == "user":
                conversation_lines.append(f"用户：{content}")
            elif role == "assistant":
                conversation_lines.append(f"助手：{content[:500]}")

        conversation_text = "\n".join(conversation_lines)

        return (
            "你是一个用户行为分析专家。请基于以下完整对话历史，深度分析用户画像。\n\n"
            "## 分析维度\n\n"
            "### 1. preferences（偏好习惯）\n"
            "用户有哪些明显的偏好？例如分析维度、关注指标、输出格式、交互方式等。\n"
            "列出所有能确实验证的偏好。\n\n"
            "### 2. constraints（确认的约束）\n"
            "用户在对话中明确表达的约束条件有哪些？\n"
            "例如默认时间范围、关注的区域/产品、数据粒度要求等。\n\n"
            "### 3. workflows（工作流模式）\n"
            "用户的提问顺序是否展现出规律性的工作流程？\n"
            "归纳用户的典型工作步骤。\n\n"
            "## 对话历史\n\n"
            f"{conversation_text}\n\n"
            "## 输出格式\n\n"
            "请严格按以下 JSON 格式输出：\n"
            "{\n"
            '  "preferences": ["偏好1", "偏好2", ...],\n'
            '  "constraints": ["约束1", "约束2", ...],\n'
            '  "workflows": ["工作流1", "工作流2", ...],\n'
            '  "summary": "对用户工作模式和关注点的整体总结（50字以内）"\n'
            "}\n\n"
            "要求：\n"
            "- 每个列表至少 0 项，至多 8 项\n"
            "- 每项简洁明确（10-20字）\n"
            "- 只输出有把握的结论，不猜测\n"
            "- 不要加额外说明，只输出 JSON"
        )

    @staticmethod
    def parse_evolve_result(llm_output: str) -> dict:
        """解析 /evolve 的综合分析结果"""
        text = llm_output.strip()

        if "```" in text:
            import re
            json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            if json_match:
                text = json_match.group(1).strip()

        first_json_char = min(
            (i for i, c in enumerate(text) if c in "{["),
            default=0,
        )
        if first_json_char > 0:
            text = text[first_json_char:]

        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return {}
            return {
                "preferences": _ensure_list(data.get("preferences")),
                "constraints": _ensure_list(data.get("constraints")),
                "workflows": _ensure_list(data.get("workflows")),
                "summary": str(data.get("summary", "")),
            }
        except (json.JSONDecodeError, TypeError):
            return {}


def _ensure_list(value) -> list[str]:
    """确保返回字符串列表"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item and str(item).strip()]
    return []
