"""SQLite database module with aiosqlite."""

import aiosqlite
from pathlib import Path


class Database:
    def __init__(self, db_path: str = "./app.db"):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init_db(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS scripts (
              script_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              content TEXT NOT NULL,
              script_type TEXT NOT NULL,
              platform TEXT NOT NULL,
              project_id TEXT,
              description TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT,
              version INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS tasks (
              task_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              task_type TEXT DEFAULT 'functional',
              platform TEXT DEFAULT 'android',
              status TEXT DEFAULT 'pending',
              script_id TEXT REFERENCES scripts(script_id),
              device_id TEXT,
              apk_id TEXT,
              model_config_id TEXT,
              description TEXT,
              progress INTEGER DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT,
              started_at TEXT,
              completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS task_devices (
              task_id TEXT REFERENCES tasks(task_id),
              device_id TEXT,
              PRIMARY KEY (task_id, device_id)
            );

            CREATE TABLE IF NOT EXISTS task_logs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id TEXT REFERENCES tasks(task_id),
              timestamp TEXT,
              level TEXT,
              message TEXT
            );

            CREATE TABLE IF NOT EXISTS projects (
              project_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT,
              platform TEXT DEFAULT 'android',
              created_at TEXT NOT NULL,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS apks (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              original_filename TEXT,
              package_name TEXT,
              version TEXT,
              file_size INTEGER,
              file_path TEXT,
              upload_time TEXT NOT NULL,
              status TEXT DEFAULT 'uploaded'
            );

            CREATE TABLE IF NOT EXISTS reports (
              task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
              name TEXT,
              device_name TEXT,
              script_name TEXT,
              script_type TEXT,
              status TEXT,
              started_at TEXT,
              completed_at TEXT,
              duration_seconds INTEGER,
              html_content TEXT,
              summary TEXT,
              total_steps INTEGER,
              passed_steps INTEGER,
              failed_steps INTEGER,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS model_configs (
              config_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              provider TEXT NOT NULL, -- 'openai' or 'anthropic'
              base_url TEXT,
              api_key TEXT NOT NULL,
              model_name TEXT NOT NULL,
              vision_model TEXT,
              is_default INTEGER DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT
            );

            -- 脚本视觉识别用的独立模型配置（单行）。与 model_configs（手机操作模型）
            -- 完全解耦：可以一套是智谱 PhoneAgent，另一套是别家多模态/方舟。
            CREATE TABLE IF NOT EXISTS vision_model_config (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              provider TEXT NOT NULL DEFAULT 'openai',
              base_url TEXT,
              api_key TEXT,
              model_name TEXT,
              disable_thinking INTEGER DEFAULT 0,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS workflows (
              workflow_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT,
              script_ids TEXT NOT NULL,
              continue_on_error INTEGER DEFAULT 0,
              step_timeout INTEGER DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS devices (
              device_id TEXT PRIMARY KEY,
              name TEXT,
              remark TEXT,
              group_name TEXT,
              platform TEXT DEFAULT 'android',
              model TEXT,
              manufacturer TEXT,
              os_version TEXT,
              screen_width INTEGER,
              screen_height INTEGER,
              connection_type TEXT,
              enabled INTEGER DEFAULT 1,
              auto_registered INTEGER DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT,
              last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS workflow_runs (
              run_id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL,
              workflow_name TEXT NOT NULL,
              device_id TEXT NOT NULL,
              device_name TEXT,
              batch_id TEXT,
              status TEXT DEFAULT 'pending',
              current_step INTEGER DEFAULT 0,
              total_steps INTEGER NOT NULL,
              error TEXT,
              created_at TEXT NOT NULL,
              started_at TEXT,
              completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS workflow_step_runs (
              step_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL,
              step_order INTEGER NOT NULL,
              script_id TEXT NOT NULL,
              script_name TEXT NOT NULL,
              status TEXT DEFAULT 'pending',
              exit_code INTEGER,
              output TEXT,
              error TEXT,
              screenshot_path TEXT,
              captured_at TEXT,
              started_at TEXT,
              completed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow
              ON workflow_runs(workflow_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_run
              ON workflow_step_runs(run_id, step_order);
            CREATE INDEX IF NOT EXISTS idx_workflow_step_runs_screenshots
              ON workflow_step_runs(captured_at);
        """)
        
        # Add missing columns for backward compatibility
        await self._add_missing_columns()
        
        await self._conn.commit()
    
    async def _add_missing_columns(self):
        """Add missing columns to existing tables for backward compatibility."""
        # Check and add model_config_id column to tasks table
        cursor = await self._conn.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in await cursor.fetchall()]

        if 'model_config_id' not in columns:
            await self._conn.execute("ALTER TABLE tasks ADD COLUMN model_config_id TEXT")

        # 视觉识别模型（供脚本的 vision_ads 使用）；留空时按 Base URL 自动推断。
        cursor = await self._conn.execute("PRAGMA table_info(model_configs)")
        model_columns = [row[1] for row in await cursor.fetchall()]
        if 'vision_model' not in model_columns:
            await self._conn.execute("ALTER TABLE model_configs ADD COLUMN vision_model TEXT")

        # 流程容错：单步失败后是否继续后续脚本，以及单脚本超时秒数（0=不限）。
        cursor = await self._conn.execute("PRAGMA table_info(workflows)")
        workflow_columns = [row[1] for row in await cursor.fetchall()]
        if 'continue_on_error' not in workflow_columns:
            await self._conn.execute(
                "ALTER TABLE workflows ADD COLUMN continue_on_error INTEGER DEFAULT 0"
            )
        if 'step_timeout' not in workflow_columns:
            await self._conn.execute(
                "ALTER TABLE workflows ADD COLUMN step_timeout INTEGER DEFAULT 0"
            )

        # 多手机批量执行：同一次启动的多个 run 共享 batch_id，并保存手机显示名。
        cursor = await self._conn.execute("PRAGMA table_info(workflow_runs)")
        run_columns = [row[1] for row in await cursor.fetchall()]
        if 'batch_id' not in run_columns:
            await self._conn.execute("ALTER TABLE workflow_runs ADD COLUMN batch_id TEXT")
        if 'device_name' not in run_columns:
            await self._conn.execute("ALTER TABLE workflow_runs ADD COLUMN device_name TEXT")
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_runs_device_status "
            "ON workflow_runs(device_id, status)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workflow_runs_batch "
            "ON workflow_runs(batch_id)"
        )

    async def get_connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            await self.init_db()
        return self._conn

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None


db = Database()
