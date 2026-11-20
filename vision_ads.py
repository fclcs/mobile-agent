"""视觉模型广告/遮挡识别与控件定位。

脚本在“界面无法识别、已知控件全部失效”的卡住状态下调用本模块：
先用无障碍树按按钮文字确定性关闭应用更新/升级提示，再截图 → 调用视觉
模型 → 判定页面类型 → 只有确认是广告/阻塞弹窗且给出明确的关闭控件时
才点击；广告的关闭坐标还必须落在屏幕边缘区域，否则不动作。
无障碍树里完全没有节点、但画面特征明确时（如阅读类 App 首页搜索框），可用
locate() 按文字描述定位控件中心，避免写死坐标或固定比例。

模型地址和密钥复用 Web 后台注入的 PHONE_AGENT_BASE_URL / PHONE_AGENT_API_KEY。
模型名取自网页端“模型配置”的“视觉模型”字段，由后台注入 PHONE_AGENT_VISION_MODEL；
该字段留空时，智谱地址用 glm-4v-plus，其他地址回退到 PHONE_AGENT_MODEL。
本模块不打印、不保存任何密钥。仅使用 Python 标准库（Pillow 可选，用于压缩截图）。
"""

import base64
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

MODEL_ENV = "PHONE_AGENT_VISION_MODEL"
DEFAULT_MODEL = "glm-4v-plus"
MAX_CALLS = 60
MIN_CALL_INTERVAL = 2.0
CACHE_TTL = 90.0
HTTP_TIMEOUT = 60
SCREENSHOT_TIMEOUT = 25

SYSTEM_PROMPT = """你是安卓界面审核器。把画面归为其中一类：
A=阅读正文页（整屏文字，几乎没有按钮）
B=常规应用界面（首页、书城、搜索、列表、详情、设置）
C=广告或推广页（开屏/插屏/激励广告；大幅海报或视频；下载、立即打开、领取、抽奖、红包、福利按钮）
D=阻塞弹窗（应用更新/升级提示、权限请求、系统公告、评分或清理提示）

判定规则：
1. 只有 C 是广告。B 类的书籍封面、商品图片、活动入口方块都不算广告。
2. C 类必须给出关闭/跳过/X 控件；控件可能是屏幕右上角的 X、倒计时“跳过”、底部“不再提示/关闭”，也可能是广告卡片右上角的 X。画面上确实没有任何关闭控件时 close=null。
3. "立即下载/打开/领取/查看详情/点击跳转"是广告内容，不是关闭控件。
4. close 使用画面千分比坐标，取控件中心：左上为(0,0)，右下为(1000,1000)。
5. 只输出一行 JSON：{"page_type":"A|B|C|D","is_ad":true|false,"close":{"x":整数,"y":整数}|null,"dismiss":{"x":整数,"y":整数,"label":"按钮原文"}|null,"reason":"不超过15字"}
6. 剧情视频/短剧播放页一律是 B，不是广告：画面即使是大图视频、右侧有竖排的收藏/评论/点赞/分享按钮、顶部有“第N集”和倍速图标、底部有“选集/热评/发弹幕”，都按 B 处理。只有整屏是商业推广（下载 App、领红包、抽奖、商品售卖、第三方广告标识）时才判 C。
7. 弹窗遮住应用内容、必须处理才能继续时判 D，并给 dismiss：只允许“下次再说/以后再说/稍后再说/暂不更新/暂不升级/取消/关闭/我知道了/跳过/不再提示/忽略/暂不开启”这类否定或关闭按钮，label 必须原样抄按钮文字。“立即更新/立即安装/去升级/允许/开启/同意/确定”是肯定按钮，绝不能在 dismiss 里返回。没有这类按钮时 dismiss=null。"""

# 只在更新/升级语境下才点“取消/关闭”等通用按钮，避免误关业务弹窗；
# 专门的“下次再说”类按钮本身只出现在延迟/更新提示里，可以直接点。
DEFER_LABELS = {
    "下次再说", "下次再聊", "以后再说", "稍后再说", "暂不更新", "暂不升级",
    "下次更新", "以后更新", "暂不升级吧",
}
GENERIC_DISMISS_LABELS = {
    "取消", "关闭", "我知道了", "跳过", "不再提示", "忽略", "暂不", "暂不开启",
}
UPDATE_HINTS = ("更新", "升级", "新版本", "版本更新", "发现新版本")
# 更新弹窗里的“肯定按钮”文字：用来确认这是更新弹窗，同时任何控件都不得点击。
UPDATE_CONFIRM_WORDS = (
    "立即更新", "马上升级", "立即升级", "立即安装", "去升级", "去更新", "前往", "领取", "体验",
)
# 候选关闭控件里出现这些字就不能点（“立即/更新”都可能把用户带去下载页）。
UPDATE_UNSAFE_WORDS = (
    "更新", "升级", "安装", "下载", "立即", "体验", "领取", "前往",
)
# 关闭类控件的文字/无障碍描述；大小写差异由 lower() 处理。
CLOSE_LABELS = {
    "关闭", "关闭按钮", "关闭弹窗", "关闭提示", "close", "dismiss", "cancel",
    "取消", "×", "✕", "ⅹ", "╳", "x",
}


def _node_label(node) -> str:
    """节点的可读文字：优先 text，其次 content-desc（纯图标按钮只有后者）。"""
    text = (node.attrib.get("text") or "").strip()
    if text:
        return text
    return (node.attrib.get("content-desc") or "").strip()


