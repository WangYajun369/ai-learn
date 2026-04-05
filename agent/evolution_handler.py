"""
进化处理器 - 封装所有进化引擎相关的命令处理方法
"""

import logging

from agent.evolution.engine import EvolutionEngine

logger = logging.getLogger(__name__)


class EvolutionHandler:
    """处理 /evolve、/profile、/hypothesis 等进化命令"""

    def __init__(self, engine: EvolutionEngine):
        self.engine = engine

    @property
    def enabled(self) -> bool:
        return self.engine and self.engine.enabled

    def handle_evolve(self, messages: list[dict], turn_count: int, backend) -> None:
        """处理 /evolve 命令：综合分析会话，更新用户画像"""
        if not self.enabled:
            print("⚠️ 进化引擎不可用")
            return
        if turn_count < 2:
            print("💡 对话轮次太少（至少需要 2 轮），暂无法进行深度分析")
            return

        print("\n🧬 正在深度分析对话历史，归纳用户画像...", flush=True)
        result = self.engine.deep_evolve(messages, backend)

        if "error" in result:
            print(f"⚠️ 分析失败：{result['error']}")
            return

        stats = result.get("stats", {})
        print(f"\n🧬 分析完成！")
        print(f"   📌 总结：{result.get('summary', '无')}")
        print(f"   🏷️ 新增偏好：{stats.get('preferences', 0)} 条")
        print(f"   📐 新增约束：{stats.get('constraints', 0)} 条")
        print(f"   🔄 新增工作流：{stats.get('workflows', 0)} 条")

        print(self.engine.profile_store.format_for_display())

    def handle_show_profile(self) -> None:
        """处理 /profile 命令"""
        if not self.enabled:
            print("⚠️ 进化引擎不可用")
            return
        print("\n🧬 当前用户画像：")
        print("═" * 60)
        print(self.engine.profile_store.format_for_display())
        print("═" * 60)

    def handle_clear_profile(self) -> None:
        """处理 /profile clear 命令"""
        if not self.enabled:
            print("⚠️ 进化引擎不可用")
            return
        count = self.engine.profile_store.clear_all()
        print(f"\n🧬 已清空 {count} 条画像数据")

    def handle_show_hypotheses(self) -> None:
        """处理 /hypothesis 命令"""
        if not self.enabled:
            print("⚠️ 进化引擎不可用")
            return
        print("\n💡 假设队列：")
        print("═" * 60)
        print(self.engine.hypothesis_store.format_for_display())
        print("═" * 60)
        print("\n提示：对假设提示回复「是」确认，回复「否」拒绝")

    def handle_clear_hypotheses(self) -> None:
        """处理 /hypothesis clear 命令"""
        if not self.enabled:
            print("⚠️ 进化引擎不可用")
            return
        all_pending = self.engine.hypothesis_store.get_pending(limit=100)
        for item in all_pending:
            self.engine.hypothesis_store.reject_hypothesis(item["id"])
        print(f"\n💡 已清空 {len(all_pending)} 条待确认假设")

    def check_confirmation(self, user_input: str) -> str | None:
        """检查用户对假设的确认/拒绝，返回结果文本或 None"""
        if not self.enabled:
            return None
        return self.engine.handle_user_confirmation(user_input)

    def get_hypothesis_hint(self, user_input: str) -> str | None:
        """获取待确认假设提示"""
        if not self.enabled:
            return None
        return self.engine.get_hypothesis_hint(user_input)

    def background_observe(self, user_input: str, assistant_reply: str, backend) -> None:
        """后台执行进化观察"""
        try:
            self.engine.observe_and_evolve(
                user_input=user_input,
                assistant_reply=assistant_reply,
                backend=backend,
                silent=True,
            )
        except Exception as e:
            logger.warning("进化观察异常：%s", e)
