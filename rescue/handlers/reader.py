"""阅读器页内不推进：正文页在前台、没有弹窗，但滑动翻不动。

实测（某阅读类 App）：章末互动页（若干评论 / 上万次赞 / 数百票 +
「选择阅读口味，为你推荐专属好书」）连续 5 次左滑，正文截图哈希完全不变；
重开 App 后同一本书翻页正常。这类现场的坑在于通用 verify（前台包名 + 无阻塞弹窗）
天然成立，协调器会在派发前就判“已可继续”——所以脚本 handoff 时带上 stuck 标记，
由本 handler 用「正文区域截图哈希是否变化」做业务级验收。
"""

from __future__ import annotations

import hashlib
import struct
import time

import vision_ads

from ..context import HandlerResult, RescueContext
from ..screen import capture

NAME = "reader"
DESCRIPTION = "阅读器正文页翻不动（章末互动页/章节加载卡住）"
SKILL = "reader-stuck.md"
PRIORITY = 60

CHAPTER_END_HINTS = ("本章完", "本章结束", "选择阅读口味", "评论", "点赞", "月票")
NEXT_LABELS = ("下一章", "继续阅读", "下一章，继续阅读", "继续阅读下一章", "下一集")
BODY_TOP_RATIO = 0.11
BODY_BOTTOM_RATIO = 0.87


def matches(flags: dict, page_type: str | None) -> bool:
    return page_type == "阅读器"


def _png_size(png: bytes) -> tuple[int, int] | None:
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos = 8
    while pos + 8 <= len(png):
        length = struct.unpack(">I", png[pos:pos + 4])[0]
        chunk_type = png[pos + 4:pos + 8]
        if chunk_type == b"IHDR":
            return struct.unpack(">II", png[pos + 8:pos + 16])
        pos += 12 + length
    return None


def _body_digest(png: bytes | None) -> str:
    """正文区域哈希：排除状态栏（时钟）和底部导航，翻页才会变化。"""
    if not png:
        return ""
    size = _png_size(png)
    if size is None:
        return hashlib.sha1(png).hexdigest()
    width, height = size
    try:
        crop = vision_ads._crop_png(
            png,
            (0, int(height * BODY_TOP_RATIO), width, int(height * BODY_BOTTOM_RATIO)),
            pad_ratio=0,
        )
    except Exception:  # noqa: BLE001 裁图失败就退化为整图哈希
        crop = None
    return hashlib.sha1(crop or png).hexdigest()


def _fresh_png(device_id: str) -> bytes | None:
    return vision_ads._screenshot(device_id)


def _changed(before: str, after: str) -> bool:
    return bool(before) and bool(after) and after != before


def run(ctx: RescueContext, screen, flags: dict) -> HandlerResult:
    tools = ctx.tools
    before = _body_digest(screen.png)
    if not before:
        return HandlerResult(False, "取不到阅读器截图，无法判断正文是否变化")

    width, height = tools.screen_size()
    notes: list[str] = []
    if screen.has(*CHAPTER_END_HINTS):
        notes.append("现场有章末互动特征（评论/点赞/月票/选择阅读口味）")

    # 1) 先等章节加载/翻页动画结束，再补滑一次（最常见：下一章没加载出来）
    time.sleep(8)
    tools.swipe(int(width * 0.86), int(height * 0.50),
                int(width * 0.14), int(height * 0.50), 400, "等待章节加载后补滑一页")
    digest = _body_digest(_fresh_png(ctx.device_id))
    if _changed(before, digest):
        notes.append("补滑后正文已变化")
        tools.log("verify", "正文哈希 %s → %s" % (before[:8], digest[:8]), True)
        return HandlerResult(True, "；".join(notes),
                             {"digest_before": before[:12], "digest_after": digest[:12]})

    # 2) 章末页多为 H5/互动页，横向滑动无效：上滑查看入口，再点「下一章/继续阅读」
    tools.swipe(int(width * 0.50), int(height * 0.78),
                int(width * 0.50), int(height * 0.30), 300, "章末页上滑找下一章入口")
    time.sleep(1.5)
    if tools.tap_text(NEXT_LABELS, "点下一章/继续阅读"):
        time.sleep(1.5)
    digest = _body_digest(_fresh_png(ctx.device_id))
    if _changed(before, digest):
        notes.append("上滑并点击下一章后正文已变化")
        tools.log("verify", "正文哈希 %s → %s" % (before[:8], digest[:8]), True)
        return HandlerResult(True, "；".join(notes),
                             {"digest_before": before[:12], "digest_after": digest[:12]})

    # 3) 最后手段：点中央唤出阅读器菜单，在菜单里找「下一章」；找不到就把菜单收回去
    tools.tap(int(width * 0.50), int(height * 0.40), "点中央唤出阅读器菜单")
    time.sleep(1.0)
    if not tools.tap_text(("下一章", "下一章，继续阅读", "继续阅读下一章"), "菜单里的下一章"):
        tools.tap(int(width * 0.50), int(height * 0.40), "没有下一章，收回菜单")
    time.sleep(1.5)
    digest = _body_digest(_fresh_png(ctx.device_id))
    if _changed(before, digest):
        notes.append("菜单里点下一章后正文已变化")
        tools.log("verify", "正文哈希 %s → %s" % (before[:8], digest[:8]), True)
        return HandlerResult(True, "；".join(notes),
                             {"digest_before": before[:12], "digest_after": digest[:12]})

    notes.append("等待/上滑+下一章/菜单三组动作后正文仍未变化，交给兜底")
    tools.log("verify", "正文哈希仍是 %s" % before[:8], False)
    return HandlerResult(False, "；".join(notes), {"digest_before": before[:12]})