def _rect_of(node) -> tuple[int, int, int, int] | None:
    match = BOUNDS_RE.search(node.attrib.get("bounds", ""))
    if not match:
        return None
    x1, y1, x2, y2 = (int(value) for value in match.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _clickable_self_or_ancestor(node, parents, levels: int = 2):
    """文字节点常放在可点击容器里；向上最多找 levels 层可点击控件。"""
    current = node
    for _ in range(levels + 1):
        if current is None:
            return None
        if current.attrib.get("clickable") == "true":
            return current
        current = parents.get(current)
    return None


def _update_dialog_container(root, parents, screen_area=0):
    """定位承载更新提示的弹窗容器；不是弹窗时返回 None。

    只认“面积 5%~75% 屏幕、文字是从内向外最近且带点击控件”的那一层，
    并要求它内部同时有更新文案 + 肯定按钮（或两处更新文案）。整页书城
    里出现的“更新”二字不会凑出这种结构，避免误点页面上的普通按钮。
    """
    nodes = list(root.iter("node"))
    hints = [n for n in nodes if any(h in _node_label(n) for h in UPDATE_HINTS)]
    if not hints:
        return None
    best = None
    for hint in hints:
        candidate = parents.get(hint)
        for _ in range(8):
            if candidate is None:
                break
            area = _area_of(candidate)
            if screen_area and area >= screen_area * 0.75:
                break
            if screen_area and area < screen_area * 0.03:
                candidate = parents.get(candidate)
                continue
            labels = [_node_label(n) for n in candidate.iter("node")]
            has_confirm = any(
                word in label for label in labels for word in UPDATE_CONFIRM_WORDS
            )
            hint_count = sum(
                1 for label in labels
                if any(h in label for h in UPDATE_HINTS)
            )
            has_clickable = any(
                n.attrib.get("clickable") == "true"
                for n in candidate.iter("node")
            )
            if has_clickable and (has_confirm or hint_count >= 2):
                if best is None or area < best[1]:
                    best = (candidate, area)
                break
            candidate = parents.get(candidate)
    return best[0] if best else None


def _update_control_in_container(container, parents, screen_area=0):
    """在更新弹窗容器里找可安全点击的否定/关闭控件。

    优先“以后再说/暂不更新”这类延迟按钮，其次“取消/关闭/我知道了”，再其次
    右上角无文字的关闭 X 图标；任何含“立即更新/马上升级”文字的控件一律跳过。
    返回 (节点, 按钮文字)；找不到返回 (None, "")。
    """
    rect = _rect_of(container)
    if rect is None:
        return None, ""
    cx1, cy1, cx2, cy2 = rect
    cw, ch = cx2 - cx1, cy2 - cy1
    best = None
    for node in container.iter("node"):
        label = _node_label(node).strip().rstrip("。.!！~ ")
        target = _clickable_self_or_ancestor(node, parents, 2)
        if target is None:
            continue
        if label:
            if any(word in label for word in UPDATE_UNSAFE_WORDS):
                continue
            if label in DEFER_LABELS:
                priority = 0
            elif label in GENERIC_DISMISS_LABELS or label.lower() in CLOSE_LABELS:
                priority = 1
            else:
                continue
        else:
            # 无文字的图标：只认弹窗上半部右侧的小控件（关闭 X）
            node_rect = _rect_of(target)
            if node_rect is None:
                continue
            nx1, ny1, nx2, ny2 = node_rect
            nw, nh = nx2 - nx1, ny2 - ny1
            if nw > cw * 0.30 or nh > ch * 0.18:
                continue
            center_x = (nx1 + nx2) / 2
            center_y = (ny1 + ny2) / 2
            if center_y > cy1 + ch * 0.45:
                continue
            if center_x < cx1 + cw * 0.55:
                continue
            label = "关闭图标"
            priority = 2
        area = _area_of(target)
        if best is None or (priority, area) < (best[0], best[1]):
            best = (priority, area, target, label)
    if best is None:
        return None, ""
    return best[2], best[3]


def _subtree_has_update_hint(node) -> bool:
    for child in node.iter("node"):
        text = (child.attrib.get("text") or "").strip()
        if any(hint in text for hint in UPDATE_HINTS):
            return True
    return False


def _shares_update_container(node, parents, screen_area=0) -> bool:
    return _shares_hint_container(node, parents, UPDATE_HINTS, screen_area)
# 视觉模型给出的 label 可信，但坐标经常偏到画面中心；D 类弹窗一律先按
# 无障碍树里的按钮文字找真实位置，找不到才退回模型坐标。
CLOSE_ICON_TARGET = "广告或弹窗上的关闭 X 按钮（小方形或圆形的 × 图标）"
BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

_calls = 0
_last_call_at = 0.0
_cache_digest: str | None = None
_cache_result: dict | None = None
_cache_at = 0.0
_tapped_digest: str | None = None


def _api_config() -> tuple[str, str, str] | None:
    # 视觉模型有自己的 Base URL / API Key 时优先用它（网页「视觉模型」独立配置）；
    # 没配置就回落到手机操作模型的那一套，保持旧部署的行为不变。
    base_url = (
        os.environ.get(VISION_BASE_ENV)
        or os.environ.get("PHONE_AGENT_BASE_URL")
        or ""
    ).strip().rstrip("/")
    api_key = (
        os.environ.get(VISION_API_KEY_ENV)
        or os.environ.get("PHONE_AGENT_API_KEY")
        or ""
    ).strip()
    if not base_url or not api_key or api_key in {"EMPTY", "******"}:
        return None
    model = (os.environ.get(MODEL_ENV) or "").strip()
    if not model:
        model = DEFAULT_MODEL if "bigmodel" in base_url else (
            os.environ.get("PHONE_AGENT_MODEL") or DEFAULT_MODEL
        )
    url = base_url if base_url.endswith("/chat/completions") else base_url + "/chat/completions"
    return url, api_key, model


VISION_BASE_ENV = "PHONE_AGENT_VISION_BASE_URL"
VISION_API_KEY_ENV = "PHONE_AGENT_VISION_API_KEY"
DISABLE_THINKING_ENV = "PHONE_AGENT_DISABLE_THINKING"
VISION_DISABLE_THINKING_ENV = "PHONE_AGENT_VISION_DISABLE_THINKING"


def _thinking_body() -> dict:
    """配置里勾选“关闭思考模式”时，请求体带上 enable_thinking=false。"""
    value = (
        os.environ.get(VISION_DISABLE_THINKING_ENV)
        if os.environ.get(VISION_BASE_ENV)
        else os.environ.get(DISABLE_THINKING_ENV)
    ) or ""
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return {"enable_thinking": False}
    return {}


def png_size(png: bytes) -> tuple[int, int]:
    """从 PNG 的 IHDR 读取屏幕宽高，不依赖 Pillow。"""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("截图不是有效的 PNG。")
    width, height = struct.unpack(">II", png[16:24])
    return int(width), int(height)


def _prepare_image(png: bytes) -> tuple[bytes, str]:
    """可选压缩：缩到 720 宽以内再转 JPEG，降低请求体积和耗时。"""
    try:
        from PIL import Image
    except Exception:
        return png, "image/png"
    try:
        image = Image.open(io.BytesIO(png)).convert("RGB")
        image.thumbnail((720, 1600))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=70)
        return buffer.getvalue(), "image/jpeg"
    except Exception:
        return png, "image/png"


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    return None
                return data if isinstance(data, dict) else None
    return None


def classify(png: bytes) -> dict | None:
    config = _api_config()
    if config is None:
        return None
    url, api_key, model = config
    image, mime = _prepare_image(png)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"},
                    },
                    {"type": "text", "text": "审核这张手机截图，只输出 JSON。"},
                ],
            },
        ],
        "max_tokens": 800,
        "temperature": 0.0,
        **_thinking_body(),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return _parse_json(content if isinstance(content, str) else "")


