"""设备登记表与多机批量流程测试。"""

import pytest
from unittest.mock import AsyncMock

from app.db import db
from app.schemas.device import DeviceRegisterRequest, DeviceUpdateRequest
from app.schemas.workflow import WorkflowCreate, WorkflowExecute
from app.services.device_registry_service import DeviceRegistryService
from app.services.workflow_service import WorkflowService


LIVE_DEVICE = {
    "device_id": "10.0.0.11:5555",
    "name": "PEMM20",
    "platform": "android",
    "status": "connected",
    "connection_type": "tcpip",
    "ip": "127.0.0.1",
    "model": "PEMM20",
    "manufacturer": "samsung",
    "os_version": "11",
    "screen_width": 720,
    "screen_height": 1600,
    "battery_level": 88,
    "device_type": "phone",
    "android_sdk_version": "30",
}


@pytest.mark.asyncio
async def test_sync_registers_live_device_and_keeps_user_edits():
    registry = DeviceRegistryService()
    devices = await registry.sync_and_merge([LIVE_DEVICE])
    assert len(devices) == 1
    assert devices[0]["device_id"] == LIVE_DEVICE["device_id"]
    assert devices[0]["status"] == "connected"
    assert devices[0]["auto_registered"] is True

    await registry.update_device(
        LIVE_DEVICE["device_id"], DeviceUpdateRequest(name="手机1", remark="阅读专用")
    )
    # 再次同步不得覆盖用户改过的名称和备注
    devices = await registry.sync_and_merge([LIVE_DEVICE])
    assert devices[0]["name"] == "手机1"
    assert devices[0]["remark"] == "阅读专用"
    assert devices[0]["auto_registered"] is False


@pytest.mark.asyncio
async def test_offline_registered_device_is_listed_as_disconnected():
    registry = DeviceRegistryService()
    await registry.register_device(DeviceRegisterRequest(
        device_id="10.0.0.12:5555", name="备用机", group_name="演示组"
    ))
    devices = await registry.sync_and_merge([LIVE_DEVICE])
    by_id = {item["device_id"]: item for item in devices}
    assert set(by_id) == {LIVE_DEVICE["device_id"], "10.0.0.12:5555"}
    assert by_id["10.0.0.12:5555"]["status"] == "disconnected"
    assert by_id["10.0.0.12:5555"]["group_name"] == "演示组"
    assert by_id["10.0.0.12:5555"]["connection_type"] == "tcpip"


@pytest.mark.asyncio
async def test_register_existing_device_raises():
    registry = DeviceRegistryService()
    await registry.register_device(DeviceRegisterRequest(device_id="10.0.0.11:5555"))
    with pytest.raises(ValueError):
        await registry.register_device(DeviceRegisterRequest(device_id="10.0.0.11:5555"))


def test_workflow_execute_schema_accepts_multi_and_legacy():
    assert WorkflowExecute(device_ids=["a", "b", "a"]).device_ids == ["a", "b"]
    assert WorkflowExecute(device_id="a").device_ids == ["a"]
    with pytest.raises(ValueError):
        WorkflowExecute()


@pytest.mark.asyncio
async def test_create_runs_rejects_offline_and_shares_batch(monkeypatch):
    service = WorkflowService()
    script = await service.script_service.create_script(
        name="批量脚本", content="print('ok')",
        script_type="external", platform="android",
    )
    workflow = await service.create_workflow(WorkflowCreate(
        name="批量流程", script_ids=[script],
    ))
    monkeypatch.setattr(
        service.device_service, "list_online_device_ids", lambda: ["phone-a", "phone-b"]
    )
    monkeypatch.setattr(
        service.device_registry, "get_device_names",
        AsyncMock(return_value={"phone-a": "手机1", "phone-b": "手机2"}),
    )

    with pytest.raises(ValueError, match="不在线"):
        await service.create_runs(workflow["workflow_id"], ["phone-a", "phone-c"])

    result = await service.create_runs(workflow["workflow_id"], ["phone-a", "phone-b"])
    assert len(result["run_ids"]) == 2
    runs = await service.list_runs(workflow["workflow_id"])
    assert {run["batch_id"] for run in runs} == {result["batch_id"]}
    assert {run["device_name"] for run in runs} == {"手机1", "手机2"}

    with pytest.raises(ValueError, match="已有流程"):
        await service.create_runs(workflow["workflow_id"], ["phone-a"])

    # 清理忙碌状态，避免遗留运行记录干扰其它用例
    conn = await db.get_connection()
    await conn.execute("DELETE FROM workflow_runs")
    await conn.execute("DELETE FROM workflow_step_runs")
    await conn.commit()