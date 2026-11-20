"""Device schemas."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum
from typing import Optional


class PlatformType(str, Enum):
    """Supported platforms."""
    ANDROID = "android"
    IOS = "ios"
    HARMONYOS = "harmonyos"


class DeviceStatus(str, Enum):
    """Device connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ONLINE = "online"
    OFFLINE = "offline"


class ConnectionType(str, Enum):
    """Device connection type."""
    USB = "usb"
    TCPIP = "tcpip"


class DeviceInfo(BaseModel):
    """Device information model."""
    device_id: str
    name: str
    platform: PlatformType
    status: DeviceStatus
    connection_type: ConnectionType = ConnectionType.USB
    ip: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None
    screen_width: Optional[int] = None
    screen_height: Optional[int] = None
    battery_level: Optional[int] = None
    device_type: Optional[str] = None
    android_sdk_version: Optional[str] = None
    last_seen: Optional[str] = None
    last_seen_at: Optional[str] = None
    remark: Optional[str] = None
    group_name: Optional[str] = None
    registered: bool = True
    auto_registered: bool = True
    available_actions: Optional[list] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class DeviceRegisterRequest(BaseModel):
    """手动登记设备（可登记未在线的手机）。"""
    device_id: str = Field(min_length=1, max_length=100)
    name: Optional[str] = Field(default=None, max_length=100)
    remark: Optional[str] = Field(default=None, max_length=200)
    group_name: Optional[str] = Field(default=None, max_length=50)
    platform: PlatformType = PlatformType.ANDROID
    connection_type: Optional[ConnectionType] = None

    @field_validator("device_id")
    @classmethod
    def device_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("设备标识（serial）不能为空")
        return value


class DeviceUpdateRequest(BaseModel):
    """编辑已登记设备的名称、备注和分组。"""
    name: Optional[str] = Field(default=None, max_length=100)
    remark: Optional[str] = Field(default=None, max_length=200)
    group_name: Optional[str] = Field(default=None, max_length=50)
    enabled: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("设备名称不能为空")
        return value


class DeviceConnectRequest(BaseModel):
    """Request model for connecting a device."""
    device_id: str
    platform: PlatformType


class DeviceActionResponse(BaseModel):
    """Response model for device actions."""
    success: bool
    message: str
    device_id: str


class TcpIpConnectRequest(BaseModel):
    """Request model for TCP/IP connection."""
    ip_port: str


class WirelessConnectRequest(BaseModel):
    """Request model for enabling wireless connection."""
    device_id: str
    port: int = 5555


class DeviceIpResponse(BaseModel):
    """Response model for device IP address."""
    ip: Optional[str] = None
    interface: Optional[str] = None
