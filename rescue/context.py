"""救援上下文：handler 只依赖这里的字段，不直接碰 HTTP 或数据库。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .tools import Tools


@dataclass
class HandlerResult:
    ok: bool
    evidence: str = ""
    state_patch: dict = field(default_factory=dict)


@dataclass
class RescueContext:
    rescue_id: str
    device_id: str
    app: str            # 中文应用名，如「某短视频 App」
    package: str        # 包名，可空
    goal: str           # 脚本交回时描述的业务目标
    expected: str       # 期望到达的页面类型/包名；"any" 表示只需恢复可继续
    state: dict         # 脚本交回的进度快照（页码/已读时长…）
    tools: Tools
    verify: Callable[[], bool]
    rounds_left: int = 2

    def goal_line(self) -> str:
        parts = [self.app or "当前应用"]
        if self.goal:
            parts.append(self.goal)
        if self.expected and self.expected != "any":
            parts.append("目标是到达「%s」" % self.expected)
        return "，".join(parts)