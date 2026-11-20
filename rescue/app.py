"""oag-rescue HTTP 服务：只监听 127.0.0.1，由平台后端反代出去。

接口分两类：
- 脚本侧（/v1/rescue）：救援入口，脚本阻塞等待结果后自己决定是否继续；
- 网页侧（/v1/settings、/v1/runs、/v1/skills）：配置与审计，全部经平台后端代理。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, coordinator, skills, store


def _cleanup_screenshots() -> int:
    """按保留天数清理现场截图，避免 /var/lib 无限膨胀。"""
    cutoff = time.time() - config.SCREENSHOT_RETENTION_DAYS * 86400
    removed = 0
    root = config.SCREENSHOT_DIR
    if not os.path.isdir(root):
        return 0
    for name in os.listdir(root):
        directory = os.path.join(root, name)
        try:
            if os.path.isdir(directory) and os.path.getmtime(directory) < cutoff:
                for inner in os.listdir(directory):
                    os.unlink(os.path.join(directory, inner))
                os.rmdir(directory)
                removed += 1
        except OSError:
            continue
    return removed


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.connect()
    store.load_settings().apply_env()
    _cleanup_screenshots()
    yield


app = FastAPI(title="oag-rescue", version="0.1.0", lifespan=lifespan)


class RescueRequest(BaseModel):
    device_id: str
    run_id: str = ""
    step_id: str = ""
    script_name: str = ""
    app: str = ""
    package: str = ""
    goal: str = ""
    expected: str = "any"
    state: dict = {}
    # 脚本判定“业务动作卡住”（不是单纯页面遮挡）时置 True：
    # 协调器据此跳过“现场已可继续”的提前放行，交给 handler 做业务验收。
    stuck: bool = False


class SettingsRequest(BaseModel):
    enabled: int | bool | None = None
    provider: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    # 视觉识别独立配置（留空即沿用操作模型）
    vision_model: str | None = None
    vision_base_url: str | None = None
    vision_api_key: str | None = None
    vision_disable_thinking: int | bool | None = None
    max_seconds: int | None = None
    max_vision_calls: int | None = None


class SettingsTestRequest(SettingsRequest):
    """测试连接：target=op 测操作模型，target=vision 测视觉模型。"""

    target: str | None = None


def _chat_probe(base_url: str, api_key: str, model_name: str, disable_thinking: bool,
                retry_without_thinking: bool = True) -> tuple[bool, str]:
    """对 OpenAI 兼容接口发一次最小请求，只用于判断 Key / URL / 模型名是否可用。"""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return False, "Base URL 为空"
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 512,
        "stream": False,
    }
    if disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            json.loads(response.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")[:400]
        # 有些供应商（如部分思考模型）拒绝 thinking.type=disabled，去掉该参数重试一次。
        if disable_thinking and retry_without_thinking and exc.code == 400:
            return _chat_probe(base_url, api_key, model_name, False, False)
        return False, "HTTP %s：%s" % (exc.code, text)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return False, "请求失败：%s" % type(exc).__name__
    return True, "连接成功"


@app.get("/v1/health")
def health() -> dict:
    settings = store.load_settings()
    return {
        "ok": True,
        "service": "oag-rescue",
        "enabled": bool(settings.enabled),
        "model_ready": bool(settings.api_key and (settings.model_name or settings.vision_model)),
        "time": store.now(),
    }


@app.post("/v1/rescue")
def rescue(request: RescueRequest) -> dict:
    return coordinator.rescue(request.model_dump())


@app.get("/v1/rescue/{rescue_id}")
def rescue_detail(rescue_id: str) -> dict:
    record = store.get_run(rescue_id)
    if record is None:
        raise HTTPException(status_code=404, detail="救援记录不存在")
    return record


@app.get("/v1/runs")
def runs(run_id: str = "", step_id: str = "", limit: int = 50) -> dict:
    return {"items": store.list_runs(run_id, step_id, limit)}


@app.get("/v1/stats")
def stats() -> dict:
    return store.stats()


@app.get("/v1/settings")
def get_settings() -> dict:
    return store.load_settings().public()


@app.put("/v1/settings")
def put_settings(request: SettingsRequest) -> dict:
    fields = {k: v for k, v in request.model_dump().items() if v is not None}
    if "enabled" in fields:
        fields["enabled"] = int(bool(fields["enabled"]))
    if "vision_disable_thinking" in fields:
        fields["vision_disable_thinking"] = int(bool(fields["vision_disable_thinking"]))
    updated = store.save_settings(fields)
    return updated.public()


@app.post("/v1/settings/test")
def test_settings(request: SettingsTestRequest) -> dict:
    """用“已保存 + 本次提交（未保存）”的配置测试连接，不落库、不打印密钥。"""
    current = store.load_settings()
    fields = {k: v for k, v in request.model_dump(exclude={"target"}).items() if v is not None}
    for key in ("api_key", "vision_api_key"):
        if fields.get(key) in ("", "******"):
            fields.pop(key, None)
    merged = config.RescueSettings(**{**current.__dict__, **fields})
    if (request.target or "op") == "vision":
        if not merged.vision_ready:
            return {"success": False,
                    "message": "视觉模型配置不完整：需要视觉 Base URL、视觉 API Key、视觉模型名"}
        base_url, api_key, model_name = (
            merged.vision_base_url, merged.vision_api_key, merged.vision_model)
        disable_thinking = bool(merged.vision_disable_thinking)
        label = "视觉模型"
        provider = "openai"  # vision_ads 只走 OpenAI 兼容协议
    else:
        if not (merged.base_url and merged.api_key and merged.model_name):
            return {"success": False, "message": "操作模型配置不完整：需要 Base URL、API Key、操作模型名"}
        base_url, api_key, model_name = merged.base_url, merged.api_key, merged.model_name
        disable_thinking = False
        label = "操作模型"
        provider = merged.provider or "openai"
    if provider != "openai":
        return {"success": False, "message": "仅 OpenAI 兼容接口支持在线测试"}
    success, message = _chat_probe(base_url, api_key, model_name, disable_thinking)
    return {"success": success, "message": "%s：%s" % (label, message)}


@app.get("/v1/skills")
def get_skills() -> dict:
    return skills.list_skills()


@app.post("/v1/skills/{name}/promote")
def promote_skill(name: str) -> dict:
    if not skills.promote(name):
        raise HTTPException(status_code=404, detail="草稿技能不存在")
    return {"ok": True, "promoted": name}


@app.get("/v1/screenshots/{path:path}")
def screenshot(path: str) -> FileResponse:
    root = os.path.realpath(config.SCREENSHOT_DIR)
    target = os.path.realpath(os.path.join(root, path))
    if not target.startswith(root + os.sep) or not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="截图不存在")
    return FileResponse(target, media_type="image/png")