def _dump_ui(device_id: str) -> ET.Element | None:
    """完整 dump 无障碍树；压缩模式会过滤掉部分节点，这里不用 --compressed。"""
    try:
        dump = subprocess.run(
            [
                "adb", "-s", device_id, "shell", "uiautomator", "dump",
                "/sdcard/.vision_guard.xml",
            ],
            capture_output=True,
            timeout=15,
        )
        if dump.returncode != 0:
            return None
        result = subprocess.run(
            ["adb", "-s", device_id, "exec-out", "cat", "/sdcard/.vision_guard.xml"],
            capture_output=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        return ET.fromstring(result.stdout.decode("utf-8", "replace"))
    except ET.ParseError:
        return None


def dismiss_update_dialog(device_id: str, context: str = "", strict: bool = False) -> bool:
    """确定性关闭应用更新/升级提示；成功处理返回 True。

    不依赖视觉模型：定位承载更新文案的弹窗容器，依次找“下次再说/暂不更新”
    这类延迟按钮、“取消/关闭/我知道了”、右上角无文字的关闭 X 图标；只有
    “立即更新”一个按钮的弹窗（QQ 阅读、部分 OPPO 机型常见）按返回键关闭。
    任何含“立即更新/马上升级/安装/下载”文字的控件一律不点。
    """
    if not device_id:
        return False
    root = _dump_ui(device_id)
    if root is None:
        return False
    parents = {child: parent for parent in root.iter() for child in parent}
    screen_area = _screen_area(device_id)
    container = _update_dialog_container(root, parents, screen_area)
    if container is None:
        return False

    node, label = _update_control_in_container(container, parents, screen_area)
    if node is not None and _tap(node, device_id, label, f"更新提示：{context}"):
        return True

    # 弹窗只有“立即更新”一个按钮、关闭 X 又读不到：按返回键关掉弹窗。
    if _press_back(device_id):
        print(f"更新提示：{context} → 无可点击关闭控件，已按返回键。", flush=True)
        return True
    return False


def _tap(node: ET.Element, device_id: str, label: str, context: str) -> bool:
    match = BOUNDS_RE.search(node.attrib.get("bounds", ""))
    if not match:
        return False
    x1, y1, x2, y2 = (int(value) for value in match.groups())
    if x2 <= x1 or y2 <= y1:
        return False
    x, y = (x1 + x2) // 2, (y1 + y2) // 2
    try:
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            timeout=20,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return False
    global _cache_digest
    _cache_digest = None
    print(f"{context} → 按按钮文字点击「{label}」({x}, {y})。", flush=True)
    time.sleep(0.8)
    return True


def tap_label(device_id: str, labels, context: str = "弹窗按钮") -> bool:
    """按按钮文字确定性点击：在无障碍树里找文字精确匹配的可点击控件。

    视觉模型的 dismiss.label 通常准确，但坐标可能落在画面中部。这里只信任
    文字，用 dump 里的真实 bounds 换算点击位置；文字节点本身不可点击时，
    向上最多找四层可点击父节点（弹窗按钮常是 TextView + 可点击容器）。
    """
    wanted = {label.strip() for label in labels if label and label.strip()}
    if not device_id or not wanted:
        return False
    root = _dump_ui(device_id)
    if root is None:
        return False
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in root.iter("node"):
        label = (node.attrib.get("text") or "").strip()
        if label not in wanted:
            label = (node.attrib.get("content-desc") or "").strip()
            if label not in wanted:
                continue
        candidate: ET.Element | None = node
        for _ in range(4):
            if candidate is None:
                break
            if candidate.attrib.get("clickable") == "true":
                if _tap(candidate, device_id, label, context):
                    return True
                break
            candidate = parents.get(candidate)
    return False


AD_CLOSE_WORDS = {
    "关闭", "关闭广告", "跳过", "跳过广告", "Close", "close", "Skip", "skip",
    "X", "×", "我知道了", "不再提示",
}


def _tap_ad_close_by_ui(device_id: str, context: str) -> bool:
    """广告页优先在无障碍树里找关闭控件，不依赖模型给的坐标。

    图片广告常见结构：一张全屏可点击 ImageView + 一个小方形关闭 ImageView
    （通常没有文字）。模型容易把关闭坐标报在右上角，点空后画面不变；这里
    先按“关闭/跳过”文字找，再按“全屏图 + 四角/底部小图标”找真实节点点击。
    """
    root = _dump_ui(device_id)
    if root is None:
        return False
    nodes: list[tuple[ET.Element, int, int, int, int]] = []
    for node in root.iter("node"):
        if node.attrib.get("clickable") != "true":
            continue
        match = BOUNDS_RE.search(node.attrib.get("bounds", ""))
        if not match:
            continue
        x1, y1, x2, y2 = (int(value) for value in match.groups())
        if x2 <= x1 or y2 <= y1:
            continue
        nodes.append((node, x1, y1, x2, y2))
    if not nodes:
        return False

    for node, _x1, _y1, _x2, _y2 in nodes:
        label = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
        if label.rstrip("。.!！~ ") in AD_CLOSE_WORDS:
            return _tap(node, device_id, label, context)

    screen_w = max(x2 for _, _, _, x2, _ in nodes)
    screen_h = max(y2 for _, _, _, _, y2 in nodes)
    if screen_w <= 0 or screen_h <= 0:
        return False
    screen_area = screen_w * screen_h
    has_fullscreen = any(
        (x2 - x1) * (y2 - y1) >= screen_area * 0.7
        for _, x1, y1, x2, y2 in nodes
    )
    if not has_fullscreen:
        return False
    best: tuple[ET.Element, int, int] | None = None
    for node, x1, y1, x2, y2 in nodes:
        box_width, box_height = x2 - x1, y2 - y1
        if box_width * box_height >= screen_area * 0.5:
            continue
        if not (screen_w * 0.02 <= box_width <= screen_w * 0.10):
            continue
        if not (screen_h * 0.01 <= box_height <= screen_h * 0.07):
            continue
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        # 关闭图标一般在四角或底部，避开正文区域的普通图标。
        if not (
            cy >= screen_h * 0.60
            or cy <= screen_h * 0.18
            or cx <= screen_w * 0.15
            or cx >= screen_w * 0.85
        ):
            continue
        if best is None:
            best = (node, cx, cy)
    if best is None:
        return False
    return _tap(best[0], device_id, "关闭", context)


def _locate_close_icon(
    device_id: str, png: bytes, context: str
) -> tuple[int, int] | None:
    """模型没给出可信关闭坐标时，单独定位小方块/圆形 X 图标并校验形状。"""
    rect = locate_box(png, CLOSE_ICON_TARGET)
    if rect is None:
        return None
    width, height = png_size(png)
    x1, y1, x2, y2 = rect
    box_width, box_height = x2 - x1, y2 - y1
    if box_width <= 0 or box_height <= 0:
        return None
    # 关闭图标很小且接近正方形：过大的框多半是整张广告卡片，不点。
    if not (width * 0.015 <= box_width <= width * 0.15):
        return None
    if not (height * 0.007 <= box_height <= height * 0.10):
        return None
    if not (0.45 <= box_width / box_height <= 2.2):
        return None
    x, y = (x1 + x2) // 2, (y1 + y2) // 2
    print(f"视觉定位：{context} → 关闭图标 ({x}, {y})。", flush=True)
    return x, y


def _dismiss_point(
    result: dict | None, width: int, height: int
) -> tuple[tuple[int, int], str] | None:
    """校验模型给出的 D 类弹窗按钮：必须是白名单里的否定/关闭按钮。"""
    if not isinstance(result, dict) or result.get("page_type") != "D":
        return None
    dismiss = result.get("dismiss")
    if not isinstance(dismiss, dict):
        return None
    label = str(dismiss.get("label") or "").strip()
    if label not in DEFER_LABELS and label not in GENERIC_DISMISS_LABELS:
        return None
    try:
        x = float(dismiss.get("x"))
        y = float(dismiss.get("y"))
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        return None
    return (int(x * width / 1000), int(y * height / 1000)), label


def _close_point(result: dict | None, width: int, height: int) -> tuple[int, int] | None:
    """校验模型结论：必须是广告、close 非空，且坐标落在屏幕边缘区域。"""
    if not isinstance(result, dict):
        return None
    if result.get("page_type") != "C" or result.get("is_ad") is not True:
        return None
    close = result.get("close")
    if not isinstance(close, dict):
        return None
    try:
        x = float(close.get("x"))
        y = float(close.get("y"))
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        return None
    # 关闭/跳过控件常见位置：左右边缘、顶部两角、底部提示条；
    # 顶部居中或画面中部的一律不点，防止误触内容按钮。
    left_right_edge = x <= 220 or x >= 780
    top_corner = y <= 160 and (x <= 250 or x >= 750)
    bottom_band = y >= 880
    if not (left_right_edge or top_corner or bottom_band):
        return None
    return int(x * width / 1000), int(y * height / 1000)


def _screenshot(device_id: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=SCREENSHOT_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"视觉识别失败：截图超时（{type(exc).__name__}）。", flush=True)
        return None
    if result.returncode != 0 or not result.stdout:
        print("视觉识别失败：截图命令未返回图像。", flush=True)
        return None
    return result.stdout


def try_close(device_id: str, context: str = "", confirm: bool = False) -> bool:
    """识别当前画面并在确认存在关闭控件时点击；返回是否真的点击了。

    confirm=True 时，判定为广告后会间隔约 1.5 秒再截图复核一次，两次都确认
    是广告且都能定位关闭控件才点击。用于长时间挂机场景，避免视频画面被
    模型误判为广告后误点角落控件。
    """
    global _calls, _last_call_at, _cache_digest, _cache_result, _cache_at, _tapped_digest

    if not device_id:
        return False
    # 先走确定性路径：更新/升级弹窗按按钮文字关闭，不消耗视觉模型调用次数。
    if dismiss_update_dialog(device_id, context):
        return True
    if _api_config() is None:
        print("视觉识别跳过：未配置模型地址或密钥。", flush=True)
        return False

    now = time.monotonic()
    if _calls >= MAX_CALLS:
        print("视觉识别跳过：本次任务调用次数已达上限。", flush=True)
        return False
    if now - _last_call_at < MIN_CALL_INTERVAL:
        return False

    png = _screenshot(device_id)
    if png is None:
        return False
    digest = hashlib.sha256(png).hexdigest()
    width, height = png_size(png)

    if digest == _cache_digest and now - _cache_at < CACHE_TTL:
        verdict = _cache_result
    else:
        _calls += 1
        _last_call_at = now
        verdict = classify(png)
        _cache_digest = digest
        _cache_result = verdict
        _cache_at = now

    page_type = (verdict or {}).get("page_type", "?")
    is_ad = (verdict or {}).get("is_ad")
    reason = (verdict or {}).get("reason", "")
    if page_type == "C" and digest != _tapped_digest:
        # 广告页先按无障碍树里的真实关闭节点点击，避免模型坐标点空。
        if _tap_ad_close_by_ui(device_id, context):
            _tapped_digest = digest
            return True
    point = _close_point(verdict, width, height)
    dismiss_label = None
    if point is None:
        dismiss = _dismiss_point(verdict, width, height)
        if dismiss is not None:
            point, dismiss_label = dismiss
    if dismiss_label and digest != _tapped_digest:
        # D 类弹窗：模型给的按钮文字可信，但坐标常偏到画面中心，先按文字点。
        if tap_label(device_id, {dismiss_label}, context):
            _tapped_digest = digest
            return True
        # 无障碍树读不到界面（自动播放的视频页）时，再让操作模型按文字定位按钮。
        agent_point = _agent_tap_point(png, f"点击弹窗里的“{dismiss_label}”按钮")
        if agent_point is not None and _point_on_light_panel(png, agent_point):
            try:
                subprocess.run(
                    ["adb", "-s", device_id, "shell", "input", "tap",
                     str(agent_point[0]), str(agent_point[1])],
                    capture_output=True,
                    timeout=20,
                    check=True,
                )
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                pass
            else:
                _tapped_digest = digest
                print(
                    f"视觉识别：{context} → 页面=D，视觉点击「{dismiss_label}」"
                    f"({agent_point[0]}, {agent_point[1]})。",
                    flush=True,
                )
                time.sleep(1.0)
                return True
        # 否定按钮点不到时宁可不点：模型给的 D 类坐标可能落在“立即升级”上。
        print(f"视觉识别：{context} → 页面=D，未能定位「{dismiss_label}」，不点击。", flush=True)
        return False
    if page_type == "D":
        # D 类：模型可能给出“优先体验/立即升级”这类肯定按钮，按文字重新定位
        # 更新弹窗的否定按钮；找不到就什么都不点。
        if _tap_update_defer(png, device_id, context):
            _tapped_digest = digest
            return True
        print(f"视觉识别：{context} → 页面=D，未找到可点击的否定按钮，不操作。", flush=True)
        return False
    if point is None and page_type == "C":
        # 广告页模型没给出可信坐标时，单独定位小尺寸 X 图标并校验形状。
        icon = _locate_close_icon(device_id, png, context)
        if icon is not None:
            point = icon
    if point is None:
        print(
            f"视觉识别：{context} → 页面={page_type}，广告={is_ad}，"
            f"无可点击关闭控件（{reason}）。",
            flush=True,
        )
        return False

    if confirm:
        # 挂机场景：视频画面可能被误判成广告，复核一帧后再决定是否点击。
        time.sleep(1.5)
        png2 = _screenshot(device_id)
        if png2 is None:
            return False
        if _calls >= MAX_CALLS:
            print("视觉识别跳过：本次任务调用次数已达上限。", flush=True)
            return False
        _calls += 1
        _last_call_at = time.monotonic()
        width2, height2 = png_size(png2)
        verdict2 = classify(png2)
        point2 = _close_point(verdict2, width2, height2)
        label2 = None
        if point2 is None:
            dismiss2 = _dismiss_point(verdict2, width2, height2)
            if dismiss2 is not None:
                point2, label2 = dismiss2
        reason2 = (verdict2 or {}).get("reason", "")
        if point2 is None:
            print(
                f"视觉识别：{context} → 复核页面="
                f"{(verdict2 or {}).get('page_type', '?')}，广告="
                f"{(verdict2 or {}).get('is_ad')}，未确认广告，不点击（{reason2}）。",
                flush=True,
            )
            return False
        point = point2
        dismiss_label = label2
        reason = reason2

    if digest == _tapped_digest:
        # 同一画面已经点过关闭控件仍未变化，避免连续误点。
        print(f"视觉识别：{context} → 已点过该画面的关闭控件，画面未变化，停止重试。", flush=True)
        return False

    x, y = point
    try:
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            timeout=20,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
        print(f"视觉识别失败：点击关闭控件失败（{type(exc).__name__}）。", flush=True)
        return False

    _tapped_digest = digest
    if dismiss_label:
        print(
            f"视觉识别：{context} → 页面=D，点击「{dismiss_label}」({x}, {y})（{reason}）。",
            flush=True,
        )
    else:
        print(
            f"视觉识别：{context} → 页面=C，点击关闭控件 ({x}, {y})（{reason}）。",
            flush=True,
        )
    time.sleep(1.0)
    return True


LOCATE_PROMPT = """你是手机界面定位器。给你一张手机截图和一段目标控件描述，找出目标控件的外框。
规则：
1. 只定位与描述完全匹配的控件；画面里没有就返回 found=false，不要猜测，也不要退而求其次。
2. 用画面千分比给出外框：左上角 (0,0)，右下角 (1000,1000)；(x1,y1) 是控件左上角，(x2,y2) 是右下角，框要紧贴控件本身。
3. 只输出一行 JSON：{"found":true|false,"box":{"x1":整数,"y1":整数,"x2":整数,"y2":整数}|null,"reason":"不超过15字"}"""


VERIFY_PROMPT = """你是严格的界面控件核对员。给你的图片是从手机截图里裁出的一个候选区域，可能带少量周边画面。
请判断这块区域是否就是用户描述的目标控件本身。
规则：
1. 候选区域横跨多个并列控件（如一行功能图标、标签栏、多行列表）时，match=false。
2. 区域里没有目标控件，或目标文字与描述不符时，match=false。
3. 看不清、拿不准时一律 match=false，不要猜测、不要勉强算通过。
4. 只输出一行 JSON：{"match":true|false,"reason":"不超过15字"}"""


def _crop_png(png: bytes, rect: tuple[int, int, int, int], pad_ratio: float = 0.15) -> bytes | None:
    """按外框裁出候选区域（带少量外扩），用于二次核对。"""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        image = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:
        return None
    width, height = image.size
    x1, y1, x2, y2 = rect
    pad_x = int((x2 - x1) * pad_ratio) + 4
    pad_y = int((y2 - y1) * pad_ratio) + 4
    left, top = max(0, x1 - pad_x), max(0, y1 - pad_y)
    right, bottom = min(width, x2 + pad_x), min(height, y2 + pad_y)
    if right <= left or bottom <= top:
        return None
    buffer = io.BytesIO()
    image.crop((left, top, right, bottom)).save(buffer, "PNG")
    return buffer.getvalue()


def verify_box(png: bytes, rect: tuple[int, int, int, int], target: str) -> bool:
    """把候选外框裁出来再问一次模型：这块区域是否就是目标控件本身。

    区域/宽高/长宽比只能证明“形状像”，证明不了“选对了”。某次
    App 首页的搜索框定位就通过了形状校验，但纵向偏到功能图标行。这里任何
    不确定的情况都返回 False（不点击）。
    """
    global _calls, _last_call_at
    config = _api_config()
    if config is None or not (target or "").strip():
        return False
    crop = _crop_png(png, rect)
    if crop is None:
        return False
    if _calls >= MAX_CALLS:
        print("视觉核对跳过：本次任务调用次数已达上限。", flush=True)
        return False
    wait = MIN_CALL_INTERVAL - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _calls += 1
    _last_call_at = time.monotonic()

    url, api_key, model = config
    image, mime = _prepare_image(crop)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": VERIFY_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
                        },
                    },
                    {"type": "text", "text": f"目标控件：{target}。只输出 JSON。"},
                ],
            },
        ],
        "max_tokens": 800,
        "temperature": 0.0,
        **_thinking_body(),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return False
    result = _parse_json(content if isinstance(content, str) else "")
    if not isinstance(result, dict):
        return False
    if result.get("match") is True:
        return True
    reason = str(result.get("reason") or "")
    print(f"视觉核对：目标“{target[:24]}”被判定不匹配（{reason[:20]}）。", flush=True)
    return False


