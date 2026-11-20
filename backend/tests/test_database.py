"""Tests for the Database module."""

import pytest
from app.db import db, Database


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    conn = await db.get_connection()
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row["name"] for row in await cursor.fetchall()}
    expected = {"scripts", "tasks", "task_devices", "task_logs", "projects", "apks", "reports"}
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


@pytest.mark.asyncio
async def test_init_db_upgrades_legacy_workflow_runs_table(tmp_path):
    """旧库没有 batch_id/device_name 列时，启动迁移必须成功。"""
    import aiosqlite

    legacy_path = str(tmp_path / "legacy.db")
    async with aiosqlite.connect(legacy_path) as conn:
        await conn.executescript("""
            CREATE TABLE workflow_runs (
              run_id TEXT PRIMARY KEY,
              workflow_id TEXT NOT NULL,
              workflow_name TEXT NOT NULL,
              device_id TEXT NOT NULL,
              status TEXT DEFAULT 'pending',
              current_step INTEGER DEFAULT 0,
              total_steps INTEGER NOT NULL,
              error TEXT,
              created_at TEXT NOT NULL,
              started_at TEXT,
              completed_at TEXT
            );
        """)
        await conn.commit()

    db.db_path = legacy_path
    db._conn = None
    await db.init_db()

    conn = await db.get_connection()
    cursor = await conn.execute("PRAGMA table_info(workflow_runs)")
    columns = {row[1] for row in await cursor.fetchall()}
    assert {"batch_id", "device_name"}.issubset(columns)


@pytest.mark.asyncio
async def test_init_db_upgrades_legacy_workflows_table(tmp_path):
    """旧库 workflows 没有容错字段时，启动迁移必须补齐。"""
    import aiosqlite

    legacy_path = str(tmp_path / "legacy_workflows.db")
    async with aiosqlite.connect(legacy_path) as conn:
        await conn.executescript("""
            CREATE TABLE workflows (
              workflow_id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              description TEXT,
              script_ids TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT
            );
        """)
        await conn.commit()

    db.db_path = legacy_path
    db._conn = None
    await db.init_db()

    conn = await db.get_connection()
    cursor = await conn.execute("PRAGMA table_info(workflows)")
    columns = {row[1] for row in await cursor.fetchall()}
    assert {"continue_on_error", "step_timeout"}.issubset(columns)


@pytest.mark.asyncio
async def test_get_connection_returns_same_connection():
    conn1 = await db.get_connection()
    conn2 = await db.get_connection()
    assert conn1 is conn2


@pytest.mark.asyncio
async def test_close_resets_connection():
    conn = await db.get_connection()
    await db.close()
    assert db._conn is None
    conn_after = await db.get_connection()
    assert conn_after is not None
    assert conn_after is not conn


@pytest.mark.asyncio
async def test_database_custom_path(tmp_path):
    custom_path = str(tmp_path / "custom.db")
    d = Database(custom_path)
    assert d.db_path == custom_path
    assert d._conn is None
    await d.close()
