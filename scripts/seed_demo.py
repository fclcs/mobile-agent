"""填充演示数据：设备 / 脚本 / 流程 / 运行记录 / 报告 / 救援记录 / 截图。

用途：不接真机也能把界面跑起来（截图、录屏、作品展示）。

用法（在仓库根目录）：
    python scripts/seed_demo.py            # 生成 backend/app.db、rescue-demo.db 和截图
    cd backend && PHONE_AGENT_DEMO_MODE=1 python run.py
    python -m rescue --port 8010           # 另开一个终端

说明：脚本会覆盖已有的 backend/app.db 和 rescue-demo.db，只用于本地演示。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DB = ROOT / "backend" / "app.db"
RESCUE_DB = Path(os.environ.get("OAG_RESCUE_DB", str(ROOT / "rescue-demo.db")))
SHOT_ROOT = ROOT / "workflow_screenshots"
RESCUE_SHOT_ROOT = ROOT / "rescue-demo-screenshots"

NOW = datetime(2026, 11, 20, 10, 0, 0)


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _font(size: int):
    from PIL import ImageFont

    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def phone_screen(kind: str, title: str, lines: list[str], badge: str | None = None) -> "Image":
    """画一张 720x1600 的演示手机界面。"""
    from PIL import Image, ImageDraw

    W, H = 720, 1600
    dark = kind in ("video", "blocked")
    bg = (22, 25, 28) if dark else (250, 249, 246)
    fg = (240, 237, 230) if dark else (22, 25, 28)
    sub = (154, 160, 166)

    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    f_title, f_body, f_small = _font(38), _font(30), _font(24)

    # 状态栏 + 标题栏
    d.rectangle([0, 0, W, 96], fill=(16, 20, 24) if not dark else (12, 14, 16))
    d.text((32, 30), "10:24", font=f_small, fill=(230, 225, 216))
    d.text((W - 120, 30), "5G  ▮", font=f_small, fill=(230, 225, 216))
    d.rectangle([0, 96, W, 200], fill=(255, 255, 255) if not dark else (26, 31, 36))
    d.text((32, 128), title, font=f_title, fill=fg if dark else (22, 25, 28))

    if kind == "video":
        d.ellipse([W / 2 - 70, 720, W / 2 + 70, 860], fill=(242, 163, 58))
        d.polygon([(W / 2 - 20, 750), (W / 2 - 20, 830), (W / 2 + 40, 790)], fill=(22, 25, 28))
        d.rectangle([60, 1400, W - 60, 1416], fill=(60, 66, 72))
        d.rectangle([60, 1400, 460, 1416], fill=(242, 163, 58))
        d.text((60, 1440), "01:32 / 15:00", font=f_small, fill=sub)
    else:
        y = 250
        for line in lines:
            d.text((48, y), line, font=f_body, fill=(22, 25, 28) if not dark else fg)
            y += 92
            if kind == "reader":
                d.rectangle([48, y - 40, W - 48, y - 38], fill=(235, 232, 225))

    # 底部导航
    d.rectangle([0, H - 110, W, H], fill=(255, 255, 255) if not dark else (18, 22, 26))
    for i, name in enumerate(("首页", "发现", "我的")):
        d.text((120 + i * 200, H - 78), name, font=f_small, fill=sub)

    if kind == "blocked":
        d.rectangle([0, 200, W, H - 110], fill=(10, 12, 14))
        d.rounded_rectangle([60, 420, W - 60, 1080], 24, fill=(28, 33, 38), outline=(242, 163, 58), width=3)
        d.text((100, 480), "检测到阻塞页面", font=f_title, fill=(242, 163, 58))
        d.text((100, 560), "· 页面元素无响应", font=f_body, fill=(220, 215, 205))
        d.text((100, 630), "· 已接管现场", font=f_body, fill=(220, 215, 205))
        d.text((100, 700), "· 等待业务验收", font=f_body, fill=(220, 215, 205))

    if badge:
        d.rounded_rectangle([W - 250, 110, W - 40, 180], 14, fill=(242, 163, 58))
        d.text((W - 232, 128), badge, font=f_small, fill=(16, 20, 24))

    return img


DEMO_SCRIPTS = [
    (
        "script_demo_reader",
        "演示 · 阅读脚本（关键词=示例内容，每 90 秒翻 1 页，共 10 页）",
        "阅读类",
        '"""演示脚本：搜索并连续阅读，翻页以正文截图变化为验收依据。"""\n'
        'print(\'DEMO_READ_RESULT={"pages": 10, "verified": 10, "resumed": false}\')\n',
    ),
    (
        "script_demo_video",
        "演示 · 短视频脚本（搜索并观看 15 分钟）",
        "短视频类",
        '"""演示脚本：播放页挂机，按集数/播放状态验收，拦截 feed 广告。"""\n'
        'print(\'DEMO_WATCH_RESULT={"seconds": 900, "episodes": 6, "ads_closed": 2}\')\n',
    ),
    (
        "script_demo_browser",
        "演示 · 浏览器脚本（搜索并浏览 5 分钟）",
        "浏览器类",
        '"""演示脚本：浏览器搜索与浏览。"""\n'
        'print(\'DEMO_BROWSE_RESULT={"seconds": 300, "pages": 8}\')\n',
    ),
    (
        "script_demo_guard",
        "演示 · 弹窗守卫自检（启动后检查更新/广告弹窗）",
        "通用",
        '"""演示脚本：启动后检查更新弹窗与开屏广告。"""\n'
        'print(\'DEMO_GUARD_RESULT={"update_dialog": "closed", "splash_ad": "skipped"}\')\n',
    ),
    (
        "script_demo_health",
        "演示 · 设备连通性检查",
        "通用",
        '"""演示脚本：检查 ADB 连通、屏幕分辨率与截图能力。"""\n'
        'print(\'DEMO_HEALTH_RESULT={"adb": "ok", "screen": "720x1600"}\')\n',
    ),
]

STEPS = [
    ("script_demo_guard", "演示 · 弹窗守卫自检（启动后检查更新/广告弹窗）"),
    ("script_demo_reader", "演示 · 阅读脚本（关键词=示例内容，每 90 秒翻 1 页，共 10 页）"),
    ("script_demo_video", "演示 · 短视频脚本（搜索并观看 15 分钟）"),
    ("script_demo_health", "演示 · 设备连通性检查"),
]


def seed_backend() -> None:
    if BACKEND_DB.exists():
        BACKEND_DB.unlink()

    conn = sqlite3.connect(BACKEND_DB)
    schema = (ROOT / "backend" / "app" / "db" / "database.py").read_text(encoding="utf-8")
    start = schema.index('executescript("""') + len('executescript("""')
    end = schema.index('""")', start)
    conn.executescript(schema[start:end])

    # 设备
    devices = [
        ("demo-01", "演示机 01", "阅读类任务", "演示组", "android", "Demo One", "Demo", "14", 720, 1600, "tcpip", 1, 1),
        ("demo-02", "演示机 02", "短视频任务", "演示组", "android", "Demo Two", "Demo", "14", 1080, 2400, "tcpip", 1, 1),
        ("demo-03", "演示机 03", "通用", "演示组", "android", "Demo Three", "Demo", "13", 1080, 2340, "usb", 1, 1),
    ]
    for dev in devices:
        conn.execute(
            "INSERT INTO devices (device_id,name,remark,group_name,platform,model,manufacturer,"
            "os_version,screen_width,screen_height,connection_type,enabled,auto_registered,"
            "created_at,updated_at,last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*dev, ts(NOW - timedelta(days=6)), ts(NOW), ts(NOW)),
        )

    # 脚本
    for idx, (sid, name, desc, content) in enumerate(DEMO_SCRIPTS, start=1):
        conn.execute(
            "INSERT INTO scripts (script_id,name,content,script_type,platform,project_id,"
            "description,created_at,updated_at,version) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, name, content, "external", "android", None, desc,
             ts(NOW - timedelta(days=5, hours=idx)), ts(NOW - timedelta(hours=idx)), 3),
        )

    # 模型配置（演示占位，不含真实密钥）
    conn.execute(
        "INSERT INTO model_configs (config_id,name,provider,base_url,api_key,model_name,"
        "vision_model,is_default,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("cfg_demo", "演示模型", "openai", "https://api.example.com/v1", "demo-key",
         "demo-model", "demo-vision-model", 1, ts(NOW - timedelta(days=6)), ts(NOW)),
    )
    conn.execute(
        "INSERT INTO vision_model_config (id,provider,base_url,api_key,model_name,"
        "disable_thinking,updated_at) VALUES (1,'openai','https://api.example.com/v1',"
        "'demo-key','demo-vision-model',1,?)",
        (ts(NOW),),
    )

    # 流程
    workflows = [
        ("wf_demo_daily", "每日内容巡检", "早间流程：守卫自检 → 阅读 → 观看 → 连通性",
         ["script_demo_guard", "script_demo_reader", "script_demo_video", "script_demo_health"]),
        ("wf_demo_watch", "观看时长任务", "只跑观看与浏览两段",
         ["script_demo_video", "script_demo_browser"]),
    ]
    for wid, wname, wdesc, sids in workflows:
        conn.execute(
            "INSERT INTO workflows (workflow_id,name,description,script_ids,continue_on_error,"
            "step_timeout,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (wid, wname, wdesc, json.dumps(sids), 1, 0, ts(NOW - timedelta(days=5)), ts(NOW)),
        )

    # 运行记录：3 台设备 × 2 个批次
    runs = []
    for batch_idx, day in enumerate((2, 1)):
        batch_id = f"demo-batch-{day:02d}"
        for dev_id, dev_name in (("demo-01", "演示机 01"), ("demo-02", "演示机 02"), ("demo-03", "演示机 03")):
            run_id = f"run_demo_{day:02d}_{dev_id}"
            started = NOW - timedelta(days=day, hours=batch_idx)
            steps = STEPS if dev_id != "demo-02" else STEPS[:3]
            status = "completed"
            if dev_id == "demo-03" and day == 2:
                status = "failed"
            if dev_id == "demo-02" and day == 1:
                status = "completed"
            conn.execute(
                "INSERT INTO workflow_runs (run_id,workflow_id,workflow_name,device_id,device_name,"
                "batch_id,status,current_step,total_steps,error,created_at,started_at,completed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, "wf_demo_daily", "每日内容巡检", dev_id, dev_name, batch_id, status,
                 len(steps), len(steps), None if status == "completed" else "第 4 步超时",
                 ts(started), ts(started), ts(started + timedelta(minutes=18 - batch_idx * 3))),
            )
            runs.append((run_id, started, steps, status))

    # 步记录 + 截图
    shot_rel_paths: dict[tuple[str, int], str] = {}
    for run_id, started, steps, status in runs:
        day_dir = started.strftime("%Y-%m-%d")
        run_dir = SHOT_ROOT / day_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        for order, (sid, sname) in enumerate(steps, start=1):
            step_id = f"step_{run_id}_{order:02d}"
            kind = "reader" if "reader" in sid else ("video" if "video" in sid else "normal")
            failed = status == "failed" and order == len(steps)
            title = {"reader": "演示 · 阅读器", "video": "演示 · 播放页"}.get(kind, "演示 · 应用界面")
            img = phone_screen(
                "blocked" if failed else kind,
                title,
                ["示例正文第一段，用于展示页面结构。", "示例正文第二段，坐标与控件均来自运行时识别。",
                 "示例正文第三段，翻页以正文截图哈希变化验收。"],
                badge="已救援" if order == 2 else None,
            )
            fname = f"step_{order:02d}_step_{step_id}_1.png"
            img.save(run_dir / fname)
            rel = f"{day_dir}/{run_id}/{fname}"
            shot_rel_paths[(run_id, order)] = rel
            finished = started + timedelta(minutes=order * 4)
            conn.execute(
                "INSERT INTO workflow_step_runs (step_id,run_id,step_order,script_id,script_name,"
                "status,exit_code,output,error,screenshot_path,captured_at,started_at,completed_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (step_id, run_id, order, sid, sname, "failed" if failed else "completed",
                 1 if failed else 0,
                 '{"resolved": true}' if order == 2 else '{"ok": true}',
                 "step timeout" if failed else None, rel, ts(finished), ts(finished), ts(finished)),
            )

    # 任务
    task_rows = [
        ("task_demo_01", "演示 · 每日内容巡检（批量）", "workflow", "completed", "script_demo_guard", "demo-01", 100, 3),
        ("task_demo_02", "演示 · 阅读 10 页", "functional", "completed", "script_demo_reader", "demo-01", 100, 2),
        ("task_demo_03", "演示 · 观看 15 分钟", "functional", "completed", "script_demo_video", "demo-02", 100, 2),
        ("task_demo_04", "演示 · 浏览器浏览", "functional", "completed", "script_demo_browser", "demo-03", 100, 1),
        ("task_demo_05", "演示 · 阅读 4 页（短测）", "functional", "completed", "script_demo_reader", "demo-02", 100, 1),
        ("task_demo_06", "演示 · 观看 5 分钟（短测）", "functional", "completed", "script_demo_video", "demo-01", 100, 1),
        ("task_demo_07", "演示 · 夜间巡检", "workflow", "executing", "script_demo_guard", "demo-02", 45, 0),
        ("task_demo_08", "演示 · 连通性检查", "functional", "failed", "script_demo_health", "demo-03", 100, 3),
        ("task_demo_09", "演示 · 广告守卫回归", "functional", "completed", "script_demo_guard", "demo-01", 100, 2),
        ("task_demo_10", "演示 · 长任务稳定性", "workflow", "completed", "script_demo_reader", "demo-02", 100, 1),
    ]
    for tid, name, ttype, status, sid, dev, progress, days_ago in task_rows:
        created = NOW - timedelta(days=days_ago, hours=1)
        conn.execute(
            "INSERT INTO tasks (task_id,name,task_type,platform,status,script_id,device_id,"
            "model_config_id,description,progress,created_at,updated_at,started_at,completed_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, name, ttype, "android", status, sid, dev, "cfg_demo",
             "演示任务，由 scripts/seed_demo.py 生成", progress, ts(created), ts(created),
             ts(created), None if status == "executing" else ts(created + timedelta(minutes=12))),
        )
        conn.execute("INSERT INTO task_devices (task_id,device_id) VALUES (?,?)", (tid, dev))

    # 报告
    reports = [
        ("task_demo_02", "演示 · 阅读脚本报告", 10, 10, 0),
        ("task_demo_03", "演示 · 观看脚本报告", 6, 6, 0),
        ("task_demo_08", "演示 · 连通性报告", 4, 3, 1),
        ("task_demo_10", "演示 · 长任务稳定性报告", 8, 8, 0),
    ]
    for tid, name, total, passed, failed in reports:
        created = NOW - timedelta(days=1)
        conn.execute(
            "INSERT INTO reports (task_id,name,device_name,script_name,script_type,status,"
            "started_at,completed_at,duration_seconds,html_content,summary,total_steps,"
            "passed_steps,failed_steps,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, name, "演示机 01", "演示脚本", "external", "completed", ts(created),
             ts(created + timedelta(minutes=12)), 720, "", "演示报告", total, passed, failed, ts(created)),
        )

    conn.commit()
    conn.close()
    print(f"backend db -> {BACKEND_DB}")
    print(f"screenshots -> {SHOT_ROOT}")


