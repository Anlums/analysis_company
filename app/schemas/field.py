"""字段注册表与字段值出入参。

抽取结果按 (公司, 报告期, 字段编码) upsert 落库，所以入参叫 Upsert 而非 Create——
重复抽取是常态，用 Create 的语义会让调用方以为重跑会产生新行。
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.field import SCOPE_ALL, FieldRegistry
from app.schemas.common import FIELD_CODE_RE


class FieldRegistryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_code: str
    name: str
    unit: str | None = None
    category: str
    source_location: str | None = None
    downstream_usage: str | None = None
    is_qualitative: bool
    industry_scope: str
    is_active: bool


class FieldValueUpsert(BaseModel):
    """单个字段的抽取结果。

    定量条目填 value_num、定性条目填 value_text，由注册表的 is_qualitative 决定，
    两者互斥。未绑定证据锚点的字段不得进入上层结果（8.3），因此 evidence_id 在有值
    时必填，除非显式标记 need_review 交由人工复核。
    """

    company_id: int
    fiscal_year: int = Field(ge=1990, le=2100)
    period: str = Field(max_length=16)
    field_code: str = Field(max_length=64)
    value_num: Decimal | None = None
    value_text: str | None = None
    evidence_id: str | None = Field(default=None, max_length=128)
    task_id: int | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    need_review: bool = False

    @model_validator(mode="after")
    def _check_value_and_evidence(self) -> "FieldValueUpsert":
        if self.value_num is None and self.value_text is None:
            raise ValueError("value_num 与 value_text 至少填一个；字段缺失应直接不落行")
        if self.value_num is not None and self.value_text is not None:
            raise ValueError("定量与定性值只能取其一")
        if self.evidence_id is None and not self.need_review:
            raise ValueError(
                "无证据锚点的字段须标记 need_review，不得作为可信结果进入上层（8.3）"
            )
        return self


class FieldValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    fiscal_year: int
    period: str
    field_code: str
    value_num: Decimal | None = None
    value_text: str | None = None
    evidence_id: str | None = None
    task_id: int | None = None
    confidence: Decimal | None = None
    need_review: bool
    created_at: datetime
    updated_at: datetime


class FieldValueWithMeta(FieldValueRead):
    """带字段元数据的读模型，供跨企业对比与展示使用。

    单位取自注册表而非值行：注册表规定落库与输出均为标准单位，值行不重复存单位。
    """

    field_name: str | None = None
    unit: str | None = None
    is_qualitative: bool | None = None


class FieldDefinitionIn(BaseModel):
    """新增字段登记入参（注册表规定：新增字段须先登记，再由调度随任务下发）。"""

    field_code: str = Field(max_length=64)
    name: str = Field(max_length=128)
    unit: str | None = Field(default=None, max_length=32)
    category: str = Field(max_length=8)
    source_location: str | None = Field(default=None, max_length=255)
    downstream_usage: str | None = Field(default=None, max_length=512)
    is_qualitative: bool = False
    industry_scope: str = SCOPE_ALL

    @field_validator("field_code")
    @classmethod
    def _check_code(cls, v: str) -> str:
        # 用显式 ASCII 模式而非 str.isalnum()：isalnum() 接受所有 Unicode 字母，
        # "收入"、"ВS_АР"（西里尔大写）都能通过，而这些编码下游根本按不上
        if not FIELD_CODE_RE.fullmatch(v):
            raise ValueError(
                "编码须为「类别前缀_指标缩写」形式：ASCII 大写字母开头，"
                "下划线分隔，如 BS_AR / ENV_GHG_S1"
            )
        return v

    @model_validator(mode="after")
    def _check_unit(self) -> "FieldDefinitionIn":
        # 用 model_validator：unit 声明在 is_qualitative 之前，field_validator 的
        # info.data 取不到 is_qualitative，这条校验会静默失效
        if self.is_qualitative and self.unit is not None:
            raise ValueError("定性条目的单位应为空，定性由 is_qualitative 表达")
        return self


def to_field_value_with_meta(
    value_row, registry: FieldRegistry
) -> FieldValueWithMeta:
    """把值行与注册表元数据合成读模型。"""
    return FieldValueWithMeta(
        **FieldValueRead.model_validate(value_row).model_dump(),
        field_name=registry.name,
        unit=registry.unit,
        is_qualitative=registry.is_qualitative,
    )
