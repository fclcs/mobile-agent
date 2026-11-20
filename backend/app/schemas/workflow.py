"""Request schemas for sequential script workflows."""

from pydantic import BaseModel, Field, field_validator, model_validator


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    script_ids: list[str] = Field(min_length=1)
    continue_on_error: bool = False
    step_timeout: int = Field(default=0, ge=0, le=86400)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("流程名称不能为空")
        return value

    @field_validator("script_ids")
    @classmethod
    def scripts_must_not_be_blank(cls, value: list[str]) -> list[str]:
        if any(not script_id.strip() for script_id in value):
            raise ValueError("脚本 ID 不能为空")
        return value


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    script_ids: list[str] | None = Field(default=None, min_length=1)
    continue_on_error: bool | None = None
    step_timeout: int | None = Field(default=None, ge=0, le=86400)


class WorkflowRunBatchDelete(BaseModel):
    """批量删除执行历史：一次最多 200 条，重复 ID 自动去重。"""
    run_ids: list[str] = Field(min_length=1, max_length=200)

    @field_validator("run_ids")
    @classmethod
    def run_ids_must_not_be_blank(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for run_id in value:
            run_id = run_id.strip()
            if run_id and run_id not in unique:
                unique.append(run_id)
        if not unique:
            raise ValueError("请至少选择一条执行记录")
        return unique


class WorkflowExecute(BaseModel):
    """多机执行：每台手机独立跑完整脚本序列。

    device_id 为旧版单机接口保留；device_ids 为新版多选接口。
    """
    device_id: str | None = Field(default=None, min_length=1)
    device_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_devices(self):
        if not self.device_ids and self.device_id:
            self.device_ids = [self.device_id]
        seen = set()
        normalized = []
        for device_id in self.device_ids:
            device_id = device_id.strip()
            if device_id and device_id not in seen:
                seen.add(device_id)
                normalized.append(device_id)
        if not normalized:
            raise ValueError("请至少选择一台手机")
        self.device_ids = normalized
        return self
