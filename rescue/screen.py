"""取现场：截图 + 无障碍树 + 画面指纹 + 确定性特征。

所有识别都尽量先用确定性规则（不花模型调用），视觉只在规则给不出结论时兜底。
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import vision_ads

UPDATE_LABELS = (
    "立即更新", "立即升级", "去升级", "版本更新", "发现新版本", "升级版本",
)
DEFER_LABELS = (
    "下次再说", "下次再聊", "以后再说", "稍后再说", "暂不更新", "暂不升级",
    "下次更新", "以后更新", "取消", "关闭", "我知道了", "跳过", "不再提示",
)
PERMISSION_LABELS = ("允许", "拒绝", "仅在使用中允许", "始终允许")
CALL_HINTS = ("接听", "挂断", "来电", "通话中")
FEED_AD_HINTS = ("上滑继续观看", "继续观看短剧", "上滑查看", "广告")


@dataclass
class Screen:
    png: bytes | None
    root: ET.Element | None
    digest: str
    labels: list[str] = field(default_factory=list)
    package: str = ""
    activity: str = ""

    @property
    def ok(self) -> bool:
        return self.png is not None

    def has(self, *words: str) -> bool:
        return any(word in label for label in self.labels for word in words)

    def describe(self) -> str:
        if not self.ok and self.root is None:
            return "截图与界面树都取不到"
        return "%s/%s，节点标签 %d 个" % (self.package or "?", self.activity or "?", len(self.labels))


def capture(device_id: str, *, with_dump: bool = True) -> Screen:
    png = vision_ads._screenshot(device_id)
    root = None
    if with_dump:
        root = vision_ads._dump_ui(device_id)
    digest = hashlib.sha1(png).hexdigest() if png else ""
    if root is None:
        return Screen(png, None, digest)
    package, activity = foreground(device_id)
    return Screen(png, root, digest, _labels(root), package, activity)


def _labels(root: ET.Element) -> list[str]:
    out = []
    for node in root.iter():
        for attr in ("text", "content-desc"):
            value = node.get(attr)
            if value:
                out.append(value.strip())
    return out


def foreground(device_id: str) -> tuple[str, str]:
    """取前台包名与 Activity（只读 dumpsys）。"""
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "shell", "dumpsys", "window", "displays"],
            capture_output=True, timeout=12,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "", ""
    text = result.stdout.decode("utf-8", "replace")
    match = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([^/]+)/([^}\s]+)", text)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def signature(screen: Screen, expected_package: str = "") -> dict:
    """确定性特征。返回的 flags 里凡是 True 的，都要求零模型调用即可判定。"""
    labels = screen.labels
    joined = "|".join(labels)
    flags = {
        "update": any(word in joined for word in UPDATE_LABELS),
        "update_defer": any(word in joined for word in DEFER_LABELS),
        "permission": (
            any(word in joined for word in ("允许", "拒绝"))
            and any(word in joined for word in ("权限", "访问", "通知"))
        ),
        "rating": ("评价" in joined or "评分" in joined) and "不再提示" in joined,
        "call": any(word in joined for word in CALL_HINTS),
        "feed_ad": (
            any(word in joined for word in ("上滑继续观看", "继续观看短剧"))
            or ("广告" in joined and "上滑" in joined)
        ),
        "ad_badge": "广告" in joined,
        "app_mismatch": bool(expected_package) and bool(screen.package) and (
            screen.package != expected_package
        ),
        "blank": screen.png is None and screen.root is None,
    }
    return flags