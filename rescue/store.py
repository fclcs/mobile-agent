"""oag-rescue 的 SQLite 存储（单文件、WAL、单进程写）。

与平台 app.db 完全分开：救援服务是唯一写入者，平台只通过 HTTP 读记录。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

from . import config

_LOCK = threading.RLock()
_conn: sqlite3.Connection | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS rescue_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  enabled INTEGER NOT NULL DEFAULT 0,
  provider TEXT NOT NULL DEFAULT 'openai',
  base_url TEXT NOT NULL DEFAULT '',
  model_name TEXT NOT NULL DEFAULT '',
  vision_model TEXT NOT NULL DEFAULT '',
  vision_base_url TEXT NOT NULL DEFAULT '',
  vision_api_key TEXT NOT NULL DEFAULT '',
  vision_disable_thinking INTEGER NOT NULL DEFAULT 0,
  api_key TEXT NOT NULL DEFAULT '',
  max_seconds INTEGER NOT NULL DEFAULT 150,
  max_vision_calls INTEGER NOT NULL DEFAULT 3,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS rescue_runs (
  rescue_id TEXT PRIMARY KEY,
  run_id TEXT,
  step_id TEXT,
  device_id TEXT,
  script_name TEXT,
  app TEXT,
  package TEXT,
  goal TEXT,
  state_json TEXT,
  expected TEXT,
  status TEXT NOT NULL,
  handler TEXT,
  resolved INTEGER NOT NULL DEFAULT 0,
  vision_calls INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  evidence TEXT,
  state_patch TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_rescue_runs_step ON rescue_runs(run_id, step_id);
CREATE INDEX IF NOT EXISTS idx_rescue_runs_created ON rescue_runs(created_at);
CREATE TABLE IF NOT EXISTS rescue_steps (
  rescue_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  phase TEXT NOT NULL,
  detail TEXT,
  ok INTEGER,
  screenshot TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (rescue_id, seq)
);
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def connect() -> sqlite3.Connection:
    global _conn
    with _LOCK:
        if _conn is None:
            os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
            _conn = sqlite3.connect(config.DB_PATH, timeout=15, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA synchronous=NORMAL")
            _conn.executescript(SCHEMA)
            _add_missing_columns(_conn)
            _conn.execute("INSERT OR IGNORE INTO rescue_settings (id) VALUES (1)")
            _conn.commit()
        return _conn


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """旧库升级：CREATE TABLE IF NOT EXISTS 不会补列，这里逐列补。"""
    wanted = {
        "rescue_runs": {"package": "TEXT"},
        "rescue_settings": {
            "max_vision_calls": "INTEGER NOT NULL DEFAULT 3",
            "vision_base_url": "TEXT NOT NULL DEFAULT ''",
            "vision_api_key": "TEXT NOT NULL DEFAULT ''",
            "vision_disable_thinking": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    for table, columns in wanted.items():
        existing = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, ddl))


def load_settings() -> config.RescueSettings:
    row = connect().execute("SELECT * FROM rescue_settings WHERE id = 1").fetchone()
    if row is None:
        return config.RescueSettings()
    return config.RescueSettings(
        enabled=int(row["enabled"]),
        provider=row["provider"] or "openai",
        base_url=row["base_url"] or "",
        model_name=row["model_name"] or "",
        vision_model=row["vision_model"] or "",
        vision_base_url=row["vision_base_url"] or "",
        vision_api_key=row["vision_api_key"] or "",
        vision_disable_thinking=int(row["vision_disable_thinking"] or 0),
        api_key=row["api_key"] or "",
        max_seconds=int(row["max_seconds"] or config.MAX_SECONDS),
        max_vision_calls=int(row["max_vision_calls"] or config.MAX_VISION_CALLS),
    )


def save_settings(fields: dict) -> config.RescueSettings:
    """api_key 留空表示沿用原值；界面只提交用户真正改动的字段。"""
    current = load_settings()
    api_key = fields.get("api_key")
    if api_key is None or api_key == "" or api_key == "******":
        api_key = current.api_key
    vision_api_key = fields.get("vision_api_key")
    if vision_api_key is None or vision_api_key == "" or vision_api_key == "******":
        vision_api_key = current.vision_api_key
    values = {
        "enabled": int(bool(fields.get("enabled", current.enabled))),
        "provider": fields.get("provider", current.provider) or "openai",
        "base_url": fields.get("base_url", current.base_url) or "",
        "model_name": fields.get("model_name", current.model_name) or "",
        "vision_model": fields.get("vision_model", current.vision_model) or "",
        "vision_base_url": fields.get("vision_base_url", current.vision_base_url) or "",
        "vision_api_key": vision_api_key,
        "vision_disable_thinking": int(
            bool(fields.get("vision_disable_thinking", current.vision_disable_thinking))
        ),
        "api_key": api_key,
        "max_seconds": int(fields.get("max_seconds", current.max_seconds) or config.MAX_SECONDS),
        "max_vision_calls": int(
            fields.get("max_vision_calls", current.max_vision_calls) or config.MAX_VISION_CALLS
        ),
    }
    with _LOCK:
        conn = connect()
        conn.execute(
            "UPDATE rescue_settings SET enabled=?, provider=?, base_url=?, model_name=?,"
            " vision_model=?, vision_base_url=?, vision_api_key=?, vision_disable_thinking=?,"
            " api_key=?, max_seconds=?, max_vision_calls=?, updated_at=? WHERE id=1",
            (
                values["enabled"], values["provider"], values["base_url"],
                values["model_name"], values["vision_model"], values["vision_base_url"],
                values["vision_api_key"], values["vision_disable_thinking"], values["api_key"],
                values["max_seconds"], values["max_vision_calls"], now(),
            ),
        )
        conn.commit()
    updated = load_settings()
    updated.apply_env()
    return updated


def create_run(req: dict) -> str:
    rescue_id = "rsq_%s" % str(int(time.time() * 1_000_000))
    with _LOCK:
        conn = connect()
        conn.execute(
            "INSERT INTO rescue_runs (rescue_id, run_id, step_id, device_id, script_name, app,"
            " package, goal, state_json, expected, status, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rescue_id,
                req.get("run_id") or "",
                req.get("step_id") or "",
                req.get("device_id") or "",
                req.get("script_name") or "",
                req.get("app") or "",
                req.get("package") or "",
                req.get("goal") or "",
                json.dumps(req.get("state") or {}, ensure_ascii=False),
                req.get("expected") or "any",
                "running",
                now(),
            ),
        )
        conn.commit()
    return rescue_id


def add_step(rescue_id: str, phase: str, detail: str, ok: bool | None = None,
             screenshot: str | None = None) -> None:
    with _LOCK:
        conn = connect()
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM rescue_steps WHERE rescue_id = ?", (rescue_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO rescue_steps (rescue_id, seq, phase, detail, ok, screenshot, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (rescue_id, seq, phase, detail, None if ok is None else int(ok), screenshot, now()),
        )
        conn.commit()


def bump(rescue_id: str, field: str) -> None:
    if field not in ("vision_calls", "tool_calls"):
        return
    with _LOCK:
        conn = connect()
        conn.execute("UPDATE rescue_runs SET %s = %s + 1 WHERE rescue_id = ?" % (field, field),
                     (rescue_id,))
        conn.commit()


def finish_run(rescue_id: str, status: str, resolved: bool, handler: str = "",
               evidence: str = "", state_patch: dict | None = None,
               error: str = "") -> None:
    with _LOCK:
        conn = connect()
        conn.execute(
            "UPDATE rescue_runs SET status=?, resolved=?, handler=?, evidence=?, state_patch=?,"
            " error=?, finished_at=? WHERE rescue_id=?",
            (
                status, int(resolved), handler, evidence,
                json.dumps(state_patch or {}, ensure_ascii=False),
                error[:2000], now(), rescue_id,
            ),
        )
        conn.commit()


def _run_dict(row: sqlite3.Row, steps: list[dict] | None = None) -> dict:
    data = dict(row)
    data["state"] = json.loads(data.pop("state_json") or "{}")
    data["state_patch"] = json.loads(data.pop("state_patch") or "{}")
    data["resolved"] = bool(data["resolved"])
    data["steps"] = steps or []
    return data


def get_run(rescue_id: str) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM rescue_runs WHERE rescue_id = ?", (rescue_id,)).fetchone()
    if row is None:
        return None
    steps = [dict(s) for s in conn.execute(
        "SELECT seq, phase, detail, ok, screenshot, created_at FROM rescue_steps"
        " WHERE rescue_id = ? ORDER BY seq", (rescue_id,))]
    return _run_dict(row, steps)


def list_runs(run_id: str = "", step_id: str = "", limit: int = 50) -> list[dict]:
    conn = connect()
    clauses, args = [], []
    if run_id:
        clauses.append("run_id = ?")
        args.append(run_id)
    if step_id:
        clauses.append("step_id = ?")
        args.append(step_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(max(1, min(int(limit or 50), 200)))
    rows = conn.execute(
        "SELECT * FROM rescue_runs%s ORDER BY created_at DESC LIMIT ?" % where, tuple(args)
    ).fetchall()
    return [_run_dict(r) for r in rows]


def stats() -> dict:
    conn = connect()
    total = conn.execute("SELECT COUNT(*) FROM rescue_runs").fetchone()[0]
    resolved = conn.execute(
        "SELECT COUNT(*) FROM rescue_runs WHERE resolved = 1"
    ).fetchone()[0]
    today = time.strftime("%Y-%m-%d")
    today_total = conn.execute(
        "SELECT COUNT(*) FROM rescue_runs WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()[0]
    today_resolved = conn.execute(
        "SELECT COUNT(*) FROM rescue_runs WHERE resolved = 1 AND created_at LIKE ?",
        (today + "%",),
    ).fetchone()[0]
    avg = conn.execute(
        "SELECT AVG((julianday(finished_at) - julianday(created_at)) * 86400)"
        " FROM rescue_runs WHERE finished_at IS NOT NULL AND resolved = 1"
    ).fetchone()[0]
    return {
        "total": total,
        "resolved": resolved,
        "today_total": today_total,
        "today_resolved": today_resolved,
        "success_rate": round(resolved / total, 4) if total else None,
        "avg_seconds": round(avg, 1) if avg else None,
    }