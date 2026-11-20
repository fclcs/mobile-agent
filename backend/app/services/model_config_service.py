"""Model configuration service for managing different LLM providers."""

import time
import json
from typing import List, Optional
from app.db import db
from app.schemas.model_config import ModelConfigCreate, ModelConfigUpdate, ModelConfigResponse, ModelConfigTestResponse

has_openai = True  # uses httpx, no SDK required

try:
    import anthropic
    has_anthropic = True
except ImportError:
    has_anthropic = False

def _normalize_base_url(base_url: str) -> str:
    """Base URL 只保留到 /v1 这类根路径；用户误填完整端点时去掉 /chat/completions。

    后端测试连接、OpenAI SDK、vision_ads 都会自己拼 /chat/completions，
    保留完整端点会导致 .../chat/completions/chat/completions 的 404。
    """
    value = (base_url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix) ].rstrip("/")
    return value


def _http_error_message(status: int, text: str, base_url: str) -> str:
    """把上游的错误码和原文带回前端。

    以前 404 一律显示「模型名称不存在」，火山方舟的 404 UnsupportedModel
    （"does not support the agent plan feature"）被吞掉，看起来像模型名抄错了。
    """
    code = message = ""
    try:
        err = (json.loads(text) or {}).get("error") or {}
        code = str(err.get("code") or "")
        message = str(err.get("message") or "")
    except (ValueError, TypeError, AttributeError):
        pass
    detail = " ".join(x for x in (code, message) if x)[:160]

    if status == 401 or code in ("AuthenticationError", "Unauthorized"):
        return f"API Key 无效或权限不足（HTTP {status}{' ' + code if code else ''}）"
    if status == 404 or code in ("UnsupportedModel", "InvalidEndpointOrModel.NotFound"):
        if code == "UnsupportedModel":
            label = "该模型不在当前套餐（如 Agent Plan）支持的模型清单里"
        else:
            label = "模型名称或接入点不存在"
        hint = ""
        if "volces.com" in (base_url or ""):
            hint = "；方舟 Agent Plan 支持 deepseek-v4.1-flash、glm-5.3-flash、doubao-seed-2.1-pro 等，请按套餐清单选模型名"
        tail = f"。上游原文：{detail}" if message else ""
        return f"{label}（HTTP {status}{' ' + code if code else ''}）{hint}{tail}"
    return f"HTTP {status}{' ' + code if code else ''}：{(message or text)[:160]}"


