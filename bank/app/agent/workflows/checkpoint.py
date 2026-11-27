"""LangGraph checkpoint 公共封装。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import MemorySaver


@lru_cache(maxsize=1)
def get_workflow_checkpointer() -> MemorySaver:
    """返回进程内共享的工作流 checkpointer。"""
    return MemorySaver()


def build_thread_config(thread_id: str) -> dict[str, dict[str, Any]]:
    """构造 LangGraph 恢复同一流程所需的 thread 配置。"""
    return {"configurable": {"thread_id": thread_id}}
