"""Vision model configuration service.

网页「视觉模型」卡片读写的单行表 vision_model_config；脚本启动时把这里的
Base URL / Key / 模型名注入 PHONE_AGENT_VISION_*，vision_ads 优先使用它们。
未配置（三项不全）时返回空，vision_ads 回落到手机操作模型那一套。
"""

import time
from typing import Optional

from app.db import db
from app.schemas.model_config import ModelConfigCreate, ModelConfigTestResponse
from app.schemas.vision_model_config import VisionModelConfigResponse, VisionModelConfigUpdate
from app.services.model_config_service import ModelConfigService, _normalize_base_url

ROW_ID = 1
MASKED_KEY = "******"


def _clean(value):
    return value.strip() if isinstance(value, str) else value


class VisionModelConfigService:
    async def _row(self):
        conn = await db.get_connection()
        cursor = await conn.execute(
            """SELECT provider, base_url, api_key, model_name, disable_thinking, updated_at
               FROM vision_model_config WHERE id = ?""",
            (ROW_ID,),
        )
        return await cursor.fetchone()

    async def get_config(self) -> VisionModelConfigResponse:
        row = await self._row()
        if not row:
            return VisionModelConfigResponse()
        api_key = (row["api_key"] or "").strip()
        base_url = (row["base_url"] or "").strip()
        model_name = (row["model_name"] or "").strip()
        return VisionModelConfigResponse(
            provider=row["provider"] or "openai",
            base_url=base_url,
            api_key=MASKED_KEY if api_key else "",
            model_name=model_name,
            disable_thinking=bool(row["disable_thinking"]),
            api_key_configured=bool(api_key),
            configured=bool(api_key and base_url and model_name),
            updated_at=row["updated_at"],
        )

    async def save(self, update: VisionModelConfigUpdate) -> VisionModelConfigResponse:
        conn = await db.get_connection()
        existing = await self._row()
        update_data = update.model_dump(exclude_unset=True)

        # 空字符串/掩码占位符表示“保持原密钥”，绝不能把掩码写回数据库。
        if update_data.get("api_key") in ("", MASKED_KEY, None):
            update_data.pop("api_key", None)

        fields, values = [], []
        for key, value in update_data.items():
            if key in ("base_url", "model_name", "provider"):
                value = _clean(value)
            if key == "disable_thinking":
                value = 1 if value else 0
            fields.append(f"{key} = ?")
            values.append(value)

        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not existing:
            await conn.execute(
                """INSERT INTO vision_model_config
                   (id, provider, base_url, api_key, model_name, disable_thinking, updated_at)
                   VALUES (?, 'openai', '', '', '', 0, ?)""",
                (ROW_ID, now),
            )
        if fields:
            fields.append("updated_at = ?")
            values.extend([now, ROW_ID])
            await conn.execute(
                f"UPDATE vision_model_config SET {', '.join(fields)} WHERE id = ?", values
            )
        await conn.commit()
        return await self.get_config()

    async def _effective(self, update: Optional[VisionModelConfigUpdate] = None) -> Optional[dict]:
        """合并“已保存 + 本次提交（未保存）”的配置，用于测试连接。"""
        row = await self._row()
        merged = {
            "provider": (row["provider"] if row else "openai") or "openai",
            "base_url": (row["base_url"] if row else "") or "",
            "api_key": (row["api_key"] if row else "") or "",
            "model_name": (row["model_name"] if row else "") or "",
            "disable_thinking": bool(row["disable_thinking"]) if row else False,
        }
        if update:
            data = update.model_dump(exclude_unset=True)
            if data.get("api_key") in ("", MASKED_KEY, None):
                data.pop("api_key", None)
            for key, value in data.items():
                merged[key] = _clean(value) if key in ("base_url", "model_name", "provider") else value
        if not (merged["base_url"] and merged["api_key"] and merged["model_name"]):
            return None
        return merged

    async def test(self, update: Optional[VisionModelConfigUpdate] = None) -> ModelConfigTestResponse:
        config = await self._effective(update)
        if not config:
            return ModelConfigTestResponse(
                success=False,
                message="视觉模型配置不完整：需要 Base URL、API Key、模型名称",
            )
        return await ModelConfigService()._test_openai(
            ModelConfigCreate(
                name="vision-test",
                provider=config["provider"] or "openai",
                base_url=config["base_url"],
                api_key=config["api_key"],
                model_name=config["model_name"],
                disable_thinking=bool(config["disable_thinking"]),
                is_default=False,
            )
        )

    async def env(self) -> dict:
        """注入脚本子进程的视觉模型环境变量；未配置完整时返回空字典。"""
        row = await self._row()
        if not row:
            return {}
        api_key = (row["api_key"] or "").strip()
        base_url = (row["base_url"] or "").strip()
        model_name = (row["model_name"] or "").strip()
        if not (api_key and base_url and model_name):
            return {}
        return {
            "PHONE_AGENT_VISION_BASE_URL": _normalize_base_url(base_url),
            "PHONE_AGENT_VISION_API_KEY": api_key,
            "PHONE_AGENT_VISION_MODEL": model_name,
            "PHONE_AGENT_VISION_DISABLE_THINKING": "1" if row["disable_thinking"] else "0",
        }