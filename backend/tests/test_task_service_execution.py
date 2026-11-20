"""Task execution must not block the API event loop."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.schemas.task import TaskStatus
from app.services import task_service as task_service_module
from app.services.model_config_service import ModelConfigService
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_script_wait_does_not_block_event_loop(monkeypatch):
    service = TaskService()
    task = SimpleNamespace(
        script_id="script-1",
        model_config_id=None,
        device_id="device-1",
        status=TaskStatus.EXECUTING,
    )
    connection = SimpleNamespace(
        execute=AsyncMock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(service, "get_task", AsyncMock(return_value=task))
    monkeypatch.setattr(service, "_get_script_content", AsyncMock(return_value="print('ok')"))
    monkeypatch.setattr(service, "_log", AsyncMock())
    monkeypatch.setattr(service, "_update_task_status", AsyncMock())
    monkeypatch.setattr(service, "_generate_report", AsyncMock())
    monkeypatch.setattr(
        task_service_module.db,
        "get_connection",
        AsyncMock(return_value=connection),
    )
    monkeypatch.setattr(
        ModelConfigService,
        "get_default_config",
        AsyncMock(return_value=None),
    )

    class SlowExecutor:
        def start(self, script_content, env_vars):
            return SimpleNamespace(pid=12345)

        def wait(self, cancel_check):
            time.sleep(0.25)
            return SimpleNamespace(
                status="success",
                logs=[],
                stdout="ok",
                stderr="",
                error_message=None,
            )

    monkeypatch.setattr(task_service_module, "ScriptExecutor", SlowExecutor)
    execution = asyncio.create_task(service.execute_task("task-1"))

    # The old synchronous wait blocked here until the script had finished.
    await asyncio.sleep(0.05)
    assert not execution.done()
    await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.1)
    await execution

    service._update_task_status.assert_any_await("task-1", TaskStatus.COMPLETED, progress=100)
