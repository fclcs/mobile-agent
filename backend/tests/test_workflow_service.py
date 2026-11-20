"""Workflow sequencing, persistence, and screenshot safety tests."""

import asyncio
import base64
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db import db
from app.schemas.workflow import WorkflowCreate
from app.services.workflow_service import PNG_MAGIC, WorkflowService


@pytest.fixture
def service(tmp_path, monkeypatch):
    WorkflowService._run_processes.clear()
    WorkflowService._cancel_requested.clear()
    workflow_service = WorkflowService()
    workflow_service.screenshot_dir = tmp_path / "流程截图"
    monkeypatch.setattr(
        workflow_service.device_service,
        "get_screenshot",
        lambda device_id: base64.b64encode(PNG_MAGIC + device_id.encode()).decode(),
    )
    return workflow_service


async def create_script(service: WorkflowService, name: str, content: str) -> str:
    return await service.script_service.create_script(
        name=name,
        content=content,
        script_type="external",
        platform="android",
    )


@pytest.mark.asyncio
async def test_workflow_executes_in_order_and_stores_screenshots(service):
    first = await create_script(
        service,
        "第一步",
        "import os\nprint('first:' + os.environ['PHONE_AGENT_DEVICE_ID'])",
    )
    second = await create_script(service, "第二步", "print('second')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="顺序测试",
        description="验证顺序和截图",
        script_ids=[first, second],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)

    run = await service.get_run(run_id)
    assert run["status"] == "completed"
    assert [step["status"] for step in run["steps"]] == ["completed", "completed"]
    assert "first:device-1" in run["steps"][0]["output"]
    assert "second" in run["steps"][1]["output"]
    assert run["steps"][0]["started_at"] <= run["steps"][1]["started_at"]

    screenshots = await service.list_screenshots(workflow["workflow_id"])
    assert len(screenshots) == 2
    assert {item["workflow_name"] for item in screenshots} == {"顺序测试"}
    assert {item["script_name"] for item in screenshots} == {"第一步", "第二步"}
    for step in run["steps"]:
        image_path = await service.get_screenshot_file(step["step_id"])
        assert image_path.read_bytes().startswith(PNG_MAGIC)
        assert step["captured_at"]
        assert image_path.parent.name == run_id


def test_workflow_subprocess_runs_with_selector_event_loop(service, monkeypatch):
    monkeypatch.setattr(
        service.script_service,
        "get_script",
        AsyncMock(return_value=SimpleNamespace(content="print('selector subprocess')")),
    )
    monkeypatch.setattr(
        service,
        "_build_environment",
        AsyncMock(return_value=os.environ.copy()),
    )
    run = {"run_id": "selector-run", "device_id": "device-1"}
    step = {
        "step_id": "selector-step",
        "step_order": 1,
        "script_id": "selector-script",
        "script_name": "Selector 测试",
    }

    # Uvicorn 的 Windows 热重载子进程使用 SelectorEventLoop。
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        exit_code, output = runner.run(service._execute_script(run, step))

    assert exit_code == 0
    assert "selector subprocess" in output


@pytest.mark.asyncio
async def test_failed_step_captures_screenshot_and_skips_remaining(service):
    failed = await create_script(service, "失败步骤", "print('before failure')\nraise SystemExit(3)")
    not_run = await create_script(service, "不应执行", "print('must not run')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="失败停止测试",
        script_ids=[failed, not_run],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)

    run = await service.get_run(run_id)
    assert run["status"] == "failed"
    assert run["steps"][0]["status"] == "failed"
    assert run["steps"][0]["exit_code"] == 3
    assert run["steps"][0]["screenshot_path"]
    assert "before failure" in run["steps"][0]["output"]
    assert run["steps"][1]["status"] == "skipped"
    assert run["steps"][1]["started_at"] is None
    assert len(await service.list_screenshots()) == 1


@pytest.mark.asyncio
async def test_continue_on_error_skips_failed_step_and_runs_rest(service):
    """流程开启容错：失败脚本被跳过，后续脚本继续，最终标记为 partial。"""
    failed = await create_script(
        service, "失败步骤", "print('before failure')\nraise SystemExit(2)"
    )
    second = await create_script(service, "继续执行", "print('kept going')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="容错继续测试",
        script_ids=[failed, second],
        continue_on_error=True,
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)

    run = await service.get_run(run_id)
    assert run["status"] == "partial"
    assert [step["status"] for step in run["steps"]] == ["failed", "completed"]
    assert run["steps"][1]["output"].strip() == "kept going"
    assert "第 1 步「失败步骤」" in run["error"]
    assert "脚本退出码为 2" in run["error"]
    assert len(await service.list_screenshots()) == 2


