"""原子动作层：每个动作都受预算约束，并写入救援时间线。

复用平台脚本已经在用的 vision_ads 基元，保证“救援看到的”和“脚本看到的”是同一套判定；
不重新实现截图、点击、广告识别，避免两套行为漂移。
"""

from __future__ import annotations

import os
import subprocess
import time

import vision_ads

from . import store


class BudgetExceeded(Exception):
    pass


class Tools:
    def __init__(self, device_id: str, rescue_id: str, deadline: float,
                 vision_budget: int, tool_budget: int) -> None:
        self.device = device_id
        self.rescue_id = rescue_id
        self.deadline = deadline
        self.vision_budget = vision_budget
        self.tool_budget = tool_budget
        self.vision_calls = 0
        self.tool_calls = 0
        self._size: tuple[int, int] | None = None

    # -- 基础设施 -------------------------------------------------------
    def time_left(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def _gate(self) -> None:
        if self.time_left() <= 1.0:
            raise BudgetExceeded("救援时间预算用尽")
        if self.tool_calls >= self.tool_budget:
            raise BudgetExceeded("动作次数达到上限")

    def log(self, phase: str, detail: str, ok: bool | None = None,
            screenshot: str | None = None) -> None:
        store.add_step(self.rescue_id, phase, detail, ok, screenshot)

    def _bump(self) -> None:
        self.tool_calls += 1
        store.bump(self.rescue_id, "tool_calls")

    def _run(self, args: list[str], timeout: int = 20) -> tuple[bool, str]:
        self._gate()
        self._bump()
        try:
            result = subprocess.run(
                ["adb", "-s", self.device] + args, capture_output=True, timeout=timeout
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, "%s: %s" % (type(exc).__name__, exc)
        out = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
        return result.returncode == 0, out

    # -- 基础动作 -------------------------------------------------------
    def tap(self, x: int, y: int, why: str) -> bool:
        ok, out = self._run(["shell", "input", "tap", str(x), str(y)])
        self.log("tap", "%s @(%d,%d) %s" % (why, x, y, "" if ok else out), ok)
        return ok

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int, why: str) -> bool:
        ok, out = self._run(
            ["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms)]
        )
        self.log("swipe", "%s (%d,%d)->(%d,%d) %s" % (why, x1, y1, x2, y2, "" if ok else out), ok)
        return ok

    def key(self, name: str, times: int = 1) -> bool:
        ok = True
        for _ in range(max(1, times)):
            ok, out = self._run(["shell", "input", "keyevent", name])
            if not ok:
                self.log("key", "%s 失败：%s" % (name, out), False)
                return False
            time.sleep(0.6)
        self.log("key", "按 %s ×%d" % (name, times), True)
        return ok

    def back(self, times: int = 1) -> bool:
        return self.key("KEYCODE_BACK", times)

    def tap_text(self, labels, why: str) -> bool:
        """按无障碍树里的按钮文字点击（确定性，不花模型调用）。"""
        self._gate()
        self._bump()
        ok = vision_ads.tap_label(self.device, tuple(labels), why)
        self.log("tap", "tap_label(%s: %s) → %s" % (why, "/".join(labels), ok), ok)
        return ok

    def screen_size(self) -> tuple[int, int]:
        if self._size:
            return self._size
        ok, out = self._run(["shell", "wm", "size"])
        for token in out.replace("Override size:", "").replace("Physical size:", "").split():
            if "x" in token:
                try:
                    w, h = token.split("x")
                    self._size = (int(w), int(h))
                except ValueError:
                    continue
        return self._size or (1080, 2400)

    def launch(self, package: str) -> bool:
        ok, out = self._run(
            ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
            timeout=25,
        )
        self.log("launch", "启动 %s %s" % (package, "" if ok else out), ok)
        if ok:
            time.sleep(2.0)
        return ok

    # -- 视觉能力（受预算约束）------------------------------------------
    def classify(self, png: bytes | None, context: str) -> dict | None:
        if not png:
            return None
        if self.vision_calls >= self.vision_budget:
            self.log("vision", "视觉预算已用尽（%d），跳过" % self.vision_calls, None)
            return None
        self._gate()
        self.vision_calls += 1
        store.bump(self.rescue_id, "vision_calls")
        result = vision_ads.classify(png)
        page = (result or {}).get("page_type")
        self.log("vision", "%s → page=%s is_ad=%s reason=%s" % (
            context, page, (result or {}).get("is_ad"), (result or {}).get("reason")), None)
        return result

    def identify(self, png: bytes | None, options, context: str) -> str | None:
        if not png:
            return None
        if self.vision_calls >= self.vision_budget:
            self.log("vision", "视觉预算已用尽，跳过页面识别", None)
            return None
        self._gate()
        self.vision_calls += 1
        store.bump(self.rescue_id, "vision_calls")
        page = vision_ads.identify_page_png(png, options)
        self.log("vision", "%s → %s" % (context, page), None)
        return page

    # -- 平台既有修复基元 -----------------------------------------------
    def try_close(self, context: str, confirm: bool = True) -> bool:
        self._gate()
        self._bump()
        ok = vision_ads.try_close(self.device, context, confirm=confirm)
        self.log("close", "try_close(%s) → %s" % (context, ok), ok)
        return ok

    def dismiss_update(self, context: str) -> bool:
        self._gate()
        self._bump()
        ok = vision_ads.dismiss_update_dialog(self.device, context)
        if not ok:
            ok = vision_ads.dismiss_update_dialog_by_vision(self.device, context)
        self.log("update", "关闭更新弹窗(%s) → %s" % (context, ok), ok)
        return ok

    def dismiss_prompts(self, context: str) -> list[str]:
        self._gate()
        self._bump()
        handled = vision_ads.dismiss_blocking_prompts(self.device, context)
        self.log("prompts", "dismiss_blocking_prompts → %s" % (handled or "无"), bool(handled))
        return list(handled or [])

    def dismiss_rating(self, context: str) -> bool:
        self._gate()
        self._bump()
        ok = vision_ads.dismiss_rating_popup(self.device, context)
        self.log("rating", "关闭评分弹窗(%s) → %s" % (context, ok), ok)
        return ok

    def is_text_page(self, context: str) -> bool | None:
        self._gate()
        self._bump()
        result = vision_ads.is_text_page(self.device, context)
        self.log("vision", "is_text_page(%s) → %s" % (context, result), result)
        return result

    def mobile_agent(self, goal: str, verify) -> bool:
        """复用平台现有的 B 档 PhoneAgent：动作白名单与验收纪律保持一致。"""
        self._gate()
        self._bump()
        try:
            import vision_fallback
        except Exception as exc:  # noqa: BLE001
            self.log("agent", "无法导入 vision_fallback：%s" % exc, False)
            return False
        os.environ["OAG_RESCUE_INTERNAL"] = "1"
        try:
            ok = vision_fallback.recover_with_agent(
                self.device, goal, verify=verify, max_steps=5
            )
        except Exception as exc:  # noqa: BLE001
            self.log("agent", "PhoneAgent 异常：%s: %s" % (type(exc).__name__, exc), False)
            return False
        finally:
            os.environ.pop("OAG_RESCUE_INTERNAL", None)
        self.log("agent", "PhoneAgent 接管 → %s" % ok, ok)
        return ok