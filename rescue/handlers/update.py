"""应用更新/升级弹窗：点「下次再说」类按钮，绝不去点「立即更新」。"""

from __future__ import annotations

from ..context import HandlerResult, RescueContext

NAME = "update"
DESCRIPTION = "应用更新/升级弹窗（存在「立即更新」，需要点延迟/取消）"
SKILL = "update.md"
PRIORITY = 90

DEFER_WORDS = (
    "下次再说", "下次再聊", "以后再说", "稍后再说", "暂不更新", "暂不升级",
    "下次更新", "以后更新", "取消", "关闭", "我知道了", "跳过", "不再提示",
)


def matches(flags: dict, page_type: str | None) -> bool:
    return bool(flags.get("update")) or page_type == "更新弹窗"


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    t = ctx.tools
    context = ctx.app or "更新弹窗"
    ok = t.dismiss_update(context)
    if not ok:
        # 有的机型把按钮放在 WebView 里，dump 读不到 → 视觉定位否定按钮
        ok = t.tap_text(DEFER_WORDS, "更新弹窗延迟按钮")
    evidence = "更新弹窗已关闭（延迟/取消）" if ok else "更新弹窗无可点延迟按钮"
    return HandlerResult(ok, evidence)