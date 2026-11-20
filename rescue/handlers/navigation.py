"""跑错页面：前台不是目标 App，或停在搜索页/首页/某个子页。

先尽量「退」回去：返回键 → 重新拉起目标 App。拉起会重置业务页面，
所以放在最后，且只在拿到包名时才做。
"""

from __future__ import annotations

from ..context import HandlerResult, RescueContext
from ..screen import capture

NAME = "navigation"
DESCRIPTION = "前台不在目标页面（子页/搜索页/桌面/其他 App）"
SKILL = "navigation.md"
PRIORITY = 70


def matches(flags: dict, page_type: str | None) -> bool:
    return bool(flags.get("app_mismatch")) or page_type in (
        "搜索结果", "首页", "桌面", "列表页", "其他",
    )


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    t = ctx.tools
    notes: list[str] = []

    t.back(1)
    notes.append("已按返回键")
    fresh = capture(ctx.device_id)
    if ctx.package and fresh.package == ctx.package:
        return HandlerResult(True, "；".join(notes + ["已回到目标应用 %s" % ctx.package]))

    t.back(1)
    fresh = capture(ctx.device_id)
    if ctx.package and fresh.package == ctx.package:
        return HandlerResult(True, "；".join(notes + ["返回键 ×2 后回到目标应用"]))

    if ctx.package:
        t.launch(ctx.package)
        fresh = capture(ctx.device_id)
        if fresh.package == ctx.package:
            return HandlerResult(
                True, "；".join(notes + ["重新拉起 %s 成功" % ctx.package]),
                state_patch={"relaunched": True},
            )
        return HandlerResult(False, "重新拉起 %s 后前台仍是 %s" % (ctx.package, fresh.package or "?"))

    return HandlerResult(bool(notes), "；".join(notes) or "未识别出需要导航到的页面")