@pytest.mark.asyncio
async def test_step_timeout_kills_script_and_reports_timeout(service):
    slow = await create_script(service, "超时脚本", "import time\ntime.sleep(30)")
    workflow = await service.create_workflow(WorkflowCreate(
        name="超时测试",
        script_ids=[slow],
        continue_on_error=True,
        step_timeout=1,
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)

    run = await service.get_run(run_id)
    assert run["status"] == "partial"
    assert run["steps"][0]["status"] == "failed"
    assert run["steps"][0]["exit_code"] == 124
    assert "脚本执行超时" in run["steps"][0]["output"]
    assert "超时" in run["error"]


@pytest.mark.asyncio
async def test_screenshot_failure_prevents_false_success(service, monkeypatch):
    script_id = await create_script(service, "脚本成功", "print('ok')")
    monkeypatch.setattr(service.device_service, "get_screenshot", lambda device_id: None)
    workflow = await service.create_workflow(WorkflowCreate(
        name="截图失败测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)

    run = await service.get_run(run_id)
    assert run["status"] == "failed"
    assert run["steps"][0]["exit_code"] == 0
    assert run["steps"][0]["status"] == "failed"
    assert "步骤截图保存失败" in run["steps"][0]["error"]


@pytest.mark.asyncio
async def test_screenshot_preview_rejects_path_outside_root(service):
    script_id = await create_script(service, "安全测试", "print('ok')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="路径安全测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)
    run = await service.get_run(run_id)
    step_id = run["steps"][0]["step_id"]

    conn = await db.get_connection()
    await conn.execute(
        "UPDATE workflow_step_runs SET screenshot_path = '../outside.png' WHERE step_id = ?",
        (step_id,),
    )
    await conn.commit()
    with pytest.raises(PermissionError):
        await service.get_screenshot_file(step_id)


@pytest.mark.asyncio
async def test_missing_script_is_rejected(service):
    with pytest.raises(ValueError, match="脚本不存在"):
        await service.create_workflow(WorkflowCreate(
            name="无效流程",
            script_ids=["script_missing"],
        ))


@pytest.mark.asyncio
async def test_delete_single_run_removes_steps_and_screenshots(service):
    script_id = await create_script(service, "可删除脚本", "print('done')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="删除测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)
    run = await service.get_run(run_id)
    screenshot = await service.get_screenshot_file(run["steps"][0]["step_id"])
    assert screenshot.exists()

    result = await service.delete_runs([run_id])

    assert result["deleted"] == 1
    assert result["screenshot_files"] == 1
    assert await service.get_run(run_id) is None
    assert await service.list_screenshots(workflow["workflow_id"]) == []
    assert not screenshot.exists()


@pytest.mark.asyncio
async def test_batch_delete_runs_dedupes_and_reports_count(service):
    first_script = await create_script(service, "批量一", "print('a')")
    second_script = await create_script(service, "批量二", "print('b')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="批量删除测试",
        script_ids=[first_script, second_script],
    ))
    run_a = await service.create_run(workflow["workflow_id"], "device-1")
    run_b = await service.create_run(workflow["workflow_id"], "device-2")
    await service.execute_run(run_a)
    await service.execute_run(run_b)

    result = await service.delete_runs([run_a, run_b, run_a])

    assert result["deleted"] == 2
    assert sorted(result["run_ids"]) == sorted([run_a, run_b])
    assert await service.get_run(run_a) is None
    assert await service.get_run(run_b) is None
    assert await service.list_runs(workflow["workflow_id"]) == []


@pytest.mark.asyncio
async def test_delete_rejects_running_run(service):
    script_id = await create_script(service, "运行中", "print('x')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="运行中删除测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")

    with pytest.raises(ValueError, match="仍在运行"):
        await service.delete_runs([run_id])
    assert (await service.get_run(run_id))["status"] == "pending"


@pytest.mark.asyncio
async def test_cancel_running_run_resets_run_and_steps(service):
    slow = await create_script(
        service, "慢脚本", "import time\ntime.sleep(30)\nprint('should not finish')"
    )
    later = await create_script(service, "后续脚本", "print('must not run')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="中断测试",
        script_ids=[slow, later],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    task = asyncio.create_task(service.execute_run(run_id))

    for _ in range(300):
        if run_id in WorkflowService._run_processes:
            break
        await asyncio.sleep(0.02)
    else:
        task.cancel()
        pytest.fail("脚本进程没有启动")

    cancelled = await asyncio.wait_for(service.cancel_run(run_id), timeout=10)
    await asyncio.wait_for(task, timeout=15)

    assert cancelled["status"] == "cancelled"
    run = await service.get_run(run_id)
    assert run["status"] == "cancelled"
    assert run["steps"][0]["status"] == "cancelled"
    assert run["steps"][1]["status"] == "skipped"
    assert run["completed_at"]
    assert run_id not in WorkflowService._run_processes


@pytest.mark.asyncio
async def test_cancel_terminal_run_is_rejected(service):
    script_id = await create_script(service, "已完成", "print('ok')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="已结束中断测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    await service.execute_run(run_id)

    with pytest.raises(ValueError, match="已结束"):
        await service.cancel_run(run_id)


@pytest.mark.asyncio
async def test_cancel_duplicate_request_is_rejected(service):
    script_id = await create_script(service, "等待中", "print('x')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="重复中断测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")

    WorkflowService._cancel_requested.add(run_id)
    try:
        with pytest.raises(ValueError, match="正在中断"):
            await service.cancel_run(run_id)
    finally:
        WorkflowService._cancel_requested.discard(run_id)


@pytest.mark.asyncio
async def test_reset_orphaned_runs_marks_stale_records_cancelled(service):
    """服务重启后遗留的 pending/executing 记录会被自动重置，手机恢复可用。"""
    script_id = await create_script(service, "遗留记录", "print('x')")
    workflow = await service.create_workflow(WorkflowCreate(
        name="遗留记录测试",
        script_ids=[script_id],
    ))
    run_id = await service.create_run(workflow["workflow_id"], "device-1")
    conn = await db.get_connection()
    await conn.execute(
        "UPDATE workflow_runs SET status = 'executing' WHERE run_id = ?", (run_id,)
    )
    await conn.commit()

    assert await service.reset_orphaned_runs() == 1

    run = await service.get_run(run_id)
    assert run["status"] == "cancelled"
    assert "已自动重置" in run["error"]
    assert await service._busy_devices(["device-1"]) == []