def seed_rescue() -> None:
    if RESCUE_DB.exists():
        RESCUE_DB.unlink()
    conn = sqlite3.connect(RESCUE_DB)
    src = (ROOT / "rescue" / "store.py").read_text(encoding="utf-8")
    start = src.index('SCHEMA = """') + len('SCHEMA = """')
    end = src.index('"""', start)
    conn.executescript(src[start:end])
    conn.execute(
        "INSERT INTO rescue_settings (id,enabled,provider,base_url,model_name,vision_model,"
        "vision_base_url,vision_api_key,vision_disable_thinking,api_key,max_seconds,"
        "max_vision_calls,updated_at) VALUES (1,1,'openai','https://api.example.com/v1',"
        "'demo-model','demo-vision-model','https://api.example.com/v1','demo-key',1,"
        "'demo-key',150,3,?)",
        (ts(NOW),),
    )

    runs = [
        ("rescue_demo_01", "演示机 01", "阅读类 App", "reader", "reader-stuck",
         "阅读器不翻页（章末卡住）", 3, 2, 1),
        ("rescue_demo_02", "演示机 02", "短视频类 App", "feed_ad", "ads",
         "feed 内嵌广告（无关闭按钮）", 2, 3, 1),
        ("rescue_demo_03", "演示机 01", "阅读类 App", "update", "update",
         "应用更新弹窗遮挡首屏", 2, 1, 0),
        ("rescue_demo_04", "演示机 03", "浏览器类 App", "navigation", "navigation",
         "离开目标页，需回到内容页", 4, 2, 1),
    ]
    RESCUE_SHOT_ROOT.mkdir(parents=True, exist_ok=True)
    for idx, (rid, dev, app, kind, handler, goal, steps_n, vision, tools) in enumerate(runs):
        created = NOW - timedelta(hours=6 - idx, minutes=20)
        conn.execute(
            "INSERT INTO rescue_runs (rescue_id,run_id,step_id,device_id,script_name,app,package,"
            "goal,state_json,expected,status,handler,resolved,vision_calls,tool_calls,evidence,"
            "state_patch,error,created_at,finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, f"run_demo_01_{dev[-2:]}", f"step_demo_{idx}", dev, "演示脚本", app, "demo.app",
             goal, '{"page": 3}', "reader", "resolved", handler, 1, vision, tools,
             "正文区域截图哈希发生变化", '{"page": 4}', None, ts(created), ts(created + timedelta(seconds=28))),
        )
        print_seq = [
            ("detect", "检测到页面无响应，接管现场", 1),
            ("handler", f"命中确定性规则：{handler}", 1),
            ("verify", "业务验收通过：正文已翻页", 1),
        ]
        for seq, (phase, detail, ok) in enumerate(print_seq[:steps_n], start=1):
            img = phone_screen(
                "blocked" if seq == 1 else "reader",
                "演示 · 救援现场",
                ["现场页面快照", "用于展示救援过程逐帧留证。"],
                badge="接管中" if seq == 1 else "已恢复",
            )
            shot_name = f"{rid}_{seq}.png"
            img.save(RESCUE_SHOT_ROOT / shot_name)
            conn.execute(
                "INSERT INTO rescue_steps (rescue_id,seq,phase,detail,ok,screenshot,created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (rid, seq, phase, detail, ok, shot_name, ts(created + timedelta(seconds=seq * 6))),
            )

    conn.commit()
    conn.close()
    print(f"rescue db -> {RESCUE_DB}")
    print(f"rescue screenshots -> {RESCUE_SHOT_ROOT}")


if __name__ == "__main__":
    seed_backend()
    seed_rescue()
    print("done. 启动：")
    print("  cd backend && PHONE_AGENT_DEMO_MODE=1 python run.py")
    print(f"  OAG_RESCUE_DB={RESCUE_DB} OAG_RESCUE_SKILLS={ROOT / 'rescue' / 'skills'} "
          f"OAG_RESCUE_SCREENSHOT_DIR={RESCUE_SHOT_ROOT} python -m rescue")
    sys.exit(0)