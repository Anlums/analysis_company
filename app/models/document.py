"""文档域：文档主数据、块级解析结果、检索分块及其映射（技术架构文档 9.1 表 18）。

块是证据锚点的挂载层，分块是检索层。两者刻意分开：块边界由版面确定性导出，
不随分块参数变化，因此解析器升级或分块策略调整都不会让历史结论的证据链失效。

外键策略遵从技术架构文档 9.1“不跨域做物理外键约束”：域内父子关系建物理外键
（document→document_block/chunk、chunk/document_block→chunk_block），
跨域引用（company_id）只存标识不建约束，便于各域独立演进与归档。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 块类型（文档解析流水线：正文、标题、表格、图表）
BLOCK_TEXT = "text"
BLOCK_TITLE = "title"
BLOCK_TABLE = "table"
BLOCK_FIGURE = "figure"

# 文档类型
DOC_ANNUAL_REPORT = "annual_report"
DOC_INTERIM_REPORT = "interim_report"
DOC_ESG_REPORT = "esg_report"
DOC_AUDIT_REPORT = "audit_report"

# 报告期类型
PERIOD_FY = "FY"
PERIOD_H1 = "H1"

# 解析状态
PARSE_PENDING = "pending"
PARSE_RUNNING = "running"
PARSE_SUCCEEDED = "succeeded"
PARSE_FAILED = "failed"

# 分块类型（技术架构文档 8.2 差异化分块规则）
CHUNK_FIN_STATEMENT = "fin_statement"
CHUNK_ACCOUNTING_POLICY = "accounting_policy"
CHUNK_ESG_NARRATIVE = "esg_narrative"
CHUNK_MDA = "mda"
CHUNK_AUDIT_OPINION = "audit_opinion"


class Document(Base):
    """文档主数据。

    doc_code 是证据锚点的第一段（“文档标识:页号:块序号”），必须稳定且可人工阅读，
    否则证据链无法排查。同一份文件重复上传应得到同一个 doc_code。
    """

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_code: Mapped[str] = mapped_column(String(128), unique=True)
    # 跨域引用（公司域），按技术架构文档 9.1 不做物理外键
    company_id: Mapped[int] = mapped_column(BigInteger, index=True)
    doc_type: Mapped[str] = mapped_column(String(32), index=True)
    fiscal_year: Mapped[int | None] = mapped_column(SmallInteger)
    period: Mapped[str | None] = mapped_column(String(16))
    lang: Mapped[str | None] = mapped_column(String(8))
    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    page_count: Mapped[int | None] = mapped_column(Integer)
    parse_status: Mapped[str] = mapped_column(String(16), default=PARSE_PENDING)
    parse_version: Mapped[str | None] = mapped_column(String(32))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentBlock(Base):
    """块级解析结果，证据锚点的实际载体（技术架构文档 9.2）。

    block_id 由文档标识、页码与页内序号确定性生成，不含随机量与时间戳，
    保证同一文档重复解析得到相同标识。原文与归一化文本分列存储：
    前者用于证据比对与前端展示，后者用于检索与匹配。
    """

    __tablename__ = "document_block"
    __table_args__ = (
        UniqueConstraint("document_id", "page_no", "block_index", name="uq_block_position"),
        Index("ix_block_doc_type", "document_id", "block_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    block_id: Mapped[str] = mapped_column(String(255), unique=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column(Integer)
    block_index: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(16))
    raw_text: Mapped[str | None] = mapped_column(LONGTEXT)
    normalized_text: Mapped[str | None] = mapped_column(LONGTEXT)
    # 归一化坐标框 {x0,y0,x1,y1}，相对页面宽高的 0–1 比例值，前端据此在任意缩放下高亮
    bbox: Mapped[dict | None] = mapped_column(JSON)
    # 表格块的行列结构；锚点可借单元格引用精确定位到格
    table_data: Mapped[dict | None] = mapped_column(JSON)
    is_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Chunk(Base):
    """检索分块。按内容类型差异化切分，不是固定长度切分。"""

    __tablename__ = "chunk"
    __table_args__ = (
        Index("ix_chunk_doc_type", "document_id", "chunk_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chunk_id: Mapped[str] = mapped_column(String(128), unique=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    # 跨域引用（公司域），按技术架构文档 9.1 不做物理外键
    company_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chunk_type: Mapped[str] = mapped_column(String(32))
    # ESG 叙述类分块的层级路径，如“环境绩效 > 排放管理 > 应对气候变化”，支持按章节过滤检索
    section_path: Mapped[str | None] = mapped_column(String(512))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(LONGTEXT)
    token_count: Mapped[int | None] = mapped_column(Integer)
    lang: Mapped[str | None] = mapped_column(String(8))
    fiscal_year: Mapped[int | None] = mapped_column(SmallInteger)
    period: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChunkBlock(Base):
    """分块与块的映射。

    用于从检索命中分块回跳到块级锚点——展示与溯源一律走块，不走分块。
    """

    __tablename__ = "chunk_block"
    __table_args__ = (
        UniqueConstraint("chunk_pk", "block_pk", name="uq_chunk_block"),
        Index("ix_chunk_block_order", "chunk_pk", "ordinal"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chunk_pk: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chunk.id", ondelete="CASCADE")
    )
    block_pk: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("document_block.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
