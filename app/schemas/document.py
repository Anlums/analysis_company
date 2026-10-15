"""文档域出入参。

块与分块分开建模的原因见 models/document.py：块是证据锚点的挂载层，分块是检索层，
两者生命周期不同，出入参也不该混用。
"""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.models.document import (
    BLOCK_FIGURE,
    BLOCK_TABLE,
    BLOCK_TEXT,
    BLOCK_TITLE,
    DOC_ANNUAL_REPORT,
    DOC_AUDIT_REPORT,
    DOC_ESG_REPORT,
    DOC_INTERIM_REPORT,
    PARSE_FAILED,
    PARSE_PENDING,
    PARSE_RUNNING,
    PARSE_SUCCEEDED,
    PERIOD_FY,
    PERIOD_H1,
)
from app.schemas.common import check_doc_code, make_block_id

BLOCK_TYPES = (BLOCK_TEXT, BLOCK_TITLE, BLOCK_TABLE, BLOCK_FIGURE)
DOC_TYPES = (DOC_ANNUAL_REPORT, DOC_INTERIM_REPORT, DOC_ESG_REPORT, DOC_AUDIT_REPORT)
PERIODS = (PERIOD_FY, PERIOD_H1, "Q1", "Q2", "Q3", "Q4")
PARSE_STATUSES = (PARSE_PENDING, PARSE_RUNNING, PARSE_SUCCEEDED, PARSE_FAILED)


class BBox(BaseModel):
    """归一化坐标框，相对页面宽高的 0–1 比例值。

    用比例而非绝对像素，是为了让前端在任意缩放比例下都能正确绘制高亮（8.3）。
    """

    model_config = ConfigDict(frozen=True)

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_order(self) -> "BBox":
        # 用 model_validator 而非 field_validator：field_validator 的 info.data 只含
        # 声明顺序在前的字段，跨字段比较会因字段顺序不同而静默失效
        if self.x1 < self.x0:
            raise ValueError("x1 不得小于 x0")
        if self.y1 < self.y0:
            raise ValueError("y1 不得小于 y0")
        return self


class DocumentCreate(BaseModel):
    doc_code: str = Field(max_length=128, description="锚点第一段，须稳定且可人工阅读")
    company_id: int
    doc_type: str
    fiscal_year: int | None = Field(default=None, ge=1990, le=2100)
    period: str | None = None
    lang: str | None = Field(default=None, max_length=8)
    file_name: str = Field(max_length=512)
    file_path: str = Field(max_length=512)
    file_hash: str = Field(max_length=64)
    file_size: int | None = None
    page_count: int | None = None

    @field_validator("doc_code")
    @classmethod
    def _check_doc_code(cls, v: str) -> str:
        # 写入侧与锚点解析侧用同一套字符集，否则会出现「文档存得进去、它的锚点解析不出来」
        return check_doc_code(v)

    @field_validator("doc_type")
    @classmethod
    def _check_doc_type(cls, v: str) -> str:
        if v not in DOC_TYPES:
            raise ValueError(f"文档类型须为 {DOC_TYPES} 之一")
        return v

    @field_validator("period")
    @classmethod
    def _check_period(cls, v: str | None) -> str | None:
        if v is not None and v not in PERIODS:
            raise ValueError(f"报告期须为 {PERIODS} 之一")
        return v


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doc_code: str
    company_id: int
    doc_type: str
    fiscal_year: int | None = None
    period: str | None = None
    lang: str | None = None
    file_name: str
    file_path: str
    file_hash: str
    file_size: int | None = None
    page_count: int | None = None
    parse_status: str
    parse_version: str | None = None
    parsed_at: datetime | None = None
    created_at: datetime


class DocumentBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    block_id: str
    document_id: int
    page_no: int
    block_index: int
    block_type: str
    raw_text: str | None = None
    normalized_text: str | None = None
    bbox: BBox | None = None
    table_data: dict | None = None
    is_ocr: bool
    ocr_confidence: float | None = None


class DocumentBlockCreate(BaseModel):
    """解析流水线的落库入参。

    不收 block_id 而是由 doc_code + page_no + block_index 派生：表上的唯一约束是
    (document_id, page_no, block_index)，block_id 列本身完全自由，若允许调用方自填，
    填错不会被任何约束拦下，而由它派生的所有证据锚点此后都查不到块。

    坐标为识别结果时 is_ocr 必须为真且带置信度——8.1 要求扫描页在块上标记来源，
    使其置信度参与下游的证据可靠性评估。
    """

    doc_code: str
    page_no: int = Field(ge=1, le=9999)
    block_index: int = Field(ge=0, le=9999)
    block_type: str
    raw_text: str | None = None
    normalized_text: str | None = None
    bbox: BBox | None = None
    table_data: dict | None = None
    is_ocr: bool = False
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("doc_code")
    @classmethod
    def _check_doc_code(cls, v: str) -> str:
        return check_doc_code(v)

    @field_validator("block_type")
    @classmethod
    def _check_block_type(cls, v: str) -> str:
        if v not in BLOCK_TYPES:
            raise ValueError(f"块类型须为 {BLOCK_TYPES} 之一")
        return v

    @computed_field
    @property
    def block_id(self) -> str:
        return make_block_id(self.doc_code, self.page_no, self.block_index)

    @model_validator(mode="after")
    def _check_ocr_confidence(self) -> "DocumentBlockCreate":
        # 必须用 model_validator：ocr_confidence 走默认值 None 时 field_validator
        # 不会被触发（Pydantic v2 默认不校验默认值），OCR 块会漏掉置信度而无报错
        if self.is_ocr and self.ocr_confidence is None:
            raise ValueError("识别来源的块必须给出识别置信度")
        return self


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_id: str
    document_id: int
    company_id: int
    chunk_type: str
    section_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    text: str
    token_count: int | None = None
    lang: str | None = None
    fiscal_year: int | None = None
    period: str | None = None
