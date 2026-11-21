"""停在搜索页/搜索结果页：切分类标签、点同名联想行、重新提交搜索。

搜索类脚本常见的两种卡点：点了搜索却停在联想列表没提交；结果页分类被切到「社区」
「听书」这类没有结果的标签。脚本侧都有同样的兜底，这里作为救援链路的确定性一层，
覆盖脚本没补到的场景。判定只看「点击后页面标签集合是否变化」，不认模型自报完成。
"""

from __future__ import annotations

import time

from ..context import HandlerResult, RescueContext
from ..screen import capture

NAME = "search"
DESCRIPTION = "停在搜索页/搜索结果页（分类被切走、联想未提交）"
SKILL = "search.md"
PRIORITY = 75  # 在 ads(80) 之后、navigation(70) 之前：先原地修，退不回去再交给 navigation

TAB_LABELS = ("书籍", "剧集", "短剧", "综合")
SUGGEST_MARK = "原名"  # 搜索联想行副标题：「原名：…」/「原名【…】」；点行 = 提交搜索


def matches(flags: dict, page_type: str | None) -> bool:
    return page_type in ("搜索结果", "搜索页", "搜索联想")


def _exact(screen, wanted: str) -> str:
    """vision_ads.tap_label 只认精确文字，从现场标签里取原样字符串。"""
    for label in screen.labels:
        if label.strip() == wanted:
            return label.strip()
    return ""


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    t = ctx.tools
    if not screen.labels and screen.root is None:
        return HandlerResult(False, "搜索页读不到界面节点，无法确定性操作")

    before = tuple(sorted(screen.labels))
    before_activity = screen.activity
    plan: list[tuple[list[str], str]] = []

    # 1) 联想列表：点带「原名：…」/「原名【…】」的那一行 = 提交搜索（点搜索按钮常常不生效）
    subtitle = next((s.strip() for s in screen.labels if s.strip().startswith(SUGGEST_MARK)), "")
    if subtitle:
        plan.append(([subtitle], "点搜索联想行"))

    # 2) 分类标签被切走（社区/听书这类没有结果的分类）：切回书籍/剧集；最多试 2 个
    tabs = [label for label in TAB_LABELS if _exact(screen, label)]
    for label in tabs[:2]:
        plan.append(([label], "切到「%s」分类" % label))

    # 3) 再点一次搜索按钮
    submit = _exact(screen, "搜索")
    if submit:
        plan.append(([submit], "重新提交搜索"))

    if not plan:
        return HandlerResult(False, "搜索页没有可确定性点击的联想行/分类标签/搜索按钮")

    notes: list[str] = []
    for labels, why in plan:
        if not t.tap_text(labels, why):
            notes.append("%s 未找到可点控件" % why)
            continue
        notes.append("已%s" % why)
        time.sleep(2.0)
        fresh = capture(ctx.device_id)
        # Activity 变了也算成功：播放页/详情页首帧常常还没渲染出可读节点，
        # 只比标签会在页面切换途中误判“没变化”，接着又多点一下（11-20 真机实测）。
        moved = fresh.activity and before_activity and fresh.activity != before_activity
        if fresh.ok and (tuple(sorted(fresh.labels)) != before or moved):
            return HandlerResult(
                True,
                "；".join(notes + ["页面已切换（%s/%s）" % (fresh.package or "?", fresh.activity or "?")]),
                state_patch={"search_retry": True},
            )
    return HandlerResult(False, "；".join(notes + ["点击后页面标签未变化"]))