def locate_box(png: bytes, target: str) -> tuple[int, int, int, int] | None:
    """按文字描述在截图里定位控件外框，返回原图像素 (x1, y1, x2, y2)。

    调用方可以据此校验控件形状（如搜索框必须宽而扁），再决定是否点击，
    避免模型把标签栏、状态栏错认成目标控件。调用同样受次数和间隔限制。
    """
    global _calls, _last_call_at
    config = _api_config()
    if config is None or not (target or "").strip():
        return None
    if _calls >= MAX_CALLS:
        print("视觉定位跳过：本次任务调用次数已达上限。", flush=True)
        return None
    wait = MIN_CALL_INTERVAL - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _calls += 1
    _last_call_at = time.monotonic()

    url, api_key, model = config
    image, mime = _prepare_image(png)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": LOCATE_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"},
                    },
                    {"type": "text", "text": f"目标控件：{target}。只输出 JSON。"},
                ],
            },
        ],
        "max_tokens": 800,
        "temperature": 0.0,
        **_thinking_body(),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    result = _parse_json(content if isinstance(content, str) else "")
    if not isinstance(result, dict) or result.get("found") is not True:
        reason = (result or {}).get("reason", "无结论")
        print(f"视觉定位未找到“{target}”（{reason}）。", flush=True)
        return None
    box = result.get("box")
    if not isinstance(box, dict):
        return None
    try:
        x1 = float(box.get("x1"))
        y1 = float(box.get("y1"))
        x2 = float(box.get("x2"))
        y2 = float(box.get("y2"))
    except (TypeError, ValueError):
        return None
    if not all(0 <= value <= 1000 for value in (x1, y1, x2, y2)) or x2 <= x1 or y2 <= y1:
        return None
    width, height = png_size(png)
    return (
        int(x1 * width / 1000),
        int(y1 * height / 1000),
        int(x2 * width / 1000),
        int(y2 * height / 1000),
    )


