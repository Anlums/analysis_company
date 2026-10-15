"""证据域出入参。

技术架构文档 8.3 规定锚点格式为「文档标识:页号:块序号」，表格类证据额外附加
单元格引用，形如「文档标识:页号:块序号#表序R行C列」。这里把这个格式做成可解析、
可校验、可回渲染的类型，而不是在三处各写一遍字符串拼接——锚点是「结论可回指原文」
的唯一凭据，格式一旦写错，前端高亮和人工复核都会静默失效。
"""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.evidence import (
    CONCLUSION_ESG_DIMENSION,
    CONCLUSION_FIN_INDICATOR,
    CONCLUSION_MAPPING,
    CONCLUSION_RISK_THEME,
    RELATION_COUNTER,
    RELATION_DIRECT,
    RELATION_INDIRECT,
)
from app.schemas.common import check_doc_code

# 页号与块序号不接受前导零：块标识是由文档标识、页码与页内序号确定性生成的字符串，
# 若解析时把 "007" 归一化成 "7"，与库里存的 "007" 就不再相等，而且不报错——
# 表现为锚点查不到块。宁可拒绝也不静默改写。
_ANCHOR_RE = re.compile(
    r"(?P<doc_code>[A-Za-z0-9_\-]+)"
    r":(?P<page_no>[1-9]\d{0,3})"
    r":(?P<block_index>\d{1,4})"
    r"(?:#(?P<cell_ref>[^#\s]+))?"
)

# 单元格引用形如「表1R3C2」
_CELL_RE = re.compile(r"^表\d+R[1-9]\d*C[1-9]\d*$")

RELATION_TYPES = (RELATION_DIRECT, RELATION_INDIRECT, RELATION_COUNTER)
CONCLUSION_TYPES = (
    CONCLUSION_FIN_INDICATOR,
    CONCLUSION_RISK_THEME,
    CONCLUSION_ESG_DIMENSION,
    CONCLUSION_MAPPING,
)


class EvidenceAnchor(BaseModel):
    """块级证据锚点。锚定在块级而非分块级，块边界与分块参数无关（8.3）。"""

    model_config = ConfigDict(frozen=True)

    doc_code: str
    page_no: int = Field(ge=1, le=9999)
    block_index: int = Field(ge=0, le=9999)
    cell_ref: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "EvidenceAnchor":
        check_doc_code(self.doc_code)
        if self.cell_ref is not None and not _CELL_RE.fullmatch(self.cell_ref):
            raise ValueError(f"单元格引用 {self.cell_ref!r} 格式应为「表1R3C2」")
        return self

    @classmethod
    def parse(cls, anchor: str) -> "EvidenceAnchor":
        # 用 fullmatch 而非 match+$：Python 的 $ 允许串尾一个换行，模型输出带 \n 时
        # 会被静默接受，破坏「可回渲染」契约（str(parse(s)) != s）
        m = _ANCHOR_RE.fullmatch(anchor)
        if not m:
            raise ValueError(
                f"锚点 {anchor!r} 不符合「文档标识:页号:块序号[#表序R行C列]」格式"
            )
        return cls(
            doc_code=m.group("doc_code"),
            page_no=int(m.group("page_no")),
            block_index=int(m.group("block_index")),
            cell_ref=m.group("cell_ref"),
        )

    def __str__(self) -> str:
        base = f"{self.doc_code}:{self.page_no}:{self.block_index}"
        return f"{base}#{self.cell_ref}" if self.cell_ref else base

    @property
    def block_anchor(self) -> str:
        """去掉单元格引用的块级锚点，对应 document_block.block_id。"""
        return f"{self.doc_code}:{self.page_no}:{self.block_index}"


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_id: str
    document_id: int
    block_id: str
    cell_ref: str | None = None
    quoted_text: str | None = None
    page_no: int | None = None
    task_id: int | None = None
    created_at: datetime


class EvidenceWithAnchor(EvidenceRead):
    """带上解析后的锚点，供前端定位高亮使用（8.3 展示阶段按页号与坐标框定位）。

    anchor 必须由 block_id 派生，不能让调用方传：ORM 行上没有 anchor 属性，
    from_attributes 会把缺属性直接落成默认值 None，于是这个字段存在的唯一意义
    静默消失且不报错。
    """

    # 声明为可空是为了让 from_attributes 能从没有 anchor 属性的 ORM 行构造成功，
    # 校验器随后必填上；校验通过后它一定非空，block_id 畸形则直接抛错而非留空。
    anchor: EvidenceAnchor | None = None

    @model_validator(mode="after")
    def _derive_anchor(self) -> "EvidenceWithAnchor":
        if self.anchor is None:
            parsed = EvidenceAnchor.parse(self.block_id)
            if self.cell_ref:
                # 单元格引用以 evidence 列为准：block_id 只到块级
                parsed = parsed.model_copy(update={"cell_ref": self.cell_ref})
            self.anchor = parsed
        return self


class ConclusionEvidenceCreate(BaseModel):
    task_id: int | None = None
    conclusion_type: str
    conclusion_code: str | None = None
    conclusion_text: str | None = None
    evidence_id: str
    relation_type: str = RELATION_DIRECT

    @field_validator("conclusion_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in CONCLUSION_TYPES:
            raise ValueError(f"结论类型须为 {CONCLUSION_TYPES} 之一")
        return v

    @field_validator("relation_type")
    @classmethod
    def _check_relation(cls, v: str) -> str:
        if v not in RELATION_TYPES:
            raise ValueError(f"关联类型须为 {RELATION_TYPES} 之一")
        return v


class ConclusionEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None = None
    conclusion_type: str
    conclusion_code: str | None = None
    conclusion_text: str | None = None
    evidence_id: str
    relation_type: str
    created_at: datetime
