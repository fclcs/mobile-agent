"""Device management API."""

import asyncio

from fastapi import APIRouter, HTTPException
from typing import List

from app.schemas.device import (
    DeviceInfo,
    DeviceRegisterRequest,
    DeviceUpdateRequest,
    PlatformType,
    TcpIpConnectRequest,
    WirelessConnectRequest,
    DeviceIpResponse,
)
from app.services.device_service import DeviceService
from app.services.device_registry_service import device_registry_service

router = APIRouter()
device_service = DeviceService()


async def _live_devices(platform: PlatformType | None = None) -> List[DeviceInfo]:
    """ADB/HDC 探测会阻塞，放到线程里避免卡住事件循环。"""
    return await asyncio.to_thread(device_service.list_devices, platform)


async def _merged_devices(platform: PlatformType | None = None) -> list[dict]:
    live = await _live_devices(platform)
    return await device_registry_service.sync_and_merge(
        [device.model_dump() for device in live],
        platform.value if platform else None,
    )


@router.get("/")
async def list_devices(platform: PlatformType | None = None):
    """List registered devices merged with live ADB status.

    在线设备自动登记；已登记但离线的设备仍会返回，状态为 disconnected。
    """
    return {"devices": await _merged_devices(platform)}


@router.post("/")
async def register_device(data: DeviceRegisterRequest):
    """Manually register a device (offline phones included)."""
    try:
        device = await device_registry_service.register_device(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return device


# --- Static TCP/IP routes must precede "/{device_id}/..." routes ---

@router.post("/tcpip/connect")
async def connect_tcpip(request: TcpIpConnectRequest):
    """Connect to an Android device via TCP/IP (e.g., 192.168.1.100:5555)."""
    success = await asyncio.to_thread(device_service.connect_tcpip, request.ip_port)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to connect via TCP/IP")
    return {"status": "connected", "ip_port": request.ip_port}


@router.post("/tcpip/disconnect/{ip_port}")
async def disconnect_tcpip(ip_port: str):
    """Disconnect from an Android device connected via TCP/IP."""
    await asyncio.to_thread(device_service.disconnect_tcpip, ip_port)
    return {"status": "disconnected", "ip_port": ip_port}


@router.get("/{device_id}")
async def get_device(device_id: str) -> DeviceInfo:
    """Get device details by ID."""
    devices = await _merged_devices()
    match = next((item for item in devices if item["device_id"] == device_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceInfo(**match)


@router.put("/{device_id}")
async def update_device(device_id: str, data: DeviceUpdateRequest):
    """Edit name / remark / group of a registered device."""
    device = await device_registry_service.update_device(device_id, data)
    if device is None:
        raise HTTPException(status_code=404, detail="设备未登记，请先添加设备")
    return device


@router.delete("/{device_id}")
async def delete_device(device_id: str):
    """Remove a registered device. Online devices must be disconnected first."""
    online = await asyncio.to_thread(device_service.list_online_device_ids)
    if device_id in online:
        raise HTTPException(status_code=400, detail="设备当前在线，请先断开连接再删除")
    if not await device_registry_service.delete_device(device_id):
        raise HTTPException(status_code=404, detail="设备未登记")
    return {"message": "设备已从登记表移除"}


@router.post("/{device_id}/connect")
async def connect_device(device_id: str):
    """Connect to a device (reconnects offline TCP/IP devices)."""
    result = await asyncio.to_thread(device_service.connect_device, device_id)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="连接失败：请确认手机端 frpc 已启动、无线调试已开启；USB 设备需重新插线",
        )
    return {"status": "connected", "device_id": device_id}


@router.post("/{device_id}/disconnect")
async def disconnect_device(device_id: str):
    """Disconnect from a device."""
    await asyncio.to_thread(device_service.disconnect_device, device_id)
    return {"status": "disconnected", "device_id": device_id}


@router.get("/{device_id}/screenshot")
async def get_screenshot(device_id: str):
    """Get screenshot from device."""
    screenshot_data = await asyncio.to_thread(device_service.get_screenshot, device_id)
    if not screenshot_data:
        raise HTTPException(status_code=400, detail="Failed to capture screenshot")
    return {"screenshot_base64": screenshot_data, "device_id": device_id}


@router.post("/{device_id}/launch/{app_name}")
async def launch_app(device_id: str, app_name: str):
    """Launch an app on the device."""
    result = await asyncio.to_thread(device_service.launch_app, device_id, app_name)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to launch app")
    return {"status": "launched", "app_name": app_name}


@router.get("/{device_id}/apps")
async def get_installed_apps(device_id: str):
    """Get list of installed apps on device."""
    apps = await asyncio.to_thread(device_service.get_installed_apps, device_id)
    return {"apps": apps}


@router.get("/{device_id}/ip", response_model=DeviceIpResponse)
async def get_device_ip(device_id: str):
    """Get device IP address."""
    ip = await asyncio.to_thread(device_service.get_device_ip, device_id)
    if not ip:
        raise HTTPException(status_code=404, detail="无法获取设备IP地址")
    return {"ip": ip, "interface": "wlan0"}


@router.post("/{device_id}/wireless")
async def enable_wireless(device_id: str, port: int = 5555):
    """Enable wireless connection for a USB device."""
    result = await asyncio.to_thread(
        device_service.enable_wireless_connection, device_id, port
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result