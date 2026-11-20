"""协调器：一次救援 = 取现场 → 确定性分类 → 分流 handler → 业务验收 → 落记录。

设计约束（来自脚本侧的现实）：
- 脚本进程还活着、步骤还停在 executing，所以这里只负责“把现场修回可继续”，
  不负责重跑步骤，也不改脚本的计数器；修好之后脚本自己的 verify() 仍说了算。
- 同一台手机同时只允许一次救援（per-device 锁），避免两路 adb 输入互相打架。
"""

from __future__ import annotations

import os
import threading
import time

from . import config, screen as screen_mod, store
from .context import RescueContext
from .handlers import candidates
from .skills import write_draft
from .tools import BudgetExceeded, Tools

BLOCKING_FLAGS = ("update", "permission", "rating", "call", "feed_ad", "ad_badge", "app_mismatch")

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(device_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(device_id, threading.Lock())


def _save_screenshot(rescue_id: str, png: bytes | None, tag: str) -> str:
    if not png:
        return ""
    directory = os.path.join(config.SCREENSHOT_DIR, rescue_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "%s_%s.png" % (str(int(time.time() * 1000)), tag))
    try:
        with open(path, "wb") as handle:
            handle.write(png)
    except OSError:
        return ""
    return os.path.relpath(path, config.SCREENSHOT_DIR)


def _blocked(flags: dict) -> bool:
    return any(flags.get(name) for name in BLOCKING_FLAGS)


def _verify_maker(device_id: str, expected: str, package: str):
    """业务验收：现场干净 + 前台回到目标包（expected 形如 "pkg:com.xxx" 时也校验）。

    视觉词表验收要花模型调用，不进 verify；脚本自己的 verify() 仍是最终裁判。
    """
    want = package
    if expected.startswith("pkg:"):
        want = expected[4:].strip() or package

    def verify() -> bool:
        fresh = screen_mod.capture(device_id)
        flags = screen_mod.signature(fresh, want)
        if _blocked(flags):
            return False
        if want and fresh.package:
            return fresh.package == want
        return True

    return verify


def _draft_from(req: dict, screen, flags: dict, evidence: str) -> None:
    lines = [
        "- 记录时间：%s" % store.now(),
        "- 应用：%s（%s）" % (req.get("app") or "?", req.get("package") or "?"),
        "- 现场特征：%s" % ("，".join(k for k, v in flags.items() if v) or "无"),
        "- 可见文字：%s" % ("、".join(dict.fromkeys(screen.labels))[:400] or "（dump 失败）"),
        "- 成功动作：%s" % evidence,
        "",
        "判据：再次出现同样特征时，确定性规则应直接命中，不必再交给模型。",
    ]
    slug = "%s-%s" % (req.get("app") or "unknown", time.strftime("%m%d-%H%M"))
    write_draft(slug, "\n".join(lines))


def rescue(req: dict) -> dict:
    settings = store.load_settings()
    settings.apply_env()
    if not settings.enabled:
        return {"status": "disabled", "resolved": False, "detail": "救援未启用"}

    device_id = (req.get("device_id") or "").strip()
    if not device_id:
        return {"status": "error", "resolved": False, "detail": "缺少 device_id"}

    rescue_id = store.create_run(req)
    started = time.monotonic()
    deadline = started + max(30, int(settings.max_seconds))
    tools = Tools(device_id, rescue_id, deadline, settings.max_vision_calls, config.MAX_TOOL_CALLS)
    verify = _verify_maker(device_id, req.get("expected") or "any", req.get("package") or "")
    ctx = RescueContext(
        rescue_id=rescue_id,
        device_id=device_id,
        app=req.get("app") or "",
        package=req.get("package") or "",
        goal=req.get("goal") or "",
        expected=req.get("expected") or "any",
        state=req.get("state") or {},
        tools=tools,
        verify=verify,
    )

    lock = _lock_for(device_id)
    if not lock.acquire(timeout=max(5, int(tools.time_left()))):
        tools.log("lock", "该设备已有救援在进行，放弃", False)
        store.finish_run(rescue_id, "busy", False, error="device busy")
        return {"rescue_id": rescue_id, "status": "busy", "resolved": False}

    used: list[str] = []
    patch: dict = {}
    evidence = ""
    handler_name = ""
    try:
        for round_no in (1, 2):
            screen = screen_mod.capture(device_id)
            flags = screen_mod.signature(screen, req.get("package") or "")
            shot = _save_screenshot(rescue_id, screen.png, "r%d_现场" % round_no)
            tools.log("observe", "第 %d 轮现场：%s；特征 %s" % (
                round_no, screen.describe(), "/".join(k for k, v in flags.items() if v) or "无",
            ), None, shot or None)

            page_type = None
            if screen.png:
                page_type = tools.identify(
                    screen.png, ("广告", "更新弹窗", "权限弹窗", "评分弹窗", "来电",
                                 "搜索结果", "首页", "桌面", "播放页", "阅读器", "其他"),
                    "第 %d 轮页面判定" % round_no,
                )

            # 第二轮换一个处理器，避免在同一动作上空转
            hits = candidates(flags, page_type)
            module = next((m for m in hits if m.NAME not in used), hits[-1])
            used.append(module.NAME)
            tools.log("dispatch", "分发给 %s（%s）" % (module.NAME, module.DESCRIPTION))

            # 脚本 handoff 带 stuck 标记时不能提前放行：这类现场“前台正确 + 无弹窗”
            # 天然满足通用 verify，但业务动作其实卡住了（如阅读器章末页翻不动）。
            if not _blocked(flags) and verify() and not req.get("stuck"):
                evidence = "进入救援时现场已可继续，无需动作"
                handler_name = module.NAME
                store.finish_run(rescue_id, "resolved", True, handler_name, evidence, patch)
                return _result(rescue_id, "resolved", True, evidence, patch, tools, started)

            try:
                outcome = module.run(ctx, screen, flags)
            except BudgetExceeded:
                raise
            except Exception as exc:  # noqa: BLE001  handler 崩溃不能连累脚本
                tools.log("handler", "%s 异常：%s: %s" % (
                    module.NAME, type(exc).__name__, exc), False)
                continue

            if outcome.state_patch:
                patch.update(outcome.state_patch)
            tools.log("handler", "%s → %s" % (module.NAME, outcome.evidence), outcome.ok)
            evidence = outcome.evidence
            handler_name = module.NAME

            time.sleep(1.0)
            if outcome.ok and verify():
                shot_after = screen_mod.capture(device_id)
                after_path = _save_screenshot(rescue_id, shot_after.png, "r%d_恢复" % round_no)
                tools.log("verify", "业务验收通过（%s）" % module.NAME, True, after_path or None)
                if module.NAME == "unknown":
                    _draft_from(req, screen, flags, evidence)
                store.finish_run(rescue_id, "resolved", True, handler_name, evidence, patch)
                return _result(rescue_id, "resolved", True, evidence, patch, tools, started)

            tools.log("verify", "%s 后现场仍未恢复，进入下一轮" % module.NAME, False)

        store.finish_run(rescue_id, "failed", False, handler_name, evidence, patch,
                        error="两轮都未能通过业务验收")
        return _result(rescue_id, "failed", False, evidence, patch, tools, started)
    except BudgetExceeded as exc:
        store.finish_run(rescue_id, "timeout", False, handler_name, evidence, patch, error=str(exc))
        return _result(rescue_id, "timeout", False, str(exc), patch, tools, started)
    except Exception as exc:  # noqa: BLE001
        store.finish_run(rescue_id, "error", False, handler_name, evidence, patch,
                         error="%s: %s" % (type(exc).__name__, exc))
        return _result(rescue_id, "error", False, "%s: %s" % (type(exc).__name__, exc),
                       patch, tools, started)
    finally:
        lock.release()


def _result(rescue_id: str, status: str, resolved: bool, evidence: str,
            patch: dict, tools: Tools, started: float) -> dict:
    return {
        "rescue_id": rescue_id,
        "status": status,
        "resolved": resolved,
        "evidence": evidence,
        "state_patch": patch,
        "seconds": round(time.monotonic() - started, 1),
        "vision_calls": tools.vision_calls,
        "tool_calls": tools.tool_calls,
    }