"""Persistent, sequential script workflows with per-step screenshots."""

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.config import settings
from app.db import db
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services.device_registry_service import DeviceRegistryService
from app.services.device_service import DeviceService
from app.services.model_config_service import ModelConfigService
from app.services.vision_model_config_service import VisionModelConfigService
from app.services.script_service import ScriptService
from app.services.update_guard import start_update_guard

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def local_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _adb_state(device_id: str) -> str:
    """只读查询 ADB 状态；任何异常都按不可用处理。"""
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "get-state"],
            capture_output=True,
            check=False,
            timeout=15,
        )
    except Exception:  # noqa: BLE001
        return "error"
    return result.stdout.decode("utf-8", errors="replace").strip() or "unknown"


def _wait_device_ready(device_id: str, timeout: float = 90.0) -> bool:
    """步骤启动前的设备门槛：只在有界窗口内重连，超时返回 False。

    2026-11-16 手机2 的 FRP 隧道退出后约 48 秒才恢复；上一步已经因断线失败，
    下一步却立即启动，只能再失败一次。这里先等设备真的可用再拉起脚本进程。
    """
    deadline = time.monotonic() + timeout
    delay = 1.0
    while True:
        if _adb_state(device_id) == "device":
            return True
        if time.monotonic() >= deadline:
            return False
        try:
            subprocess.run(
                ["adb", "connect", device_id],
                capture_output=True,
                check=False,
                timeout=15,
            )
        except Exception:  # noqa: BLE001
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(delay, remaining))
        delay = min(delay + 1.0, 5.0)


