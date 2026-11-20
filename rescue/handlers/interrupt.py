"""打断类弹窗：权限申请、评分引导、来电、系统提示。

优先级高于广告：这些弹窗往往盖在业务页面上，不处理脚本就看不到正文。
"""

from __future__ import annotations

from ..context import HandlerResult, RescueContext

NAME = "interrupt"
DESCRIPTION = "权限/评分/来电等打断弹窗"
SKILL = "interrupt.md"
PRIORITY = 85

REJECT_WORDS = ("拒绝", "不允许", "禁止", "稍后", "以后再说", "不再提示", "暂不", "取消", "关闭")
CALL_REJECT_WORDS = ("挂断", "拒绝接听", "拒绝", "结束通话")


def matches(flags: dict, page_type: str | None) -> bool:
    return any(flags.get(k) for k in ("permission", "rating", "call")) or page_type in (
        "权限弹窗", "评分弹窗", "来电",
    )


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    t = ctx.tools
    handled: list[str] = []
    notes: list[str] = []

    if flags.get("call"):
        if t.tap_text(CALL_REJECT_WORDS, "来电"):
            notes.append("来电已拒绝")
        else:
            notes.append("来电界面未找到挂断按钮")

    # 权限/评分/桌面图标提示都在这个统一入口里处理
    handled = t.dismiss_prompts(ctx.app or "打断弹窗")
    if handled:
        notes.append("已处理：" + "/".join(handled))

    if flags.get("rating") and not notes:
        if t.dismiss_rating(ctx.app or "评分弹窗"):
            notes.append("评分弹窗已关闭")

    if not notes:
        # 规则没命中就退回按钮文字兜底
        if t.tap_text(REJECT_WORDS, "打断弹窗兜底"):
            notes.append("按按钮文字关闭")

    ok = bool(notes) and not any("未找到" in n for n in notes)
    return HandlerResult(ok, "；".join(notes) or "无可处理的打断弹窗")