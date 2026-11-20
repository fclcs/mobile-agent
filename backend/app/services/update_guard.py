"""脚本执行期间统一兜底关闭应用“更新提示”弹窗。

单个脚本里的更新弹窗处理零散且覆盖不全（例如某类 App 一启动就弹
“XX 更新啦”，脚本随后找不到搜索框直接失败）。这里在脚本子进程
运行期间起一个守护线程，周期性读无障碍树，点掉“下次再说/以后再说/
暂不更新”等延迟按钮，让所有脚本（工作流和单任务）都获得同一层冗余。
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INTERVAL_SECONDS = 8.0
INITIAL_DELAY_SECONDS = 3.0
ADB_TIMEOUT_SECONDS = 15


def _adb(device_id: str, *args: str, timeout: int = ADB_TIMEOUT_SECONDS):
    return subprocess.run(
        ["adb", "-s", device_id, *args],
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _script_is_dumping(device_id: str) -> bool:
    """脚本自己正在 dump 时让路，避免两个 uiautomator 并发互相报错。"""
    try:
        result = _adb(device_id, "shell", "ps", "-A", timeout=8)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and b"uiautomator" in result.stdout


def _is_asleep(device_id: str) -> bool:
    try:
        result = _adb(device_id, "shell", "dumpsys", "power")
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and b"mWakefulness=Asleep" in result.stdout


def ensure_device_awake(device_id: str) -> bool:
    """屏幕熄灭时唤醒并上滑解锁；否则脚本读到的是全黑画面，视觉会误判成广告页。"""
    if not _is_asleep(device_id):
        return False
    try:
        _adb(device_id, "shell", "input", "keyevent", "224")
        time.sleep(1.0)
        size_text = _adb(device_id, "shell", "wm", "size").stdout.decode(
            "utf-8", "replace"
        )
        match = re.search(r"(\d+)x(\d+)", size_text)
        if not match:
            return True
        width, height = int(match.group(1)), int(match.group(2))
        _adb(
            device_id, "shell", "input", "swipe",
            str(width // 2), str(int(height * 0.8)),
            str(width // 2), str(int(height * 0.2)), "300",
        )
    except (subprocess.TimeoutExpired, OSError):
        return True
    return True


class UpdateGuard:
    def __init__(self, device_id: str, context: str) -> None:
        self.device_id = device_id
        self.context = context
        self.dismissed = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="update-guard", daemon=True
        )

    def start(self) -> "UpdateGuard":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=30)
        if self.dismissed:
            print(
                f"更新提示兜底：{self.context} 期间共关闭 {self.dismissed} 次。",
                flush=True,
            )

    def _run(self) -> None:
        try:
            import vision_ads
        except Exception as exc:  # noqa: BLE001
            print(f"更新提示兜底不可用：{exc}", flush=True)
            return
        if self._stop.wait(INITIAL_DELAY_SECONDS):
            return
        while not self._stop.is_set():
            try:
                if ensure_device_awake(self.device_id):
                    print("设备屏幕已熄灭，兜底线程已唤醒并上滑解锁。", flush=True)
                if not _script_is_dumping(self.device_id):
                    dismiss_prompts = getattr(
                        vision_ads, "dismiss_blocking_prompts", None
                    )
                    if dismiss_prompts is not None:
                        self.dismissed += len(
                            dismiss_prompts(self.device_id, self.context)
                        )
                    elif vision_ads.dismiss_update_dialog(
                        self.device_id, self.context, strict=True
                    ):
                        self.dismissed += 1
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(INTERVAL_SECONDS)


def start_update_guard(device_id: str | None, context: str) -> UpdateGuard | None:
    """为一次脚本执行启动更新弹窗兜底；没有设备号时返回 None。"""
    if not device_id:
        return None
    try:
        ensure_device_awake(device_id)
        return UpdateGuard(device_id, context).start()
    except Exception:  # noqa: BLE001
        return None
