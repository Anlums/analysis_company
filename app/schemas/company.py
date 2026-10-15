"""公司域出入参。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import check_doc_code


class CompanyAliasCreate(BaseModel):
    alias: str = Field(max_length=255)
    lang: str | None = Field(default=None, max_length=8)


class CompanyAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    alias: str
    lang: str | None = None


class CompanyCreate(BaseModel):
    company_code: str = Field(max_length=64, description="业务标识，用于拼装 doc_code")
    name_cn: str | None = Field(default=None, max_length=255)
    name_en: str | None = Field(default=None, max_length=255)
    stock_code: str | None = Field(default=None, max_length=32)
    market: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=16)
    industry_code: str | None = Field(default=None, max_length=16)

    @field_validator("company_code")
    @classmethod
    def _check_company_code(cls, v: str) -> str:
        # company_code 会被拼进 doc_code，字符集必须与锚点解析规则一致
        return check_doc_code(v)


class CompanyUpdate(BaseModel):
    name_cn: str | None = Field(default=None, max_length=255)
    name_en: str | None = Field(default=None, max_length=255)
    stock_code: str | None = Field(default=None, max_length=32)
    market: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=16)
    industry_code: str | None = Field(default=None, max_length=16)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_code: str
    name_cn: str | None = None
    name_en: str | None = None
    stock_code: str | None = None
    market: str | None = None
    country: str | None = None
    industry_code: str | None = None
    created_at: datetime


class CompanyWithAliases(CompanyRead):
    aliases: list[CompanyAliasRead] = []
