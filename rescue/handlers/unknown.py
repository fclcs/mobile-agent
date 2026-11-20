"""兜底：确定性规则和页面词表都给不出结论时，交给平台现有的 PhoneAgent 接管。

与脚本里的 B 档完全同一套：动作白名单 + 业务验收才算成功。
"""

from __future__ import annotations

from ..context import HandlerResult, RescueContext

NAME = "unknown"
DESCRIPTION = "未归类的现场，交给 PhoneAgent 接管"
SKILL = "unknown.md"
PRIORITY = 10


def matches(flags: dict, page_type: str | None) -> bool:
    return True


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    ok = ctx.tools.mobile_agent(ctx.goal_line(), ctx.verify)
    return HandlerResult(ok, "PhoneAgent 接管%s" % ("成功" if ok else "未通过业务验收"))