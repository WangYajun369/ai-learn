#!/usr/bin/env python3
"""
MCP Agent 入口文件

MCP + Skills 销售分析 Agent。演示如何通过 MCP 工具 + Skills 技能包
构建具备"专家级分析能力"的 AI 助手。

用法：
    uv run agent.py          # 启动 Agent（交互式选择模型，默认 REPL 模式）
    uv run agent.py --tui    # 启动 Agent（TUI 界面）
"""

import asyncio
import sys

import pick
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

from agent import SkillLoader, AgentCore
from agent.backends import BACKENDS, BACKEND_LABELS, get_backend
from memory_store import MemoryStore
from conversation_store import ConversationStore


def select_backend() -> str | None:
    """
    交互式选择模型后端
    
    Returns:
        选择的后端名称，或 None（退出）
    """
    keys = list(BACKENDS.keys())
    options = [pick.Option(BACKEND_LABELS[k], k) for k in keys]
    options.append(pick.Option("退出程序", "__quit__"))

    try:
        while True:
            title = "🤖 请选择大模型后端（↑↓ 移动，Enter 确认）："
            selected, _ = pick.pick(options, title, indicator="❯")
            backend_arg = selected.value

            if backend_arg == "__quit__":
                print("\033c", end="", flush=True)
                return None

            # 清屏并显示验证信息
            print("\033c", end="", flush=True)
            label = BACKEND_LABELS[backend_arg]
            print(f"\n🔍 正在检查 {label} ...")

            backend_class = get_backend(backend_arg)
            backend = backend_class()
            err = backend.check()

            if err:
                print(f"❌ 模型不可用：{err}")
                from prompt_toolkit import prompt as pt_prompt
                pt_prompt("\n按 Enter 键重新选择...")
                print("\033c", end="", flush=True)  # 清屏后重新显示选择
                continue

            print(f"✅ {label} — 当前模型可用")
            return backend_arg

    except KeyboardInterrupt:
        print("\n👋 再见！")
        return None


def main():
    """主入口函数"""
    # 检查是否有 --tui 参数
    if "--tui" in sys.argv:
        # TUI 模式（如果需要可以在这里实现）
        print("TUI 模式暂未实现，使用 REPL 模式")

    # 选择后端
    backend_name = select_backend()
    if backend_name is None:
        print("\n👋 再见！")
        sys.exit(0)

    # 创建后端实例
    backend_class = get_backend(backend_name)
    backend = backend_class()

    # 创建依赖组件
    skill_loader = SkillLoader()
    memory_store = MemoryStore()
    conv_store = ConversationStore()

    # 创建 Agent 核心
    agent = AgentCore(
        backend=backend,
        skill_loader=skill_loader,
        memory_store=memory_store,
        conv_store=conv_store,
    )

    # 运行 Agent
    asyncio.run(agent.run(backend_name))


if __name__ == "__main__":
    main()