def locate(png: bytes, target: str) -> tuple[int, int] | None:
    """按文字描述在截图里定位控件中心，返回原图像素坐标；不确认时返回 None。"""
    rect = locate_box(png, target)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    return (x1 + x2) // 2, (y1 + y2) // 2


def is_text_page(device_id: str, context: str = "") -> bool | None:
    """用视觉模型判断当前是否为阅读正文页（A）。

    用于像素统计落在“文字很淡/过渡动画”灰区时兜底：模型确认 A 就继续阅读，
    不再因为暗色占比略低而判定失败。未配置模型、限流或调用失败返回 None。
    """
    global _calls, _last_call_at, _cache_digest, _cache_result, _cache_at

    if not device_id or _api_config() is None:
        return None
    now = time.monotonic()
    if _calls >= MAX_CALLS:
        return None
    if now - _last_call_at < MIN_CALL_INTERVAL:
        return None
    png = _screenshot(device_id)
    if png is None:
        return None
    digest = hashlib.sha256(png).hexdigest()
    if digest == _cache_digest and now - _cache_at < CACHE_TTL:
        verdict = _cache_result
    else:
        _calls += 1
        _last_call_at = now
        verdict = classify(png)
        _cache_digest = digest
        _cache_result = verdict
        _cache_at = now
    if not isinstance(verdict, dict):
        return None
    page_type = verdict.get("page_type")
    if page_type not in {"A", "B", "C", "D"}:
        return None
    print(
        f"视觉识别：{context} → 页面={page_type}（{verdict.get('reason', '')}）。",
        flush=True,
    )
    return page_type == "A"


