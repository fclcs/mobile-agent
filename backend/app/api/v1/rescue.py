"""救援服务（oag-rescue）代理。

救援服务只监听 127.0.0.1:8010，本模块把网页需要的只读接口转出去；
救援本身由脚本进程直接调用救援服务，不经过这里（避免 150 秒的长请求占用平台 worker）。
平台数据库不写入救援记录：救援库是唯一写入者，这里只读。
"""

import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

router = APIRouter()

RESCUE_BASE = os.environ.get("OAG_RESCUE_URL", "http://127.0.0.1:8010").rstrip("/")
SHORT_TIMEOUT = 5.0


async def _request(method: str, path: str, **kwargs):
    # 单独指定 timeout 的接口（如模型测试）走长超时，保持其余代理 5s 快速失败。
    timeout = kwargs.pop("timeout", SHORT_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, RESCUE_BASE + path, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="救援服务不可用：%s" % type(exc).__name__)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text[:300])
    return response


@router.get("/health")
async def rescue_health():
    try:
        response = await _request("GET", "/v1/health")
    except HTTPException:
        return {"ok": False, "enabled": False, "detail": "救援服务未运行"}
    return response.json()


@router.get("/runs")
async def rescue_runs(run_id: str = "", step_id: str = "", limit: int = 50):
    response = await _request(
        "GET", "/v1/runs", params={"run_id": run_id, "step_id": step_id, "limit": limit}
    )
    return response.json()


@router.get("/runs/{rescue_id}")
async def rescue_run_detail(rescue_id: str):
    response = await _request("GET", "/v1/rescue/%s" % rescue_id)
    return response.json()


@router.get("/stats")
async def rescue_stats():
    try:
        response = await _request("GET", "/v1/stats")
    except HTTPException:
        return {"total": 0, "resolved": 0, "today_total": 0, "today_resolved": 0,
                "success_rate": None, "avg_seconds": None}
    return response.json()


@router.get("/settings")
async def rescue_settings():
    try:
        response = await _request("GET", "/v1/settings")
    except HTTPException:
        return {"enabled": 0, "provider": "openai", "base_url": "", "model_name": "",
                "vision_model": "", "max_seconds": 150, "max_vision_calls": 3,
                "api_key_configured": False, "offline": True}
    return response.json()


@router.put("/settings")
async def update_rescue_settings(payload: dict):
    response = await _request("PUT", "/v1/settings", json=payload)
    return response.json()


@router.post("/settings/test")
async def test_rescue_settings(payload: dict):
    """转给救援服务做一次最小模型请求；模型响应慢，给 120s。"""
    response = await _request("POST", "/v1/settings/test", json=payload, timeout=120.0)
    return response.json()


@router.get("/skills")
async def rescue_skills():
    try:
        response = await _request("GET", "/v1/skills")
    except HTTPException:
        return {"active": [], "drafts": []}
    return response.json()


@router.post("/skills/{name}/promote")
async def promote_skill(name: str):
    response = await _request("POST", "/v1/skills/%s/promote" % name)
    return response.json()


@router.get("/screenshots/{path:path}")
async def rescue_screenshot(path: str):
    response = await _request("GET", "/v1/screenshots/%s" % path)
    return Response(content=response.content, media_type="image/png")