class ModelConfigService:
    async def create_config(self, config: ModelConfigCreate) -> str:
        config.base_url = _normalize_base_url(config.base_url)
        config_id = f"mcfg_{int(time.time_ns())}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        conn = await db.get_connection()
        
        # If this is set as default, unset others
        if config.is_default:
            await conn.execute("UPDATE model_configs SET is_default = 0")
            
        await conn.execute(
            """INSERT INTO model_configs (config_id, name, provider, base_url, api_key, model_name, vision_model, disable_thinking, is_default, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (config_id, config.name, config.provider.value, config.base_url, config.api_key,
             config.model_name, config.vision_model, 1 if config.disable_thinking else 0,
             1 if config.is_default else 0, now, now)
        )
        await conn.commit()
        return config_id

    async def get_config(self, config_id: str) -> Optional[ModelConfigResponse]:
        conn = await db.get_connection()
        cursor = await conn.execute("SELECT * FROM model_configs WHERE config_id = ?", (config_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        return ModelConfigResponse(**dict(row))

    async def list_configs(self) -> List[ModelConfigResponse]:
        conn = await db.get_connection()
        cursor = await conn.execute("SELECT * FROM model_configs ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [ModelConfigResponse(**dict(row)) for row in rows]

    async def update_config(self, config_id: str, update: ModelConfigUpdate) -> Optional[ModelConfigResponse]:
        conn = await db.get_connection()
        
        # Check if exists
        existing = await self.get_config(config_id)
        if not existing:
            return None
            
        fields = []
        values = []
        update_data = update.model_dump(exclude_unset=True)
        if update_data.get("base_url"):
            update_data["base_url"] = _normalize_base_url(update_data["base_url"])

        # The API returns a masked placeholder; never write it back over the real key.
        if update_data.get("api_key") in ("******", ""):
            update_data.pop("api_key", None)

        if 'is_default' in update_data and update_data['is_default']:
            await conn.execute("UPDATE model_configs SET is_default = 0")
            
        for k, v in update_data.items():
            fields.append(f"{k} = ?")
            values.append(v)
            
        if fields:
            fields.append("updated_at = ?")
            values.append(time.strftime("%Y-%m-%dT%H:%M:%S"))
            values.append(config_id)
            await conn.execute(f"UPDATE model_configs SET {', '.join(fields)} WHERE config_id = ?", values)
            await conn.commit()
            
        return await self.get_config(config_id)

    async def delete_config(self, config_id: str):
        conn = await db.get_connection()
        await conn.execute("DELETE FROM model_configs WHERE config_id = ?", (config_id,))
        await conn.commit()

    async def get_default_config(self) -> Optional[ModelConfigResponse]:
        conn = await db.get_connection()
        cursor = await conn.execute("SELECT * FROM model_configs WHERE is_default = 1")
        row = await cursor.fetchone()
        if not row:
            # Fallback to the latest created if no default is set
            cursor = await conn.execute("SELECT * FROM model_configs ORDER BY created_at DESC LIMIT 1")
            row = await cursor.fetchone()
            
        if not row:
            return None
        return ModelConfigResponse(**dict(row))

    async def test_config(self, config: ModelConfigCreate) -> ModelConfigTestResponse:
        provider = config.provider
        if provider.value == "openai":
            if not has_openai:
                return ModelConfigTestResponse(
                    success=False,
                    message="OpenAI SDK 未安装，请执行 pip install openai"
                )
            return await self._test_openai(config)
        elif provider.value == "anthropic":
            if not has_anthropic:
                return ModelConfigTestResponse(
                    success=False,
                    message="Anthropic SDK 未安装，请执行 pip install anthropic"
                )
            return await self._test_anthropic(config)
        else:
            return ModelConfigTestResponse(
                success=False,
                message=f"不支持的 provider: {provider.value}"
            )

    async def test_saved_config(self, config_id: str) -> ModelConfigTestResponse:
        """测试已保存的配置；从数据库读取真实密钥，避免浏览器拿到掩码后测试必失败。"""
        existing = await self.get_config(config_id)
        if not existing:
            return ModelConfigTestResponse(success=False, message="模型配置不存在")
        config = ModelConfigCreate(
            name=existing.name,
            provider=existing.provider,
            base_url=existing.base_url,
            api_key=existing.api_key,
            model_name=existing.model_name,
            disable_thinking=existing.disable_thinking,
            is_default=existing.is_default,
        )
        return await self.test_config(config)

    async def _test_openai(self, config: ModelConfigCreate) -> ModelConfigTestResponse:
        import httpx
        start = time.time()
        url = _normalize_base_url(config.base_url) + "/chat/completions"
        body = {
            "model": config.model_name,
            "messages": [{"role": "user", "content": "Respond with exactly: OK"}],
            # 512 而非 10：推理模型（如方舟 glm-5.3-flash 无法关闭思考）会先花
            # 几十到几百 token 思考，10 会被截断成空正文，误报“连接失败”。
            "max_tokens": 512,
        }
        if config.disable_thinking:
            body["enable_thinking"] = False
        print(f"\n[LLM TEST] URL={url}, Model={config.model_name}, Key=<redacted>")
        print(f"[LLM TEST] Request: {json.dumps(body, ensure_ascii=False)}")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
                resp = await client.post(url, json=body, headers=headers)
                # 部分模型不接受 enable_thinking 参数，报 400 时去掉它再试一次
                if resp.status_code == 400 and "enable_thinking" in resp.text and "enable_thinking" in body:
                    print("[LLM TEST] 400 且提到 enable_thinking，去掉该参数重试")
                    body.pop("enable_thinking", None)
                    resp = await client.post(url, json=body, headers=headers)
                elapsed = round((time.time() - start) * 1000)
                ct = resp.headers.get("content-type", "N/A")
                print(f"[LLM TEST] 状态码: {resp.status_code}, Content-Type: {ct}")
                print(f"[LLM TEST] 响应体前300字: {resp.text[:300]}")

                if resp.status_code != 200:
                    return ModelConfigTestResponse(
                        success=False,
                        message=_http_error_message(resp.status_code, resp.text, config.base_url),
                        response_time_ms=elapsed,
                    )

                # 尝试解析 SSE 流式响应
                if "text/event-stream" in ct or resp.text.startswith("data:"):
                    content = ""
                    for line in resp.text.splitlines():
                        line = line.strip()
                        if line.startswith("data:") and "[DONE]" not in line:
                            try:
                                chunk = json.loads(line[5:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                if delta.get("content"):
                                    content += delta["content"]
                            except (json.JSONDecodeError, IndexError, KeyError):
                                pass
                    if content.strip():
                        print(f"[LLM TEST] SSE 解析成功, content={content}")
                        return ModelConfigTestResponse(success=True, message="连接成功", response_time_ms=elapsed)
                    print(f"[LLM TEST] SSE 解析得到空内容，完整响应: {resp.text[:500]}")
                    return ModelConfigTestResponse(success=False, message=f"SSE 响应为空: {resp.text[:200]}", response_time_ms=elapsed)

                # 尝试解析标准 JSON 响应
                try:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices and choices[0].get("message", {}).get("content"):
                        return ModelConfigTestResponse(success=True, message="连接成功", response_time_ms=elapsed)
                    print(f"[LLM TEST] JSON 无有效 choices: {resp.text[:300]}")
                    return ModelConfigTestResponse(success=False, message=f"JSON 响应无有效内容: {resp.text[:200]}", response_time_ms=elapsed)
                except json.JSONDecodeError:
                    print(f"[LLM TEST] 无法解析响应: {resp.text[:300]}")
                    return ModelConfigTestResponse(success=False, message=f"无法解析响应: {resp.text[:200]}", response_time_ms=elapsed)

        except httpx.ConnectError:
            elapsed = round((time.time() - start) * 1000)
            return ModelConfigTestResponse(success=False, message="无法连接到服务器，请检查 API Base URL", response_time_ms=elapsed)
        except httpx.TimeoutException:
            elapsed = round((time.time() - start) * 1000)
            return ModelConfigTestResponse(success=False, message="连接超时，请检查网络", response_time_ms=elapsed)
        except Exception as e:
            elapsed = round((time.time() - start) * 1000)
            print(f"[LLM TEST] 异常: {type(e).__name__}: {e}")
            import traceback
            print(f"[LLM TEST] 堆栈: {''.join(traceback.format_tb(e.__traceback__))}")
            return ModelConfigTestResponse(success=False, message=f"{type(e).__name__}: {e}", response_time_ms=elapsed)

    async def _test_anthropic(self, config: ModelConfigCreate) -> ModelConfigTestResponse:
        start = time.time()
        try:
            client = anthropic.Anthropic(
                base_url=config.base_url,
                api_key=config.api_key,
                timeout=15,
            )
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=config.model_name,
                    max_tokens=512,
                    messages=[{"role": "user", "content": "Respond with exactly: OK"}],
                )
            )
            elapsed = round((time.time() - start) * 1000)
            if response.content and response.content[0].text:
                return ModelConfigTestResponse(
                    success=True,
                    message="连接成功",
                    response_time_ms=elapsed,
                )
            else:
                return ModelConfigTestResponse(
                    success=False,
                    message="响应格式异常",
                    response_time_ms=elapsed,
                )
        except Exception as e:
            elapsed = round((time.time() - start) * 1000)
            msg = self._classify_error(e, api_key=config.api_key)
            return ModelConfigTestResponse(
                success=False,
                message=msg,
                response_time_ms=elapsed,
            )

    @staticmethod
    def _classify_error(e: Exception, api_key: str = "") -> str:
        msg = str(e).lower()
        if any(x in msg for x in ["connect", "connection refused", "connection error", "name resolution"]):
            return "无法连接到服务器，请检查 API Base URL"
        if any(x in msg for x in ["401", "unauthorized", "403", "forbidden", "invalid api key", "authentication"]):
            return "API Key 无效或权限不足"
        if any(x in msg for x in ["404", "not found", "model_not_found", "model not found"]):
            return "模型名称不存在"
        if any(x in msg for x in ["timeout", "timed out"]):
            return "连接超时，请检查网络"
        safe = str(e)
        if api_key and api_key in safe:
            safe = safe.replace(api_key, "***")
        return f"连接失败: {safe}"
