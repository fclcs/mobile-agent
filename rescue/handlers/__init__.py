"""处理器注册表：确定性规则先分流，视觉判定补充，最后统一兜底。

新接入一个应用/一种新故障 = 新增一个 handler 文件 + 一条 skills/*.md，
不需要改协调器；也允许运行时把 _draft 里的草稿技能一键提升。
"""

from __future__ import annotations

from . import ads, interrupt, navigation, reader, unknown, update

HANDLERS = sorted(
    (update, interrupt, ads, navigation, reader, unknown),
    key=lambda module: module.PRIORITY,
    reverse=True,
)


def candidates(flags: dict, page_type: str | None) -> list:
    """按优先级返回所有命中的处理器，末位永远是 unknown 兜底。"""
    hits = []
    for module in HANDLERS:
        try:
            if module.matches(flags, page_type):
                hits.append(module)
        except Exception:  # noqa: BLE001  单个 handler 的判定失败不影响兜底
            continue
    return hits or [unknown]


def pick(flags: dict, page_type: str | None):
    return candidates(flags, page_type)[0]


def by_name(name: str):
    for module in HANDLERS:
        if module.NAME == name:
            return module
    return None