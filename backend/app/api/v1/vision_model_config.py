"""Vision model configuration API (script-side screenshot recognition)."""

from typing import Optional

from fastapi import APIRouter

from app.schemas.model_config import ModelConfigTestResponse
from app.schemas.vision_model_config import VisionModelConfigResponse, VisionModelConfigUpdate
from app.services.vision_model_config_service import VisionModelConfigService

router = APIRouter()
vision_model_config_service = VisionModelConfigService()


@router.get("/", response_model=VisionModelConfigResponse)
async def get_vision_config():
    return await vision_model_config_service.get_config()


@router.put("/", response_model=VisionModelConfigResponse)
async def update_vision_config(update: VisionModelConfigUpdate):
    return await vision_model_config_service.save(update)


@router.post("/test", response_model=ModelConfigTestResponse)
async def test_vision_config(update: Optional[VisionModelConfigUpdate] = None):
    """测试视觉模型；请求体可省略（用已保存的配置），也可带上未保存的临时值。"""
    return await vision_model_config_service.test(update)