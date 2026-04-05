"""
进化引擎模块

协调 Observer → UserProfile → Hypothesis 的完整进化流程：
1. 每轮对话后：观察 → 提取信号 → 存入画像 → 管理假设
2. 每轮对话前：注入画像 → 检查待确认假设
3. /evolve 命令：综合分析整个会话 → 批量更新画像
"""

from datetime import datetime

from .observer import Observer, Observation
from .profile import UserProfileStore
from .hypothesis import HypothesisStore


class EvolutionEngine:
    """
    Agent 自我进化引擎。

    使用方式：
        engine = EvolutionEngine()
        engine.connect()

        # 对话前：注入画像 + 检查假设提示
        profile_text = engine.get_profile_for_prompt()
        hypothesis_hint = engine.get_hypothesis_hint(user_input)

        # 对话后：观察并进化
        engine.observe_and_evolve(user_input, assistant_reply, backend)

        # /evolve 命令：综合分析
        engine.deep_evolve(messages, backend)
    """

    def __init__(self, db_path: str | None = None):
        self.profile_store = UserProfileStore(db_path) if db_path else UserProfileStore()
        self.hypothesis_store = HypothesisStore(db_path) if db_path else HypothesisStore()
        self.enabled = False
        self._evolve_count = 0  # 进化操作计数

    def connect(self, silent: bool = False) -> bool:
        """连接所有存储"""
        p_ok = self.profile_store.connect(silent=True)
        h_ok = self.hypothesis_store.connect(silent=True)
        self.enabled = p_ok and h_ok

        if not self.enabled:
            if not silent:
                print("⚠️ 进化引擎不可用（画像或假设数据库连接失败）")
            return False
        if not silent:
            p_stats = self.profile_store.get_stats()
            h_stats = self.hypothesis_store.get_stats()
            print(
                f"🧬 进化引擎已就绪"
                f"（画像 {p_stats['total_items']} 条，"
                f"假设 {h_stats['pending']} 条待确认）"
            )
        return True

    def close(self):
        self.profile_store.close()
        self.hypothesis_store.close()

    # ── 对话前：注入画像 ──

    def get_profile_for_prompt(self) -> str:
        """获取格式化的用户画像文本，用于注入 system prompt"""
        return self.profile_store.format_for_prompt()

    # ── 对话前：检查假设提示 ──

    def get_hypothesis_hint(self, user_input: str) -> str | None:
        """
        检查用户输入是否触发了待确认假设。
        返回提示文本或 None。
        """
        if not self.enabled:
            return None
        return self.hypothesis_store.format_pending_for_prompt(user_input)

    # ── 对话后：观察并进化 ──

    def observe_and_evolve(
        self,
        user_input: str,
        assistant_reply: str,
        backend,
        silent: bool = False,
    ) -> Observation:
        """
        每轮对话结束后调用：观察 → 更新画像 → 管理假设。

        Args:
            user_input: 用户本轮输入
            assistant_reply: Agent 本轮回复
            backend: LLM 后端（用于调用 LLM 分析）
            silent: 是否静默（不打印日志）

        Returns:
            观察结果 Observation
        """
        if not self.enabled:
            return Observation()

        # 1. 获取已有约束和偏好（传给 Observer 避免重复）
        existing_constraints = [
            item["content"]
            for item in self.profile_store.get_by_category("constraint")
        ]
        existing_preferences = [
            item["content"]
            for item in self.profile_store.get_by_category("preference")
        ]

        # 2. 构建 prompt 并调用 LLM 分析
        prompt = Observer.build_observation_prompt(
            user_input=user_input,
            assistant_reply=assistant_reply,
            existing_constraints=existing_constraints,
            existing_preferences=existing_preferences,
        )
        analysis_messages = [
            {
                "role": "system",
                "content": "你是对话分析专家。只输出 JSON，不要加额外说明。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            result = backend.chat(analysis_messages, [])
            llm_output = result.get("content", "")
        except Exception as e:
            if not silent:
                print(f"   ⚠️ 进化观察失败：{e}")
            return Observation()

        # 3. 解析观察结果
        observation = Observer.parse_observation(llm_output)

        if not observation.has_signals():
            return observation

        if not silent:
            print("   🧬 进化观察完成", end="")

        # 4. 更新用户画像
        source = f"自动观察（{datetime.now().strftime('%m-%d %H:%M')}）"
        saved_count = 0
        for pref in observation.preferences:
            self.profile_store.add_item("preference", pref, source=source, confidence=0.4)
            saved_count += 1

        for pattern in observation.workflow_patterns:
            self.profile_store.add_item("workflow", pattern, source=source, confidence=0.4)
            saved_count += 1

        # 5. 管理假设：遗漏的约束 → 生成假设
        for constraint in observation.missing_constraints:
            # 从约束内容中提取触发关键词
            trigger_kw = self._extract_trigger_keywords(constraint, user_input)
            self.hypothesis_store.add_hypothesis(
                hypothesis=f"用户可能需要约束：{constraint}",
                context=f"用户问「{user_input[:50]}」时未指定{constraint}",
                trigger_keywords=trigger_kw,
            )
            saved_count += 1

        if not silent and saved_count > 0:
            print(f"（画像+{saved_count}）")

        self._evolve_count += 1
        return observation

    # ── /evolve 命令：综合分析 ──

    def deep_evolve(self, messages: list[dict], backend) -> dict:
        """
        综合分析整个会话历史，批量更新用户画像。

        由 /evolve 命令触发。

        Returns:
            分析结果字典
        """
        if not self.enabled:
            return {"error": "进化引擎不可用"}

        prompt = Observer.build_evolve_prompt(messages)
        analysis_messages = [
            {
                "role": "system",
                "content": "你是用户行为分析专家。只输出 JSON，不要加额外说明。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            result = backend.chat(analysis_messages, [])
            llm_output = result.get("content", "")
        except Exception as e:
            return {"error": f"分析失败：{e}"}

        evolve_result = Observer.parse_evolve_result(llm_output)
        if not evolve_result:
            return {"error": "分析结果解析失败"}

        # 批量更新画像
        source = f"深度分析 /evolve（{datetime.now().strftime('%m-%d %H:%M')}）"
        stats = {"preferences": 0, "constraints": 0, "workflows": 0}

        for pref in evolve_result.get("preferences", []):
            self.profile_store.add_item("preference", pref, source=source, confidence=0.6)
            stats["preferences"] += 1

        for constraint in evolve_result.get("constraints", []):
            self.profile_store.add_item("constraint", constraint, source=source, confidence=0.7)
            stats["constraints"] += 1

        for workflow in evolve_result.get("workflows", []):
            self.profile_store.add_item("workflow", workflow, source=source, confidence=0.5)
            stats["workflows"] += 1

        self._evolve_count += 1
        return {
            "summary": evolve_result.get("summary", ""),
            "stats": stats,
        }

    # ── 用户确认/拒绝假设 ──

    def handle_user_confirmation(self, user_input: str) -> str | None:
        """
        处理用户对假设的确认/拒绝。

        检查用户输入是否包含对假设的确认（是/对/确认/加/好）或拒绝（否/不/取消/不需要）。

        Returns:
            处理结果文本，或 None（未检测到确认/拒绝操作）
        """
        if not self.enabled:
            return None

        pending = self.hypothesis_store.get_pending(limit=1)
        if not pending:
            return None

        # 简单的意图识别
        confirm_words = ["是", "对", "确认", "加上", "好", "可以", "是的", "没问题"]
        reject_words = ["否", "不", "取消", "不需要", "不用", "算了"]

        is_confirm = any(w in user_input for w in confirm_words)
        is_reject = any(w in user_input for w in reject_words)

        if not is_confirm and not is_reject:
            return None

        # 如果同时包含确认和拒绝词，优先按最近上下文判断
        if is_confirm and is_reject:
            # 简单策略：看哪个词出现在更前面
            first_confirm = min(
                (user_input.index(w) for w in confirm_words if w in user_input),
                default=999,
            )
            first_reject = min(
                (user_input.index(w) for w in reject_words if w in user_input),
                default=999,
            )
            if first_reject < first_confirm:
                is_confirm = False
            else:
                is_reject = False

        results = []
        for item in pending:
            if is_confirm:
                self.hypothesis_store.confirm_hypothesis(item["id"])
                # 将确认的假设转为约束存入画像
                constraint_text = item["hypothesis"].replace("用户可能需要约束：", "")
                self.profile_store.add_item(
                    "constraint",
                    constraint_text,
                    source=f"用户确认（{datetime.now().strftime('%m-%d %H:%M')}）",
                    confidence=0.9,
                )
                results.append(f"✅ 已确认并添加约束：{constraint_text}")
            elif is_reject:
                self.hypothesis_store.reject_hypothesis(item["id"])
                results.append(f"❌ 已忽略假设：{item['hypothesis']}")

        return "\n".join(results) if results else None

    # ── 获取约束列表（供 Observer 使用） ──

    def get_confirmed_constraints(self) -> list[str]:
        """获取所有已确认的约束内容"""
        return [
            item["content"]
            for item in self.profile_store.get_by_category("constraint")
        ]

    # ── 统计信息 ──

    def get_full_stats(self) -> dict:
        """获取完整的进化统计"""
        return {
            "profile": self.profile_store.get_stats(),
            "hypotheses": self.hypothesis_store.get_stats(),
            "evolve_count": self._evolve_count,
        }

    # ── 内部方法 ──

    @staticmethod
    def _extract_trigger_keywords(constraint: str, user_input: str) -> list[str]:
        """从约束描述和用户输入中提取触发关键词"""
        keywords = []

        # 从约束内容提取有意义的词
        for phrase in ["时间", "区域", "产品", "月份", "季度", "年份", "维度", "范围"]:
            if phrase in constraint:
                keywords.append(phrase)

        # 从用户输入提取核心词（去除常见停用词）
        stop_words = {"的", "了", "吗", "呢", "吧", "啊", "什么", "怎么", "怎么", "帮我"}
        for word in user_input[:50]:
            if len(word) >= 2 and word not in stop_words:
                keywords.append(word)

        # 去重并限制数量
        seen = set()
        unique_kw = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_kw.append(kw)
        return unique_kw[:8]
