"""技能库：每个 handler 一份 markdown 操作手册。

进化路径（用户要的“新脚本需求能不能自己长出来”）：
1. 兜底 handler 成功救回一次现场 → 自动在 `_draft/` 落一份候选手册；
2. 人在网页上看到候选，确认后一键「提升」成正式技能；
3. 同一现场再次出现时，规则层就能命中，不再依赖模型反复试。

这里只做文件系统操作：技能即 markdown，可直接编辑、可直接 git 版本化。
"""

from __future__ import annotations

import os
import re
import time

from . import config


def _ensure() -> None:
    os.makedirs(config.SKILLS_DIR, exist_ok=True)
    os.makedirs(config.DRAFT_DIR, exist_ok=True)


def _describe(text: str) -> str:
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line[:120]
    return ""


def _collect(directory: str) -> list[dict]:
    items: list[dict] = []
    if not os.path.isdir(directory):
        return items
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(directory, name)
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        items.append({
            "name": name[:-3],
            "file": name,
            "description": _describe(text),
            "chars": len(text),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(path))),
        })
    return items


def list_skills() -> dict:
    _ensure()
    return {
        "active": _collect(config.SKILLS_DIR),
        "drafts": _collect(config.DRAFT_DIR),
    }


def load(name: str) -> str:
    for directory in (config.SKILLS_DIR, config.DRAFT_DIR):
        path = os.path.join(directory, "%s.md" % os.path.basename(name))
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                return handle.read()
    return ""


def write_draft(slug: str, body: str) -> str:
    """兜底成功时落草稿；同名草稿追加而不是覆盖。"""
    _ensure()
    safe = re.sub(r"[^0-9A-Za-z_\-一-鿿]+", "-", slug).strip("-") or "draft"
    path = os.path.join(config.DRAFT_DIR, "%s.md" % safe)
    header = ""
    if not os.path.isfile(path):
        header = "# %s\n\n" % slug
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(header + body.rstrip() + "\n\n---\n\n")
    return path


def promote(name: str) -> bool:
    _ensure()
    safe = os.path.basename(name)
    if not safe.endswith(".md"):
        safe += ".md"
    source = os.path.join(config.DRAFT_DIR, safe)
    target = os.path.join(config.SKILLS_DIR, safe)
    if not os.path.isfile(source):
        return False
    os.replace(source, target)
    return True