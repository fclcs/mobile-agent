"""设备登记表：自动收录在线手机，并保存用户可编辑的名称、备注和分组。"""

import time
from typing import Optional

from app.db import db
from app.schemas.device import DeviceRegisterRequest, DeviceUpdateRequest


def local_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _infer_connection_type(device_id: str, storage: Optional[str]) -> str:
    if storage:
        return storage
    return "tcpip" if ":" in device_id else "usb"


class DeviceRegistryService:
    """把 ADB 实时状态与持久化登记信息合并成设备列表。"""

    async def sync_and_merge(
        self, live_devices: list[dict], platform: Optional[str] = None
    ) -> list[dict]:
        """写入在线设备的硬件信息和最后在线时间，再与登记表合并。"""
        conn = await db.get_connection()
        now = local_now()
        live_by_id = {device["device_id"]: device for device in live_devices}

        cursor = await conn.execute("SELECT * FROM devices")
        registered = {row["device_id"]: dict(row) for row in await cursor.fetchall()}

        for device_id, info in live_by_id.items():
            record = registered.get(device_id)
            hardware = {
                "platform": info.get("platform") or "android",
                "model": info.get("model"),
                "manufacturer": info.get("manufacturer"),
                "os_version": info.get("os_version"),
                "screen_width": info.get("screen_width"),
                "screen_height": info.get("screen_height"),
                "connection_type": info.get("connection_type"),
                "last_seen_at": now,
            }
            if record is None:
                await conn.execute(
                    """INSERT OR IGNORE INTO devices
                       (device_id, name, remark, group_name, platform, model,
                        manufacturer, os_version, screen_width, screen_height,
                        connection_type, enabled, auto_registered, created_at,
                        updated_at, last_seen_at)
                       VALUES (?, ?, '', '', ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)""",
                    (
                        device_id,
                        info.get("name") or device_id,
                        hardware["platform"],
                        hardware["model"],
                        hardware["manufacturer"],
                        hardware["os_version"],
                        hardware["screen_width"],
                        hardware["screen_height"],
                        hardware["connection_type"],
                        now,
                        now,
                        now,
                    ),
                )
                registered[device_id] = {
                    "device_id": device_id,
                    "name": info.get("name") or device_id,
                    "remark": "",
                    "group_name": "",
                    "enabled": 1,
                    "auto_registered": 1,
                    **hardware,
                }
                continue

            # 只更新硬件字段和最后在线时间，保留用户编辑过的名称/备注/分组。
            await conn.execute(
                """UPDATE devices
                   SET platform = ?, model = ?, manufacturer = ?, os_version = ?,
                       screen_width = ?, screen_height = ?, connection_type = ?,
                       last_seen_at = ?, updated_at = ?
                   WHERE device_id = ?""",
                (
                    hardware["platform"],
                    hardware["model"],
                    hardware["manufacturer"],
                    hardware["os_version"],
                    hardware["screen_width"],
                    hardware["screen_height"],
                    hardware["connection_type"],
                    now,
                    now,
                    device_id,
                ),
            )
            record.update(hardware)
        await conn.commit()

        merged = []
        for device_id, record in registered.items():
            if platform and (record.get("platform") or "android") != platform:
                continue
            if record.get("enabled") == 0:
                continue
            merged.append(self._merged_dict(record, live_by_id.get(device_id)))
        merged.sort(key=lambda item: (
            0 if item["status"] == "connected" else 1,
            item.get("group_name") or "",
            item.get("name") or item["device_id"],
        ))
        return merged

    def _merged_dict(self, record: dict, live: Optional[dict]) -> dict:
        device_id = record["device_id"]
        info = live or {}
        connection_type = _infer_connection_type(
            device_id, info.get("connection_type") or record.get("connection_type")
        )
        ip = info.get("ip")
        if not ip and ":" in device_id:
            ip = device_id.rsplit(":", 1)[0]
        online = info.get("status") == "connected"
        if online:
            actions = (
                ["wireless", "screenshot", "apps", "launch", "detail", "edit"]
                if connection_type == "usb"
                else ["disconnect", "screenshot", "apps", "launch", "detail", "edit"]
            )
        else:
            actions = ["connect", "detail", "edit", "delete"]

        return {
            "device_id": device_id,
            "name": record.get("name") or info.get("name") or device_id,
            "platform": info.get("platform") or record.get("platform") or "android",
            "status": "connected" if online else "disconnected",
            "connection_type": connection_type,
            "ip": ip,
            "model": info.get("model") or record.get("model"),
            "manufacturer": info.get("manufacturer") or record.get("manufacturer"),
            "os_version": info.get("os_version") or record.get("os_version"),
            "screen_width": info.get("screen_width") or record.get("screen_width"),
            "screen_height": info.get("screen_height") or record.get("screen_height"),
            "battery_level": info.get("battery_level"),
            "device_type": info.get("device_type"),
            "android_sdk_version": info.get("android_sdk_version"),
            "last_seen_at": record.get("last_seen_at"),
            "remark": record.get("remark") or "",
            "group_name": record.get("group_name") or "",
            "registered": True,
            "auto_registered": bool(record.get("auto_registered", 1)),
            "available_actions": actions,
        }

    async def get_device_names(self, device_ids: list[str]) -> dict[str, str]:
        if not device_ids:
            return {}
        conn = await db.get_connection()
        placeholders = ",".join("?" for _ in device_ids)
        cursor = await conn.execute(
            f"SELECT device_id, name FROM devices WHERE device_id IN ({placeholders})",
            device_ids,
        )
        return {row["device_id"]: row["name"] for row in await cursor.fetchall()}

    async def get_registered(self, device_id: str) -> Optional[dict]:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        )
        row = await cursor.fetchone()
        return self._merged_dict(dict(row), None) if row else None

    async def register_device(self, data: DeviceRegisterRequest) -> dict:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT device_id FROM devices WHERE device_id = ?", (data.device_id,)
        )
        if await cursor.fetchone():
            raise ValueError("该设备已登记，可直接编辑名称或备注")

        now = local_now()
        connection_type = _infer_connection_type(
            data.device_id, data.connection_type.value if data.connection_type else None
        )
        await conn.execute(
            """INSERT INTO devices
               (device_id, name, remark, group_name, platform, connection_type,
                enabled, auto_registered, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?)""",
            (
                data.device_id,
                data.name or data.device_id,
                data.remark or "",
                data.group_name or "",
                data.platform.value,
                connection_type,
                now,
                now,
            ),
        )
        await conn.commit()
        return await self.get_registered(data.device_id)

    async def update_device(self, device_id: str, data: DeviceUpdateRequest) -> Optional[dict]:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        update = data.model_dump(exclude_unset=True)
        if "name" in update and update["name"] is not None:
            update["name"] = update["name"].strip()
        if "remark" in update and update["remark"] is not None:
            update["remark"] = update["remark"].strip()
        if "group_name" in update and update["group_name"] is not None:
            update["group_name"] = update["group_name"].strip()
        if "enabled" in update and update["enabled"] is not None:
            update["enabled"] = 1 if update["enabled"] else 0
        if update:
            # 用户手工编辑后不再视为“自动登记”。
            update["auto_registered"] = 0
            update["updated_at"] = local_now()
            assignments = ", ".join(f"{field} = ?" for field in update)
            await conn.execute(
                f"UPDATE devices SET {assignments} WHERE device_id = ?",
                [*update.values(), device_id],
            )
            await conn.commit()
        return await self.get_registered(device_id)

    async def delete_device(self, device_id: str) -> bool:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "DELETE FROM devices WHERE device_id = ?", (device_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0


device_registry_service = DeviceRegistryService()