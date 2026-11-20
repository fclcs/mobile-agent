"""Sequential workflow execution and screenshot history API."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowExecute,
    WorkflowRunBatchDelete,
    WorkflowUpdate,
)
from app.services.workflow_service import WorkflowService

router = APIRouter()
workflow_service = WorkflowService()
logger = logging.getLogger(__name__)

# 并行执行多个手机的 run；持有引用避免任务被垃圾回收。
_background_runs: set[asyncio.Task] = set()


def _spawn_run(run_id: str) -> None:
    task = asyncio.create_task(_execute_run_safely(run_id))
    _background_runs.add(task)
    task.add_done_callback(lambda finished: _background_runs.discard(finished))


async def _execute_run_safely(run_id: str) -> None:
    try:
        await workflow_service.execute_run(run_id)
    except Exception:  # noqa: BLE001
        logger.exception("流程执行器异常：%s", run_id)


@router.get("/screenshots")
async def list_screenshots(workflow_id: str | None = None):
    return {"screenshots": await workflow_service.list_screenshots(workflow_id)}


@router.get("/screenshots/{step_id}/image")
async def get_screenshot(step_id: str):
    try:
        path = await workflow_service.get_screenshot_file(step_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="image/png",
        filename=path.name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/runs")
async def list_runs(workflow_id: str | None = None):
    return {"runs": await workflow_service.list_runs(workflow_id)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = await workflow_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="流程执行记录不存在")
    return run


@router.post("/runs/batch-delete")
async def batch_delete_runs(data: WorkflowRunBatchDelete):
    """批量删除执行历史；运行中的记录需要先中断，否则返回 409。"""
    try:
        result = await workflow_service.delete_runs(data.run_ids)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="没有找到要删除的执行记录")
    return {"message": f"已删除 {result['deleted']} 条执行记录", **result}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """中断运行中的流程执行（终止当前脚本进程，后续步骤跳过）。"""
    try:
        run = await workflow_service.cancel_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="流程执行记录不存在")
    return run


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    """删除单条执行历史（含步骤记录与截图文件）。"""
    try:
        result = await workflow_service.delete_runs([run_id])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail="流程执行记录不存在")
    return {"message": "执行记录已删除", **result}


@router.get("/")
async def list_workflows():
    return {"workflows": await workflow_service.list_workflows()}


@router.post("/")
async def create_workflow(data: WorkflowCreate):
    try:
        return await workflow_service.create_workflow(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    workflow = await workflow_service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return workflow


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, data: WorkflowUpdate):
    try:
        workflow = await workflow_service.update_workflow(workflow_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if workflow is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return workflow


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    if not await workflow_service.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="流程不存在")
    return {"message": "流程已删除，历史执行记录和截图仍保留"}


@router.post("/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, data: WorkflowExecute):
    """在选中的多台手机上并行启动同一流程（每台独立、互不影响）。"""
    try:
        result = await workflow_service.create_runs(workflow_id, data.device_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for run_id in result["run_ids"]:
        _spawn_run(run_id)
    return {
        "workflow_id": workflow_id,
        "batch_id": result["batch_id"],
        "run_ids": result["run_ids"],
        "device_ids": result["device_ids"],
        "status": "executing",
    }
