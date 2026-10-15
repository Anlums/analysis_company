"""准则映射域：准则对照规则、映射明细与差异说明、双语事实对齐标注库（技术架构文档 9.1 表 18、9.2、10.4）。

映射结果进入下游分析时附带来源提示——该报表为准则映射转换所得而非企业原生报表，
准则固有差异会影响指标解读。因此映射记录必须带上口径差异说明与匹配置信度，
不能只留一个结果值。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 准则框架。10.4 本期只实现两条单向映射路径。
FRAMEWORK_IFRS = "IFRS"
FRAMEWORK_CAS = "CAS"
FRAMEWORK_CASS_ESG_6 = "CASS_ESG_6"
FRAMEWORK_ISSB = "ISSB"
FRAMEWORK_GRI = "GRI"

# 映射方向：财务维度 IFRS→CAS；ESG 维度 CASS-ESG 6.0→ISSB+GRI 双框架交叉
MAPPING_PATH_FINANCE = "IFRS_TO_CAS"
MAPPING_PATH_ESG = "CASS_ESG_TO_ISSB_GRI"

# 无直接对应项单独记录并注明原因，禁止强行匹配（10.4）
NO_DIRECT_MATCH = "no_direct_match"


class StandardMapping(Base):
    """准则对照表：两个框架之间的术语对应、核算边界与口径差异规则（9.2）。

    规则以数据形式注入，新增准则框架不需要改代码（10.4）。
    """

    __tablename__ = "standard_mapping"
    __table_args__ = (
        UniqueConstraint(
            "source_framework", "target_framework", "source_item",
            name="uq_standard_mapping_item",
        ),
        Index("ix_standard_mapping_path", "mapping_path"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mapping_path: Mapped[str] = mapped_column(String(32))
    source_framework: Mapped[str] = mapped_column(String(16))
    target_framework: Mapped[str] = mapped_column(String(16))
    source_item: Mapped[str] = mapped_column(String(255))
    # 无直接对应项时留空，原因记在 no_match_reason
    target_item: Mapped[str | None] = mapped_column(String(255))
    no_match_reason: Mapped[str | None] = mapped_column(String(512))
    # 核算边界与口径差异：CAS 资产组 vs IFRS CGU 这类差异写在这里
    boundary_note: Mapped[str | None] = mapped_column(LONGTEXT)
    requires_split: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(32), default="v0.1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MappingRecord(Base):
    """映射记录表：双语对齐智能体每次准则映射的明细（9.2）。

    无直接对应项单独记录并注明原因，不写入目标条目字段——这条是为可追溯性设的：
    下游看到 target_item 为空即知是准则本身没有对应，而不是抽取漏了。
    """

    __tablename__ = "mapping_record"
    __table_args__ = (
        Index("ix_mapping_record_path", "mapping_path"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_code: Mapped[str] = mapped_column(String(64), unique=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    mapping_path: Mapped[str] = mapped_column(String(32))
    source_framework: Mapped[str] = mapped_column(String(16))
    target_framework: Mapped[str] = mapped_column(String(16))
    # 来源报表科目或披露条目
    source_item: Mapped[str] = mapped_column(String(255))
    target_item: Mapped[str | None] = mapped_column(String(255))
    no_match_reason: Mapped[str | None] = mapped_column(String(512))
    caliber_difference: Mapped[str | None] = mapped_column(LONGTEXT)
    # 校正后金额：存在可匹配 CAS 科目的，提取校正后金额并标注口径边界（10.4）
    adjusted_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    evidence_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnnotationLibrary(Base):
    """标注库表：自建的双语事实对齐标注案例（9.2）。

    既是提示词案例层的素材来源，也是回归测试的基准样本。
    """

    __tablename__ = "annotation_library"
    __table_args__ = (
        Index("ix_annotation_library_path", "mapping_path"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mapping_path: Mapped[str] = mapped_column(String(32))
    source_lang: Mapped[str] = mapped_column(String(8))
    target_lang: Mapped[str] = mapped_column(String(8))
    source_text: Mapped[str] = mapped_column(LONGTEXT)
    standard_term: Mapped[str] = mapped_column(String(255))
    standard_difference: Mapped[str | None] = mapped_column(LONGTEXT)
    alignment_approach: Mapped[str | None] = mapped_column(LONGTEXT)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
