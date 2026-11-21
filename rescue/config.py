"""oag-rescue 配置：独立于平台 model_configs 的一份救援模型配置。

为什么要单独一份而不是复用平台默认配置：
1. 平台的 model_configs 读取接口对 api_key 做了掩码，救援服务拿不到真值；
2. 用户要求救援模型可以在网页上随时更换，且不影响主流程模型；
3. 救援服务与平台进程解耦，任一重启不牵连对方。

api_key 只写入、不回读：GET /v1/settings 永远只返回是否已配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict

_HERE = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.environ.get("OAG_RESCUE_DB", "rescue.db")
SCREENSHOT_DIR = os.environ.get("OAG_RESCUE_SCREENSHOTS", "rescue-screenshots")
SKILLS_DIR = os.environ.get("OAG_RESCUE_SKILLS", os.path.join(_HERE, "skills"))
DRAFT_DIR = os.path.join(SKILLS_DIR, "_draft")
SCREENSHOT_RETENTION_DAYS = int(os.environ.get("OAG_RESCUE_RETENTION_DAYS", "14"))

# 与平台脚本用同一个 adb；vision_ads 里是裸 "adb"，靠 PATH 找到它。留空则不注入。
ADB_DIR = os.environ.get("OAG_ADB_DIR", "")
PLATFORM_ROOT = os.environ.get("OAG_PLATFORM_ROOT", "")

MAX_SECONDS = 150          # 单次救援硬上限（客户端等 180s，留 30s 回传余量）
MAX_VISION_CALLS = 3       # 每次救援最多几次视觉判定，防止模型反复试
MAX_TOOL_CALLS = 40        # 单次救援的动作上限


@dataclass
class RescueSettings:
    enabled: int = 0
    # 操作模型（PhoneAgent 接管现场用）
    provider: str = "openai"
    base_url: str = ""
    model_name: str = ""
    api_key: str = ""
    # 视觉识别模型（独立一套，可为空；为空时回落到操作模型）
    vision_model: str = ""
    vision_base_url: str = ""
    vision_api_key: str = ""
    vision_disable_thinking: int = 0
    max_seconds: int = MAX_SECONDS
    max_vision_calls: int = MAX_VISION_CALLS

    @property
    def vision_ready(self) -> bool:
        """视觉独立配置是否齐全（Base URL + Key + 模型名）。"""
        return bool(self.vision_base_url and self.vision_api_key and self.vision_model)

    def public(self) -> dict:
        """返回给网页的形态：两套密钥都只暴露“是否已配置”。"""
        data = asdict(self)
        data.pop("api_key", None)
        data.pop("vision_api_key", None)
        data["api_key_configured"] = bool(self.api_key)
        data["vision_api_key_configured"] = bool(self.vision_api_key)
        data["vision_configured"] = self.vision_ready
        return data

    def apply_env(self) -> None:
        """把配置注入进程环境变量，vision_ads / vision_fallback 据此选模型。"""
        os.environ["PHONE_AGENT_PROVIDER"] = self.provider or "openai"
        os.environ["PHONE_AGENT_BASE_URL"] = self.base_url or ""
        os.environ["PHONE_AGENT_MODEL"] = self.model_name or ""
        os.environ["PHONE_AGENT_API_KEY"] = self.api_key or ""
        os.environ["PHONE_AGENT_DISABLE_THINKING"] = "0"
        # 视觉独立配置齐全时用它；否则清掉相关变量，让 vision_ads 回落到
        # 上面的操作模型 + vision_model（旧行为）。
        vision_keys = (
            "PHONE_AGENT_VISION_BASE_URL",
            "PHONE_AGENT_VISION_API_KEY",
            "PHONE_AGENT_VISION_MODEL",
            "PHONE_AGENT_VISION_DISABLE_THINKING",
        )
        if self.vision_ready:
            os.environ["PHONE_AGENT_VISION_BASE_URL"] = self.vision_base_url
            os.environ["PHONE_AGENT_VISION_API_KEY"] = self.vision_api_key
            os.environ["PHONE_AGENT_VISION_MODEL"] = self.vision_model
            os.environ["PHONE_AGENT_VISION_DISABLE_THINKING"] = (
                "1" if self.vision_disable_thinking else "0"
            )
        else:
            for key in vision_keys:
                os.environ.pop(key, None)
            os.environ["PHONE_AGENT_VISION_MODEL"] = self.vision_model or ""
        if ADB_DIR:
            path = os.environ.get("PATH", "")
            if ADB_DIR not in path.split(os.pathsep):
                os.environ["PATH"] = ADB_DIR + os.pathsep + path


DEFAULTS = RescueSettings()