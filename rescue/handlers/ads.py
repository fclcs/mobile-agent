"""广告类现场：整屏推广、开屏广告、feed 内嵌品牌视频条。

短视频类 App 的 feed 广告没有关闭按钮，判据是右上「广告」角标 + 底部「上滑继续观看」，
正确动作是上划跳过，不是点 X、也不是返回键（R7）。
"""

from __future__ import annotations

from ..context import HandlerResult, RescueContext

NAME = "ads"
DESCRIPTION = "整屏广告 / 开屏广告 / feed 内嵌广告"
SKILL = "ads.md"
PRIORITY = 80

FEED_HINTS = ("上滑继续观看", "继续观看短剧", "上滑查看")


def matches(flags: dict, page_type: str | None) -> bool:
    return bool(flags.get("feed_ad") or flags.get("ad_badge")) or page_type in (
        "广告", "开屏广告", "整屏广告", "推广页",
    )


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    t = ctx.tools
    context = ctx.app or "广告"
    labels = "|".join(screen.labels) if screen.labels else ""

    if flags.get("feed_ad") or any(h in labels for h in FEED_HINTS):
        width, height = t.screen_size()
        x = width // 2
        for _ in range(2):
            t.swipe(x, int(height * 0.78), x, int(height * 0.22), 300, "feed 广告上划跳过")
        return HandlerResult(True, "feed 内嵌广告已上划跳过")

    if t.try_close(context, confirm=True):
        return HandlerResult(True, "广告已点关闭")

    # 整屏互推广告（App 内 WebView）通常没有关闭控件，返回键是唯一出路
    t.back(2)
    return HandlerResult(True, "无关闭控件，已按返回键 ×2")