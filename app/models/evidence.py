"""证据域：证据记录与结论证据关联（技术架构文档 9.2）。

证据的引用原文与块记录里的原文分开存：前者是结论生成时实际看到的那段文字，
后者是解析结果。两者不一致即说明引用被篡改或解析器新旧版本有差异，
人工复核阶段正是靠这个比对来发现问题。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 关联类型：同一份证据在支撑不同结论时，角色可以不同
RELATION_DIRECT = "direct"
RELATION_INDIRECT = "indirect"
RELATION_COUNTER = "counter"

# 结论类型，对应产出结论的智能体
CONCLUSION_FIN_INDICATOR = "fin_indicator"
CONCLUSION_RISK_THEME = "risk_theme"
CONCLUSION_ESG_DIMENSION = "esg_dimension"
CONCLUSION_MAPPING = "mapping"


class Evidence(Base):
    """证据记录。

    block_id 存块标识原文（“文档标识:页号:块序号”），不是 document_block 的代理主键——
    证据链要能在脱离数据库的情况下被读懂和核对。表格类证据额外带单元格引用。
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_block", "block_id"),
        Index("ix_evidence_doc_page", "document_id", "page_no"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evidence_id: Mapped[str] = mapped_column(String(128), unique=True)
    document_id: Mapped[int] = mapped_column(BigInteger)
    block_id: Mapped[str] = mapped_column(String(255))
    # 形如“表1R3C2”；非表格证据为空
    cell_ref: Mapped[str | None] = mapped_column(String(64))
    quoted_text: Mapped[str | None] = mapped_column(LONGTEXT)
    page_no: Mapped[int | None] = mapped_column(Integer)
    # 产生该证据的任务标识。任务域尚未建表，按 9.1 不跨域做物理外键，故此处只存标识。
    task_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ConclusionEvidence(Base):
    """结论与证据的多对多关联。

    同一证据可以同时支撑多个结论；relation_type 让它在每个结论里的角色显式化，
    跨模块结论冲突（同一证据一边直接支撑、一边是反证）因此可被识别。
    """

    __tablename__ = "conclusion_evidence"
    __table_args__ = (
        Index("ix_conclusion_lookup", "conclusion_type", "conclusion_code"),
        Index("ix_conclusion_evidence_ev", "evidence_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    conclusion_type: Mapped[str] = mapped_column(String(32))
    conclusion_code: Mapped[str | None] = mapped_column(String(64))
    conclusion_text: Mapped[str | None] = mapped_column(LONGTEXT)
    evidence_id: Mapped[str] = mapped_column(String(128))
    relation_type: Mapped[str] = mapped_column(String(16), default=RELATION_DIRECT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