class WorkflowService:
    # 运行中的脚本进程句柄与中断标记，类级别共享，保证 API 实例和
    # 执行实例（可能来自不同 WorkflowService 对象）看到同一份状态。
    _run_processes: dict[str, subprocess.Popen] = {}
    _cancel_requested: set[str] = set()

    INTERRUPTIBLE_STATUSES = ("pending", "executing")

    def __init__(self):
        configured_dir = settings.workflow_screenshot_dir
        self.screenshot_dir = (
            Path(configured_dir).expanduser()
            if configured_dir
            else PROJECT_ROOT / "workflow_screenshots"
        )
        if not self.screenshot_dir.is_absolute():
            self.screenshot_dir = PROJECT_ROOT / self.screenshot_dir
        self.script_service = ScriptService()
        self.device_service = DeviceService()
        self.device_registry = DeviceRegistryService()

    async def _validate_scripts(self, script_ids: list[str]) -> None:
        for script_id in script_ids:
            if await self.script_service.get_script(script_id) is None:
                raise ValueError(f"脚本不存在：{script_id}")

    def _workflow_dict(self, row, scripts: list[dict]) -> dict:
        return {
            "workflow_id": row["workflow_id"],
            "name": row["name"],
            "description": row["description"] or "",
            "script_ids": json.loads(row["script_ids"]),
            "continue_on_error": bool(row["continue_on_error"]),
            "step_timeout": row["step_timeout"] or 0,
            "scripts": scripts,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def _scripts_for_workflow(self, script_ids: list[str]) -> list[dict]:
        scripts = []
        for script_id in script_ids:
            script = await self.script_service.get_script(script_id)
            scripts.append({
                "script_id": script_id,
                "name": script.name if script else "脚本已删除",
                "platform": script.platform if script else "unknown",
            })
        return scripts

    async def create_workflow(self, data: WorkflowCreate) -> dict:
        await self._validate_scripts(data.script_ids)
        workflow_id = f"workflow_{time.time_ns()}"
        now = local_now()
        conn = await db.get_connection()
        await conn.execute(
            """INSERT INTO workflows
               (workflow_id, name, description, script_ids,
                continue_on_error, step_timeout, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_id,
                data.name,
                data.description,
                json.dumps(data.script_ids),
                1 if data.continue_on_error else 0,
                data.step_timeout,
                now,
                now,
            ),
        )
        await conn.commit()
        return await self.get_workflow(workflow_id)

    async def get_workflow(self, workflow_id: str) -> dict | None:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        script_ids = json.loads(row["script_ids"])
        scripts = await self._scripts_for_workflow(script_ids)
        return self._workflow_dict(row, scripts)

    async def list_workflows(self) -> list[dict]:
        conn = await db.get_connection()
        cursor = await conn.execute("SELECT * FROM workflows ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        workflows = []
        for row in rows:
            script_ids = json.loads(row["script_ids"])
            scripts = await self._scripts_for_workflow(script_ids)
            workflows.append(self._workflow_dict(row, scripts))
        return workflows

    async def update_workflow(self, workflow_id: str, data: WorkflowUpdate) -> dict | None:
        existing = await self.get_workflow(workflow_id)
        if existing is None:
            return None
        update = data.model_dump(exclude_unset=True)
        if "script_ids" in update:
            await self._validate_scripts(update["script_ids"])
            update["script_ids"] = json.dumps(update["script_ids"])
        if "name" in update:
            update["name"] = update["name"].strip()
            if not update["name"]:
                raise ValueError("流程名称不能为空")
        if update:
            update["updated_at"] = local_now()
            assignments = ", ".join(f"{field} = ?" for field in update)
            conn = await db.get_connection()
            await conn.execute(
                f"UPDATE workflows SET {assignments} WHERE workflow_id = ?",
                [*update.values(), workflow_id],
            )
            await conn.commit()
        return await self.get_workflow(workflow_id)

    async def delete_workflow(self, workflow_id: str) -> bool:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "DELETE FROM workflows WHERE workflow_id = ?", (workflow_id,)
        )
        await conn.commit()
        return cursor.rowcount > 0

    async def _insert_run(
        self,
        workflow: dict,
        device_id: str,
        batch_id: str | None = None,
        device_name: str | None = None,
    ) -> str:
        conn = await db.get_connection()
        run_id = f"run_{time.time_ns()}"
        now = local_now()
        await conn.execute(
            """INSERT INTO workflow_runs
               (run_id, workflow_id, workflow_name, device_id, device_name,
                batch_id, status, current_step, total_steps, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?)""",
            (
                run_id,
                workflow["workflow_id"],
                workflow["name"],
                device_id,
                device_name or device_id,
                batch_id,
                len(workflow["scripts"]),
                now,
            ),
        )
        for index, script in enumerate(workflow["scripts"], start=1):
            await conn.execute(
                """INSERT INTO workflow_step_runs
                   (step_id, run_id, step_order, script_id, script_name, status)
                   VALUES (?, ?, ?, ?, ?, 'pending')""",
                (
                    f"step_{time.time_ns()}_{index}",
                    run_id,
                    index,
                    script["script_id"],
                    script["name"],
                ),
            )
        return run_id

    async def _busy_devices(self, device_ids: list[str]) -> list[str]:
        conn = await db.get_connection()
        placeholders = ",".join("?" for _ in device_ids)
        cursor = await conn.execute(
            f"""SELECT DISTINCT device_id FROM workflow_runs
                WHERE device_id IN ({placeholders})
                  AND status IN ('pending', 'executing')""",
            device_ids,
        )
        return [row["device_id"] for row in await cursor.fetchall()]

    async def create_run(self, workflow_id: str, device_id: str) -> str:
        workflow = await self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError("流程不存在")
        if await self._busy_devices([device_id]):
            raise ValueError("该手机已有流程正在执行，请等待完成后再启动新流程")
        run_id = await self._insert_run(workflow, device_id)
        conn = await db.get_connection()
        await conn.commit()
        return run_id

    async def create_runs(self, workflow_id: str, device_ids: list[str]) -> dict:
        """为多台手机各创建一个独立 run，共享 batch_id。

        仅允许当前 ADB 在线的手机；离线 TCP/IP 手机会先自动重连一次。
        """
        workflow = await self.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError("流程不存在")
        if not device_ids:
            raise ValueError("请至少选择一台手机")

        online = set(await asyncio.to_thread(self.device_service.list_online_device_ids))
        missing = [device_id for device_id in device_ids if device_id not in online]
        if missing:
            for device_id in missing:
                if ":" in device_id:
                    await asyncio.to_thread(self.device_service.connect_tcpip, device_id)
            if any(":" in device_id for device_id in missing):
                await asyncio.sleep(1)
                online = set(
                    await asyncio.to_thread(self.device_service.list_online_device_ids)
                )
            missing = [device_id for device_id in device_ids if device_id not in online]
        if missing:
            raise ValueError(f"以下手机不在线，无法启动流程：{'、'.join(missing)}")

        busy = await self._busy_devices(device_ids)
        if busy:
            raise ValueError(f"以下手机已有流程正在执行：{'、'.join(busy)}")

        names = await self.device_registry.get_device_names(device_ids)
        batch_id = f"batch_{time.time_ns()}"
        run_ids = [
            await self._insert_run(
                workflow, device_id, batch_id, names.get(device_id)
            )
            for device_id in device_ids
        ]
        conn = await db.get_connection()
        await conn.commit()
        return {
            "batch_id": batch_id,
            "run_ids": run_ids,
            "device_ids": device_ids,
        }

    def _run_dict(self, row, steps: list[dict] | None = None) -> dict:
        result = {
            "run_id": row["run_id"],
            "workflow_id": row["workflow_id"],
            "workflow_name": row["workflow_name"],
            "device_id": row["device_id"],
            "device_name": row["device_name"] or row["device_id"],
            "batch_id": row["batch_id"],
            "status": row["status"],
            "current_step": row["current_step"],
            "total_steps": row["total_steps"],
            "error": row["error"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }
        if steps is not None:
            result["steps"] = steps
        else:
            result["steps"] = []
        return result

    def _step_dict(self, row) -> dict:
        screenshot_path = row["screenshot_path"]
        return {
            "step_id": row["step_id"],
            "run_id": row["run_id"],
            "step_order": row["step_order"],
            "script_id": row["script_id"],
            "script_name": row["script_name"],
            "status": row["status"],
            "exit_code": row["exit_code"],
            "output": row["output"] or "",
            "error": row["error"],
            "screenshot_path": (
                str(self.screenshot_dir.resolve() / screenshot_path)
                if screenshot_path else None
            ),
            "screenshot_url": (
                f"/api/v1/workflows/screenshots/{row['step_id']}/image"
                if screenshot_path else None
            ),
            "captured_at": row["captured_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }

    async def get_run(self, run_id: str) -> dict | None:
        conn = await db.get_connection()
        cursor = await conn.execute("SELECT * FROM workflow_runs WHERE run_id = ?", (run_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        cursor = await conn.execute(
            """SELECT * FROM workflow_step_runs
               WHERE run_id = ? ORDER BY step_order""",
            (run_id,),
        )
        steps = [self._step_dict(step) for step in await cursor.fetchall()]
        return self._run_dict(row, steps)

    async def list_runs(self, workflow_id: str | None = None) -> list[dict]:
        conn = await db.get_connection()
        if workflow_id:
            cursor = await conn.execute(
                """SELECT * FROM workflow_runs WHERE workflow_id = ?
                   ORDER BY created_at DESC LIMIT 100""",
                (workflow_id,),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM workflow_runs ORDER BY created_at DESC LIMIT 100"
            )
        return [self._run_dict(row) for row in await cursor.fetchall()]

    async def _build_environment(self, run_id: str, step_id: str, device_id: str) -> dict:
        env = os.environ.copy()
        model_config = await ModelConfigService().get_default_config()
        if model_config:
            env.update({
                "PHONE_AGENT_BASE_URL": model_config.base_url or "",
                "PHONE_AGENT_MODEL": model_config.model_name,
                "PHONE_AGENT_API_KEY": model_config.api_key,
                "PHONE_AGENT_PROVIDER": model_config.provider.value,
                "PHONE_AGENT_VISION_MODEL": model_config.vision_model or "",
                "PHONE_AGENT_DISABLE_THINKING": "1" if model_config.disable_thinking else "0",
            })
        # 视觉识别独立配置优先；未配置时保留上面的“共用操作模型”回落行为。
        vision_env = await VisionModelConfigService().env()
        if vision_env:
            env.update(vision_env)
        env.update({
            "PHONE_AGENT_DEVICE_ID": device_id,
            "DEVICE_SERIAL": device_id,
            "PHONE_AGENT_WORKFLOW_RUN_ID": run_id,
            "PHONE_AGENT_WORKFLOW_STEP_ID": step_id,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(
                filter(None, [str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
            ),
        })
        return env

    async def _execute_script(
        self, run: dict, step: dict, timeout: int = 0
    ) -> tuple[int, str]:
        # 中断可能发生在“步骤标记为执行中”与“进程真正启动”之间。
        # 这里只看内存标记，避免在本方法里多一次数据库访问。
        if run["run_id"] in self._cancel_requested:
            return -1, "已被用户中断，脚本未启动"
        script = await self.script_service.get_script(step["script_id"])
        if script is None:
            raise RuntimeError(f"脚本不存在或已被删除：{step['script_name']}")
        env = await self._build_environment(
            run["run_id"], step["step_id"], run["device_id"]
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", encoding="utf-8", delete=False
        ) as temp_script:
            temp_script.write(script.content)
            script_path = Path(temp_script.name)
        guard = start_update_guard(run["device_id"], f"步骤{step['step_order']}")
        # 用 Popen 而不是 subprocess.run：句柄要留给 cancel_run，中断时才能
        # 真正结束脚本进程；communicate 仍在线程里跑，兼容 Selector 事件循环。
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._run_processes[run["run_id"]] = process
        try:
            try:
                stdout, stderr = await asyncio.to_thread(
                    process.communicate, timeout=timeout or None
                )
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = await asyncio.to_thread(process.communicate)
                output = "\n".join(
                    part.decode("utf-8", errors="replace")
                    for part in (stdout or b"", stderr or b"") if part
                )
                note = f"脚本执行超时（超过 {timeout} 秒），已强制结束。"
                print(note, flush=True)
                return 124, f"{output}\n{note}".strip()
            output = "\n".join(
                part.decode("utf-8", errors="replace")
                for part in (stdout or b"", stderr or b"") if part
            )
            return process.returncode, output
        finally:
            if self._run_processes.get(run["run_id"]) is process:
                self._run_processes.pop(run["run_id"], None)
            if guard is not None:
                guard.stop()
            script_path.unlink(missing_ok=True)

    async def _capture_screenshot(
        self, run_id: str, step: dict, device_id: str
    ) -> tuple[str, str]:
        encoded = None
        state = "device"
        waited = False
        for attempt in range(3):
            encoded = await asyncio.to_thread(self.device_service.get_screenshot, device_id)
            if encoded:
                break
            state = await asyncio.to_thread(_adb_state, device_id)
            # 设备刚好断开时补一次短重连窗口再试，避免把“离线”记成图片错误；
            # 只等一次，避免整步预算被反复重连耗尽。
            if attempt < 2 and not waited:
                waited = True
                await asyncio.to_thread(_wait_device_ready, device_id, 30.0)
        if not encoded:
            if state != "device":
                raise RuntimeError(
                    f"无法从设备 {device_id} 获取截图"
                    "（设备离线，ADB/FRP 通道不可用，不是图片格式错误）"
                )
            raise RuntimeError(f"无法从设备 {device_id} 获取截图")
        png_data = base64.b64decode(encoded, validate=True)
        if not png_data.startswith(PNG_MAGIC):
            raise RuntimeError("设备截图不是有效的 PNG 图片")
        captured_at = local_now()
        relative_path = Path(time.strftime("%Y-%m-%d")) / run_id / (
            f"step_{step['step_order']:02d}_{step['step_id']}.png"
        )
        destination = self.screenshot_dir.resolve() / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(destination.write_bytes, png_data)
        return relative_path.as_posix(), captured_at

    async def _run_status(self, run_id: str) -> str | None:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT status FROM workflow_runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return row["status"] if row else None

    async def _is_cancelled(self, run_id: str) -> bool:
        if run_id in self._cancel_requested:
            return True
        return await self._run_status(run_id) == "cancelled"

    async def _finish_cancelled(
        self, run_id: str, step: dict | None = None, conn=None,
        reason: str = "已被用户中断",
    ) -> None:
        """把正在执行的步骤标记为已中断，等待中的步骤标记为跳过。"""
        conn = conn or await db.get_connection()
        now = local_now()
        if step is not None:
            await conn.execute(
                """UPDATE workflow_step_runs
                   SET status = 'cancelled', error = ?, completed_at = ?
                   WHERE step_id = ? AND status IN ('executing', 'pending')""",
                (reason, now, step["step_id"]),
            )
        else:
            await conn.execute(
                """UPDATE workflow_step_runs
                   SET status = 'cancelled', error = ?, completed_at = ?
                   WHERE run_id = ? AND status = 'executing'""",
                (reason, now, run_id),
            )
        await conn.execute(
            """UPDATE workflow_step_runs SET status = 'skipped'
               WHERE run_id = ? AND status = 'pending'""",
            (run_id,),
        )
        await conn.execute(
            """UPDATE workflow_runs SET status = 'cancelled', error = ?, completed_at = ?
               WHERE run_id = ?""",
            (reason, now, run_id),
        )
        await conn.commit()
        self._cancel_requested.discard(run_id)

    async def reset_orphaned_runs(self) -> int:
        """服务重启后重置遗留的 pending/executing 记录。

        脚本进程随服务退出而结束，这些记录已不可能再有进展；不重置会一直
        占用手机（busy 判定），也无法再启动新流程。
        """
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT run_id FROM workflow_runs WHERE status IN ('pending', 'executing')"
        )
        run_ids = [row["run_id"] for row in await cursor.fetchall()]
        reason = "执行进程已不存在（服务重启或手机断开），已自动重置"
        for run_id in run_ids:
            await self._finish_cancelled(run_id, conn=conn, reason=reason)
        if run_ids:
            print(f"已重置 {len(run_ids)} 条遗留的流程执行记录", flush=True)
        return len(run_ids)

    async def cancel_run(self, run_id: str) -> dict | None:
        """中断运行中的流程执行：结束脚本进程并立即更新状态。

        只支持 pending / executing；已结束的记录不会被改写。
        """
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT status FROM workflow_runs WHERE run_id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if row["status"] not in self.INTERRUPTIBLE_STATUSES:
            raise ValueError("该执行记录已结束，不能中断")
        if run_id in self._cancel_requested:
            raise ValueError("该执行记录正在中断，请勿重复操作")

        self._cancel_requested.add(run_id)
        process = self._run_processes.get(run_id)
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        await self._finish_cancelled(run_id)
        return await self.get_run(run_id)

    async def delete_runs(self, run_ids: list[str]) -> dict:
        """删除执行历史记录（含步骤记录和截图文件）。

        运行中的记录必须先中断，避免删除仍在写入的记录。
        """
        unique_ids: list[str] = []
        for run_id in run_ids:
            value = (run_id or "").strip()
            if value and value not in unique_ids:
                unique_ids.append(value)
        if not unique_ids:
            raise ValueError("请至少选择一条执行记录")

        conn = await db.get_connection()
        placeholders = ",".join("?" for _ in unique_ids)
        cursor = await conn.execute(
            f"SELECT run_id, status FROM workflow_runs WHERE run_id IN ({placeholders})",
            unique_ids,
        )
        rows = await cursor.fetchall()
        if not rows:
            return {"deleted": 0, "run_ids": [], "screenshot_files": 0}

        active = [
            row["run_id"] for row in rows
            if row["status"] in self.INTERRUPTIBLE_STATUSES
        ]
        if active:
            raise ValueError(
                f"有 {len(active)} 条执行记录仍在运行，请先中断后再删除"
            )

        existing_ids = [row["run_id"] for row in rows]
        existing_placeholders = ",".join("?" for _ in existing_ids)
        cursor = await conn.execute(
            f"""SELECT screenshot_path FROM workflow_step_runs
                WHERE run_id IN ({existing_placeholders})""",
            existing_ids,
        )
        screenshot_paths = [
            row["screenshot_path"] for row in await cursor.fetchall()
            if row["screenshot_path"]
        ]

        await conn.execute(
            f"DELETE FROM workflow_step_runs WHERE run_id IN ({existing_placeholders})",
            existing_ids,
        )
        await conn.execute(
            f"DELETE FROM workflow_runs WHERE run_id IN ({existing_placeholders})",
            existing_ids,
        )
        await conn.commit()
        for run_id in existing_ids:
            self._cancel_requested.discard(run_id)

        root = self.screenshot_dir.resolve()
        removed_files = 0
        removed_dirs: set[Path] = set()
        for relative in screenshot_paths:
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                continue
            try:
                path.unlink(missing_ok=True)
                removed_files += 1
                removed_dirs.add(path.parent)
            except OSError:
                continue
        for directory in removed_dirs:
            for candidate in (directory, directory.parent):
                try:
                    candidate.rmdir()
                except OSError:
                    pass

        return {
            "deleted": len(existing_ids),
            "run_ids": existing_ids,
            "screenshot_files": removed_files,
        }

    async def execute_run(self, run_id: str) -> None:
        run = await self.get_run(run_id)
        if run is None:
            return
        # 创建与启动之间被中断：直接按已中断收尾，不再执行脚本。
        if run["status"] == "cancelled" or await self._is_cancelled(run_id):
            await self._finish_cancelled(run_id)
            return
        conn = await db.get_connection()
        # 容错策略按流程保存：失败后是否继续、单脚本超时秒数。
        cursor = await conn.execute(
            "SELECT continue_on_error, step_timeout FROM workflows WHERE workflow_id = ?",
            (run["workflow_id"],),
        )
        settings = await cursor.fetchone()
        continue_on_error = bool(settings["continue_on_error"]) if settings else False
        step_timeout = (settings["step_timeout"] or 0) if settings else 0

        now = local_now()
        await conn.execute(
            "UPDATE workflow_runs SET status = 'executing', started_at = ? WHERE run_id = ?",
            (now, run_id),
        )
        await conn.commit()

        failed_steps: list[str] = []
        try:
            for step in run["steps"]:
                # 每一步开始前检查中断：被中断后不再启动后续脚本。
                if await self._is_cancelled(run_id):
                    await self._finish_cancelled(run_id)
                    return
                now = local_now()
                await conn.execute(
                    """UPDATE workflow_step_runs
                       SET status = 'executing', started_at = ? WHERE step_id = ?""",
                    (now, step["step_id"]),
                )
                await conn.execute(
                    "UPDATE workflow_runs SET current_step = ? WHERE run_id = ?",
                    (step["step_order"], run_id),
                )
                await conn.commit()

                exit_code = None
                output = ""
                errors = []
                try:
                    # 上一步可能因 FRP/ADB 断线失败；先等设备真的回来再启动脚本。
                    if not await asyncio.to_thread(
                        _wait_device_ready, run["device_id"], 90.0
                    ):
                        raise RuntimeError(
                            "设备未就绪：ADB 通道在 90 秒恢复窗口内未恢复，"
                            "已跳过该步骤，未启动脚本"
                        )
                    exit_code, output = await self._execute_script(
                        run, step, step_timeout
                    )
                    if exit_code != 0:
                        errors.append(f"脚本退出码为 {exit_code}")
                # 启动或环境异常也要留下现场截图，并终止后续步骤。
                except Exception as exc:  # noqa: BLE001
                    message = (
                        f"{type(exc).__name__}: {exc}"
                        if str(exc) else type(exc).__name__
                    )
                    output = message
                    errors.append(message)

                # 脚本被中断结束（进程被 terminate，退出码非 0）：
                # 不再补截图，也不按失败收尾，直接标记为已中断。
                if await self._is_cancelled(run_id):
                    await self._finish_cancelled(run_id, step, conn)
                    return

                screenshot_path = None
                captured_at = None
                try:
                    screenshot_path, captured_at = await self._capture_screenshot(
                        run_id, step, run["device_id"]
                    )
                except (OSError, ValueError, RuntimeError) as exc:
                    errors.append(f"步骤截图保存失败：{exc}")

                succeeded = exit_code == 0 and not errors
                now = local_now()
                error = "；".join(errors) if errors else None
                await conn.execute(
                    """UPDATE workflow_step_runs
                       SET status = ?, exit_code = ?, output = ?, error = ?,
                           screenshot_path = ?, captured_at = ?, completed_at = ?
                       WHERE step_id = ?""",
                    (
                        "completed" if succeeded else "failed",
                        exit_code,
                        output,
                        error,
                        screenshot_path,
                        captured_at,
                        now,
                        step["step_id"],
                    ),
                )
                await conn.commit()

                if not succeeded:
                    if continue_on_error:
                        # 只跳过当前脚本，后续脚本继续执行；流程最终标记为部分失败。
                        failed_steps.append(
                            f"第 {step['step_order']} 步「{step['script_name']}」：{error}"
                        )
                        continue
                    await conn.execute(
                        """UPDATE workflow_step_runs SET status = 'skipped'
                           WHERE run_id = ? AND status = 'pending'""",
                        (run_id,),
                    )
                    await conn.execute(
                        """UPDATE workflow_runs
                           SET status = 'failed', error = ?, completed_at = ? WHERE run_id = ?""",
                        (f"第 {step['step_order']} 步失败：{error}", now, run_id),
                    )
                    await conn.commit()
                    return

            if await self._is_cancelled(run_id):
                await self._finish_cancelled(run_id, conn=conn)
                return

            await conn.execute(
                """UPDATE workflow_runs
                   SET status = ?, error = ?, completed_at = ? WHERE run_id = ?""",
                (
                    "partial" if failed_steps else "completed",
                    "；".join(failed_steps) or None,
                    local_now(),
                    run_id,
                ),
            )
            await conn.commit()
        except Exception as exc:
            # 中断导致进程通信异常时按中断收尾，不要误记成流程失败。
            if await self._is_cancelled(run_id):
                await self._finish_cancelled(run_id, conn=conn)
                return
            await conn.execute(
                """UPDATE workflow_runs
                   SET status = 'failed', error = ?, completed_at = ? WHERE run_id = ?""",
                (f"流程执行器异常：{exc}", local_now(), run_id),
            )
            await conn.commit()
            raise

    async def list_screenshots(self, workflow_id: str | None = None) -> list[dict]:
        conn = await db.get_connection()
        where = "s.screenshot_path IS NOT NULL"
        params = []
        if workflow_id:
            where += " AND r.workflow_id = ?"
            params.append(workflow_id)
        cursor = await conn.execute(
            f"""SELECT s.*, r.workflow_id, r.workflow_name, r.device_id
                FROM workflow_step_runs s
                JOIN workflow_runs r ON r.run_id = s.run_id
                WHERE {where}
                ORDER BY s.captured_at DESC, s.step_id DESC LIMIT 200""",
            params,
        )
        records = []
        for row in await cursor.fetchall():
            records.append({
                "step_id": row["step_id"],
                "run_id": row["run_id"],
                "workflow_id": row["workflow_id"],
                "workflow_name": row["workflow_name"],
                "step_order": row["step_order"],
                "script_id": row["script_id"],
                "script_name": row["script_name"],
                "status": row["status"],
                "device_id": row["device_id"],
                "captured_at": row["captured_at"],
                "screenshot_path": str(
                    self.screenshot_dir.resolve() / row["screenshot_path"]
                ),
                "screenshot_url": (
                    f"/api/v1/workflows/screenshots/{row['step_id']}/image"
                ),
            })
        return records

    async def get_screenshot_file(self, step_id: str) -> Path:
        conn = await db.get_connection()
        cursor = await conn.execute(
            "SELECT screenshot_path FROM workflow_step_runs WHERE step_id = ?",
            (step_id,),
        )
        row = await cursor.fetchone()
        if row is None or not row["screenshot_path"]:
            raise FileNotFoundError("截图记录不存在")
        root = self.screenshot_dir.resolve()
        candidate = (root / row["screenshot_path"]).resolve()
        if root != candidate.parent and root not in candidate.parents:
            raise PermissionError("截图路径超出允许的目录")
        if not candidate.is_file():
            raise FileNotFoundError("截图文件不存在")
        return candidate