def available() -> bool:
    return _api_config() is not None


PROMPT_HINTS = (
    "添加至桌面", "添加到桌面", "添加到主屏幕", "创建快捷方式", "创建桌面快捷方式",
)
PROMPT_DISMISS_LABELS = {
    "取消", "关闭", "以后再说", "下次再说", "暂不添加", "不添加",
}

# 阅读类 App 中途会弹“你对这本书的内容满意吗”评价框；它的关闭 X 是没有
# 文字和描述的图标，按钮文字匹配不到，只能按标题同一行的最左侧小图标定位。
RATING_POPUP_HINTS = ("你对这本书的内容满意吗", "提交反馈")
RATING_POPUP_ACTIVITIES = ("BottomPopupContainer",)


def _rating_popup_open(root) -> bool:
    for node in root.iter("node"):
        text = node.attrib.get("text") or ""
        if any(hint in text for hint in RATING_POPUP_HINTS):
            return True
    return False


def _current_activity(device_id: str) -> str:
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "shell", "dumpsys", "window"],
            capture_output=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    match = re.search(
        rb"mCurrentFocus=Window\{[^\n]*? u\d+ ([^/\s]+)/([^}\s]+)\}",
        result.stdout or b"",
    )
    if not match:
        return ""
    return match.group(2).decode("utf-8", "replace")


def _press_back(device_id: str) -> bool:
    try:
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "keyevent", "4"],
            capture_output=True,
            timeout=20,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return False
    time.sleep(1.0)
    return True


def _tap_rating_close(root, device_id: str, context: str) -> bool:
    """在标题行最左侧找无文字的可点击小图标（评价框的关闭 X）。"""
    title = None
    for node in root.iter("node"):
        text = node.attrib.get("text") or ""
        if any(hint in text for hint in RATING_POPUP_HINTS):
            title = node
            break
    if title is None:
        return False
    match = BOUNDS_RE.search(title.attrib.get("bounds", ""))
    if match is None:
        return False
    _left, title_top, _right, title_bottom = (int(value) for value in match.groups())
    row_height = max(title_bottom - title_top, 1)
    row_top = title_top - row_height
    row_bottom = title_bottom + row_height
    best = None
    for node in root.iter("node"):
        if node.attrib.get("clickable") != "true":
            continue
        if (node.attrib.get("text") or "").strip():
            continue
        if (node.attrib.get("content-desc") or "").strip():
            continue
        node_match = BOUNDS_RE.search(node.attrib.get("bounds", ""))
        if node_match is None:
            continue
        left, top, right, bottom = (int(value) for value in node_match.groups())
        if right <= left or bottom <= top:
            continue
        if bottom < row_top or top > row_bottom:
            continue
        if best is None or left < int(
            BOUNDS_RE.search(best.attrib.get("bounds", "")).group(1)
        ):
            best = node
    if best is None:
        return False
    return _tap(best, device_id, "评价框关闭X", context)


def dismiss_rating_popup(device_id: str, context: str = "") -> bool:
    """关闭 Dragon Read 的评价框：X 图标优先，找不到才按返回键。"""
    if not device_id:
        return False
    root = _dump_ui(device_id)
    if root is None:
        return False
    if not _rating_popup_open(root):
        return False
    if _tap_rating_close(root, device_id, f"{context}（评价框）"):
        return True
    activity = _current_activity(device_id)
    if any(hint in activity for hint in RATING_POPUP_ACTIVITIES):
        if _press_back(device_id):
            print(f"{context} → 已按返回键关闭评价框。", flush=True)
            return True
    return False


def _area_of(node) -> int:
    match = BOUNDS_RE.search(node.attrib.get("bounds", ""))
    if not match:
        return 0
    x1, y1, x2, y2 = (int(value) for value in match.groups())
    return max(0, x2 - x1) * max(0, y2 - y1)


_SCREEN_AREA_CACHE: dict[str, int] = {}


def _screen_area(device_id: str) -> int:
    """物理屏幕面积；弹窗窗体的根节点只占屏幕局部，不能当整屏用。"""
    cached = _SCREEN_AREA_CACHE.get(device_id)
    if cached:
        return cached
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "shell", "wm", "size"],
            capture_output=True,
            timeout=10,
        )
        match = re.search(rb"(\d+)x(\d+)", result.stdout or b"")
        if match:
            area = int(match.group(1)) * int(match.group(2))
            _SCREEN_AREA_CACHE[device_id] = area
            return area
    except (subprocess.TimeoutExpired, OSError):
        pass
    return 0


def _shares_hint_container(node, parents, hints, screen_area=0) -> bool:
    """按钮与提示文案必须同处一个弹窗容器（向上最多 6 层）。

    只看“全屏出现文案”会把页面上的“取消/关闭”和正文里的“更新”二字
    凑成一对；但只向上找祖先又会一路走到整屏根节点，同样误判。这里额外
    要求容器面积小于屏幕的 75%：真正的弹窗容器不会占满整个屏幕，而一旦
    祖先超过这个面积，更高的祖先只会更大，可直接放弃。
    """
    if not screen_area:
        # 拿不到物理屏幕尺寸时退回 dump 根节点；注意弹窗独占窗口时它只占局部。
        root = node
        while parents.get(root) is not None and parents[root].tag == "node":
            root = parents[root]
        screen_area = _area_of(root)
    candidate = parents.get(node)
    for _ in range(6):
        if candidate is None:
            return False
        if screen_area:
            box_area = _area_of(candidate)
            if box_area >= screen_area * 0.75:
                return False
        for child in candidate.iter("node"):
            text = (child.attrib.get("text") or "").strip()
            if any(hint in text for hint in hints):
                return True
        candidate = parents.get(candidate)
    return False


def dismiss_blocking_prompts(device_id: str, context: str = "") -> list[str]:
    """一次 dump 同时处理更新弹窗和“添加至桌面/创建快捷方式”类提示框。

    这类弹窗出现在最上层时，uiautomator 只返回弹窗自身的界面，脚本读不到
    底下的搜索框/正文，于是验证或等待超时。按钮文字与提示文案必须处于同一
    容器，避免把页面上的普通“取消”按钮误点掉。返回被点击的按钮文字。
    """
    if not device_id:
        return []
    root = _dump_ui(device_id)
    if root is None:
        return []
    parents = {child: parent for parent in root.iter() for child in parent}
    screen_area = _screen_area(device_id)
    clicked: list[str] = []

    def find_button(labels, hints):
        for node in root.iter("node"):
            if node.attrib.get("clickable") != "true":
                continue
            label = (node.attrib.get("text") or "").strip().rstrip("。.!！~ ")
            if label not in labels:
                continue
            if not _shares_hint_container(node, parents, hints, screen_area):
                continue
            return node, label
        return None

    container = _update_dialog_container(root, parents, screen_area)
    if container is not None:
        node, label = _update_control_in_container(container, parents, screen_area)
        if node is not None and _tap(node, device_id, label, f"{context}（更新提示）"):
            clicked.append(label)
        elif _press_back(device_id):
            print(f"{context} → 更新提示无关闭控件，已按返回键。", flush=True)
            clicked.append("更新提示返回键")
    prompt = find_button(PROMPT_DISMISS_LABELS, PROMPT_HINTS)
    if prompt is not None and _tap(prompt[0], device_id, prompt[1], f"{context}（提示框）"):
        clicked.append(prompt[1])
    if _rating_popup_open(root):
        if _tap_rating_close(root, device_id, f"{context}（评价框）"):
            clicked.append("评价框关闭")
        elif any(hint in _current_activity(device_id) for hint in RATING_POPUP_ACTIVITIES):
            if _press_back(device_id):
                print(f"{context} → 已按返回键关闭评价框。", flush=True)
                clicked.append("评价框返回键关闭")
    return clicked


