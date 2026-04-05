"""
统一日志配置

提供所有模块共享的 logger 实例和配置。
面向用户的交互输出（如 🤖 Agent 回复）仍使用 print，
这里主要处理内部诊断、调试和运维日志。
"""

import logging
import sys


def setup_logging(level: int = logging.WARNING) -> None:
    """配置全局日志格式

    Args:
        level: 日志级别，默认 WARNING。可设为 DEBUG 查看详细内部日志。
    """
    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)

    # 只配置根 logger 一次
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger

    Args:
        name: 通常用 __name__

    Returns:
        配置好的 Logger 实例
    """
    return logging.getLogger(name)
