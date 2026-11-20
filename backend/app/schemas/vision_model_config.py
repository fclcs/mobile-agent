"""Script-side vision model configuration schemas.

脚本的视觉识别（广告/遮挡判定、控件定位）用独立的一套模型配置，和手机操作模型
（model_configs，PhoneAgent）分开，两者可以接不同的供应商和密钥。
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional

class VisionModelConfigUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    disable_thinking: Optional[bool] = None

class VisionModelConfigResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    provider: str = "openai"
    base_url: str = ""
    # 只返回是否已配置，绝不把密钥回传给浏览器。
    api_key: str = ""
    model_name: str = ""
    disable_thinking: bool = False
    api_key_configured: bool = False
    configured: bool = False
    updated_at: Optional[str] = None