# ---------------------------------------------------------------------------
# 视觉定位兜底：无障碍树读不到界面时（自动播放的视频页，uiautomator 永远
# 报 “could not get idle state”），用手机操作模型按文字描述定位并点击控件。
# ---------------------------------------------------------------------------

GROUND_INSTRUCTION = (
    "{target}。只回答该控件的中心坐标，格式为：坐标 (x, y)，"
    "x、y 是 0 到 1000 的整数，左上角是 (0, 0)，右下角是 (1000, 1000)。"
)

COORD_RE = re.compile(r"\((\d{1,4})\s*[,，]\s*(\d{1,4})\)")

# 更新弹窗只允许点否定/延迟按钮，绝不点“立即升级/优先体验”。
UPDATE_DIALOG_TARGETS = ("以后再说", "暂不更新", "稍后再说", "下次再说", "暂不升级")


def _agent_tap_point(png: bytes, target: str) -> tuple[int, int] | None:
    """用手机操作模型定位控件中心，返回原图像素坐标；拿不到返回 None。

    这类模型不输出严格 JSON，但会给出“坐标 (x, y)”形式的千分比坐标；只取
    第一条坐标并做范围校验，超过 1000 的一律视为无效，避免点到别处。
    """
    global _calls, _last_call_at

    config = _api_config()
    if config is None or not (target or "").strip():
        return None
    if _calls >= MAX_CALLS:
        print("视觉定位跳过：本次任务调用次数已达上限。", flush=True)
        return None
    wait = MIN_CALL_INTERVAL - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _calls += 1
    _last_call_at = time.monotonic()

    url, api_key, vision_model = config
    model = (os.environ.get("PHONE_AGENT_MODEL") or "").strip() or vision_model
    image, mime = _prepare_image(png)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
                        },
                    },
                    {"type": "text", "text": GROUND_INSTRUCTION.format(target=target)},
                ],
            }
        ],
        "max_tokens": 800,
        "temperature": 0.0,
        **_thinking_body(),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(content, str):
        return None
    match = COORD_RE.search(content)
    if not match:
        print(f"视觉定位：{target} → 模型未给出坐标。", flush=True)
        return None
    x_raw, y_raw = int(match.group(1)), int(match.group(2))
    if not (0 <= x_raw <= 1000 and 0 <= y_raw <= 1000):
        print(f"视觉定位：{target} → 坐标越界（{x_raw}, {y_raw}）。", flush=True)
        return None
    width, height = png_size(png)
    return int(x_raw * width / 1000), int(y_raw * height / 1000)


def _point_on_light_panel(png: bytes, point: tuple[int, int]) -> bool:
    """校验点击点落在一块大面积浅色区域（弹窗面板），避免点到视频画面。

    没有 Pillow 时无法校验，按模型结论执行；有 Pillow 时连通区域不足屏幕
    2% 或该点本身不是浅色，就判定模型点错了。
    """
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return True
    try:
        image = Image.open(io.BytesIO(png)).convert("L")
        width, height = image.size
        step = 4
        small = image.resize((max(1, width // step), max(1, height // step)))
        pixels = small.load()
        sw, sh = small.size
        sx, sy = point[0] // step, point[1] // step
        if not (0 <= sx < sw and 0 <= sy < sh) or pixels[sx, sy] < 190:
            return False
        limit = max(200, int(sw * sh * 0.02))
        seen = {(sx, sy)}
        stack = [(sx, sy)]
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbour = (x + dx, y + dy)
                if not (0 <= neighbour[0] < sw and 0 <= neighbour[1] < sh):
                    continue
                if neighbour in seen or pixels[neighbour[0], neighbour[1]] < 190:
                    continue
                seen.add(neighbour)
                if len(seen) >= limit:
                    return True
                stack.append(neighbour)
        return False
    except Exception:  # noqa: BLE001
        return True


def _tap_update_defer(png: bytes, device_id: str, context: str) -> bool:
    """在给定截图上找更新弹窗的否定按钮并点击；找不到返回 False。"""
    for label in UPDATE_DIALOG_TARGETS:
        point = _agent_tap_point(png, f"点击应用更新弹窗里的“{label}”按钮")
        if point is None:
            continue
        if not _point_on_light_panel(png, point):
            print(
                f"视觉定位：{context} → “{label}”坐标 {point} 不在弹窗面板上，不点击。",
                flush=True,
            )
            continue
        try:
            subprocess.run(
                ["adb", "-s", device_id, "shell", "input", "tap",
                 str(point[0]), str(point[1])],
                capture_output=True,
                timeout=20,
                check=True,
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            return False
        global _cache_digest
        _cache_digest = None
        print(f"更新提示：{context} → 视觉点击「{label}」({point[0]}, {point[1]})。", flush=True)
        time.sleep(0.8)
        return True
    return False


def dismiss_update_dialog_by_vision(device_id: str, context: str = "") -> bool:
    """无障碍树读不到界面时，用视觉模型定位更新弹窗的否定按钮并点击。

    只有“立即更新”按钮的弹窗没有否定按钮，退一步定位右上角的关闭 X 图标；
    图标必须落在浅色弹窗面板上才点击，避免点到画面里的其他内容。
    """
    if not device_id or _api_config() is None:
        return False
    png = _screenshot(device_id)
    if png is None:
        return False
    if _tap_update_defer(png, device_id, context):
        return True
    point = _locate_close_icon(device_id, png, f"{context}（更新弹窗关闭图标）")
    if point is not None and _point_on_light_panel(png, point):
        try:
            subprocess.run(
                ["adb", "-s", device_id, "shell", "input", "tap",
                 str(point[0]), str(point[1])],
                capture_output=True,
                timeout=20,
                check=True,
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            return False
        global _cache_digest
        _cache_digest = None
        print(f"更新提示：{context} → 视觉点击关闭图标 ({point[0]}, {point[1]})。", flush=True)
        time.sleep(0.8)
        return True
    print(f"视觉定位：{context} → 未找到更新弹窗的否定按钮。", flush=True)
    return False


PAGE_IDENTIFY_PROMPT = (
    "这是一张安卓手机截图。请从下面的词表里选一个最符合当前画面的：{options}。"
    "只输出词表里的一个词，不要解释、不要标点；都不符合就输出：其他。"
)


def _classify_image(
    url: str,
    api_key: str,
    model: str,
    image: bytes,
    mime: str,
    options: tuple[str, ...],
    question: str | None = None,
) -> str | None:
    """用指定模型做一次页面分类，返回模型原文；请求失败返回 None。"""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            PAGE_IDENTIFY_PROMPT.format(options="、".join(options))
                            if not question
                            else (
                                f"这是一张安卓手机截图。{question}"
                                "请只从下面的词表里选一个最符合的："
                                f"{'、'.join(options)}；都不符合就输出：其他。"
                                "只输出选中的词，不要解释、不要标点。"
                            )
                        ),
                    },
                ],
            }
        ],
        "max_tokens": 800,
        "temperature": 0.0,
        **_thinking_body(),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(content, str):
        return None
    return content.strip()


