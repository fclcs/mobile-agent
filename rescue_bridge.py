"""脚本 → oag-rescue 的桥。

脚本卡住时调用 `handoff(...)`：阻塞等待救援服务把现场修回可继续，返回是否救回。
设计纪律：
- **绝不抛异常**：救援服务没开、超时、500，一律返回 False，脚本按原逻辑继续失败；
- **不重跑步骤**：救援只是把手机界面弄回可继续，脚本自己的计数器与验收照旧；
- **可关闭**：服务侧 enabled=0 或进程不在，脚本行为与今天完全一致。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("PHONE_AGENT_RESCUE_URL", "http://127.0.0.1:8010").rstrip("/")
HEALTH_TTL = 30.0

_health_cache = {"at": 0.0, "ok": False}


def _post(path: str, payload: dict, timeout: float) -> dict | None:
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _get(path: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def available(refresh: bool = False) -> bool:
    """救援服务是否可用（enabled 且有模型）。结果缓存 30 秒，脚本里可高频问。"""
    if os.environ.get("OAG_RESCUE_INTERNAL") == "1":
        # 救援服务内部复用 recover_with_agent 时禁止回调自己，避免递归
        return False
    now = time.monotonic()
    if not refresh and now - _health_cache["at"] < HEALTH_TTL:
        return bool(_health_cache["ok"])
    health = _get("/v1/health")
    ok = bool(health and health.get("ok") and health.get("enabled"))
    _health_cache.update({"at": now, "ok": ok})
    return ok


def handoff(device_id: str, goal: str = "", *, app: str = "", package: str = "",
            expected: str = "any", state: dict | None = None, rounds: int = 2,
            timeout: float = 180.0) -> dict:
    """把现场交给救援服务，最多 rounds 轮，每轮最多等 timeout 秒。

    返回 {"resolved": bool, "status": str, "evidence": str, "state_patch": dict}；
    永不抛异常。state_patch 建议脚本消费（例如 pages_delta/relaunched）。
    """
    result = {"resolved": False, "status": "unavailable", "evidence": "", "state_patch": {}}
    if not device_id or not available():
        return result

    payload = {
        "device_id": device_id,
        "run_id": os.environ.get("PHONE_AGENT_WORKFLOW_RUN_ID", ""),
        "step_id": os.environ.get("PHONE_AGENT_WORKFLOW_STEP_ID", ""),
        "script_name": os.environ.get("PHONE_AGENT_SCRIPT_NAME", ""),
        "app": app,
        "package": package,
        "goal": goal,
        "expected": expected,
        "state": state or {},
        # handoff 只在这些“自有恢复手段都失败”的位置发起，语义即业务动作已卡住，
        # 让救援跳过“前台正确即放行”的提前验收。
        "stuck": True,
    }
    for index in range(max(1, int(rounds))):
        print("[救援] 第 %d 轮接管：%s（%s）" % (index + 1, goal or "现场恢复", device_id), flush=True)
        data = _post("/v1/rescue", payload, timeout)
        if data is None:
            result["status"] = "unreachable"
            print("[救援] 服务无响应，交回脚本", flush=True)
            return result
        result = {
            "resolved": bool(data.get("resolved")),
            "status": data.get("status") or "",
            "evidence": data.get("evidence") or "",
            "state_patch": data.get("state_patch") or {},
            "rescue_id": data.get("rescue_id") or "",
            "seconds": data.get("seconds"),
        }
        print("[救援] %s：%s（%.1fs）%s" % (
            data.get("status"), result["evidence"], result.get("seconds") or 0.0,
            "，已交回脚本继续" if result["resolved"] else "",
        ), flush=True)
        if result["resolved"]:
            return result
    return result


def rescue_handoff(goal: str, state: dict | None = None, **kwargs) -> bool:
    """脚本内一行式调用；没有可用服务时立刻返回 False。"""
    device = os.environ.get("DEVICE_SERIAL", "")
    return handoff(device, goal, state=state, **kwargs)["resolved"]