def identify_page_png(
    png: bytes,
    options: tuple[str, ...],
    context: str = "",
    question: str | None = None,
) -> str | None:
    """用视觉模型从给定词表里识别页面类型；截图或模型失败返回 None。

    视觉模型（网页“视觉模型”字段）不可用（如欠费 429）时，自动回退到同一
    配置里的手机操作模型，保证页面识别在全部脚本里都能用。
    """
    config = _api_config()
    if config is None or not png or not options:
        return None
    url, api_key, vision_model = config
    agent_model = (os.environ.get("PHONE_AGENT_MODEL") or "").strip()
    models: list[str] = []
    for candidate in (vision_model, agent_model):
        if candidate and candidate not in models:
            models.append(candidate)
    image, mime = _prepare_image(png)
    for model in models:
        text = _classify_image(url, api_key, model, image, mime, options, question)
        if not text:
            # 空字符串也视为失败（推理模型思考过长被 max_tokens 截断时正文为空），
            # 继续尝试备选模型，不再直接归为“其他”把兜底废掉。
            continue
        for option in options:
            if option in text:
                print(f"视觉识别：{context} → 页面={option}（{model}）", flush=True)
                return option
        print(f"视觉识别：{context} → 模型回答“{text[:40]}”，归为其他。", flush=True)
        return "其他" if "其他" in options else None
    print(f"视觉识别：{context} → 模型调用失败，跳过。", flush=True)
    return None


def identify_page(
    device_id: str,
    options: tuple[str, ...],
    context: str = "",
    question: str | None = None,
) -> str | None:
    """截图后识别当前页面类型（跨机型，不依赖无障碍树）。"""
    if not device_id or _api_config() is None:
        return None
    png = None
    for _attempt in range(3):
        png = _screenshot(device_id)
        if png is not None:
            break
        time.sleep(1.0)
    if png is None:
        print(f"视觉识别：{context} → 截图连续失败，跳过。", flush=True)
        return None
    return identify_page_png(png, options, context, question)


def agent_point(png: bytes, target: str) -> tuple[int, int] | None:
    """公开的手机操作模型定位接口：按中文描述给出原图像素坐标。"""
    return _agent_tap_point(png, target)


def tap_agent(
    device_id: str,
    target: str,
    context: str = "",
    validate_light_panel: bool = False,
) -> bool:
    """按描述定位并点击一个控件；跨机型恢复路径统一走这里。"""
    if not device_id or _api_config() is None:
        return False
    png = None
    for _attempt in range(3):
        png = _screenshot(device_id)
        if png is not None:
            break
        time.sleep(1.0)
    if png is None:
        print(f"视觉定位：{context} → 截图连续失败，跳过。", flush=True)
        return False
    point = _agent_tap_point(png, target)
    if point is None:
        return False
    if validate_light_panel and not _point_on_light_panel(png, point):
        print(f"视觉定位：{context} → 坐标 {point} 不在浅色面板上，不点击。", flush=True)
        return False
    try:
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap",
             str(point[0]), str(point[1])],
            capture_output=True,
            timeout=20,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return False
    global _cache_digest
    _cache_digest = None
    print(f"视觉点击：{context or target} → ({point[0]}, {point[1]})。", flush=True)
    time.sleep(0.8)
    return True


def tap_target(
    device_id: str,
    target: str,
    context: str = "",
    region: tuple[float, float, float, float] | None = None,
    min_width: float = 0.0,
    max_width: float = 1.0,
    min_height: float = 0.0,
    max_height: float = 1.0,
    min_aspect: float = 0.0,
    max_aspect: float = 0.0,
    confirm: bool = False,
) -> bool:
    """定位一个控件，通过区域和形状校验后再点击；返回是否真的点击了。

    与 tap_agent 的差别：这里要求视觉模型给出结构化外框（locate_box），调用方
    可以限定目标必须出现在画面某个区域，并限制宽、高和长宽比，把状态栏、底部
    标签栏、剧情互动按钮这类“位置接近但不是目标”的误定位挡在点击之前。

    region 是画面相对区域 (左, 上, 右, 下)，取值 0~1，按目标框中心判断；
    宽高参数同样是相对屏幕比例。任何一项校验不通过都不点击。

    confirm=True 时还会把候选框裁出来再问模型一次（verify_box），用于挡掉
    “形状合格但选错控件”的定位；这是唯一会在点击前多看一帧的模式。
    """
    global _cache_digest

    if not device_id or _api_config() is None:
        return False
    label = context or target
    png = None
    for _attempt in range(2):
        png = _screenshot(device_id)
        if png is not None:
            break
        time.sleep(1.0)
    if png is None:
        print(f"视觉定位：{label} → 截图连续失败，跳过。", flush=True)
        return False

    rect = locate_box(png, target)
    if rect is None:
        return False
    width, height = png_size(png)
    x1, y1, x2, y2 = rect
    center_x, center_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    box_width = (x2 - x1) / float(width)
    box_height = (y2 - y1) / float(height)
    if region is not None:
        left, top, right, bottom = region
        if not (
            left * width <= center_x <= right * width
            and top * height <= center_y <= bottom * height
        ):
            print(
                f"视觉定位：{label} → 目标中心 ({int(center_x)}, {int(center_y)}) "
                "不在预期区域内，不点击。",
                flush=True,
            )
            return False
    if not (min_width <= box_width <= max_width and min_height <= box_height <= max_height):
        print(
            f"视觉定位：{label} → 目标尺寸 {box_width:.1%}x{box_height:.1%} "
            "不符合控件形状，不点击。",
            flush=True,
        )
        return False
    aspect = box_width / box_height if box_height > 0 else 0.0
    if (min_aspect and aspect < min_aspect) or (max_aspect and aspect > max_aspect):
        print(
            f"视觉定位：{label} → 目标长宽比 {aspect:.2f} 不符合控件形状，不点击。",
            flush=True,
        )
        return False

    if confirm and not verify_box(png, rect, target):
        print(f"视觉定位：{label} → 候选框 {rect} 二次核对未通过，不点击。", flush=True)
        return False

    x, y = int(center_x), int(center_y)
    try:
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            timeout=20,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return False
    _cache_digest = None
    print(f"视觉定位：{label} → 点击 ({x}, {y})，目标框 {rect}。", flush=True)
    time.sleep(0.8)
    return True
