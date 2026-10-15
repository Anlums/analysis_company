"""配置域（一）：行业注册、指标适用性矩阵、术语词典（技术架构文档 9.1 表 18、9.2、10.2、10.4）。

行业包是本系统跨行业扩展的核心机制（10.2）：导入一个行业包即完成系统对新行业的
支持，全过程不涉及代码变更。一个完整行业包含五项内容，其中三项落在这张表的三个
模型上——适用性矩阵、术语词典，余下两项阈值覆盖与权重方案见 rules.py。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 默认行业包覆盖通用财务与 ESG 指标，适用于全部行业；其余行业在其上叠加（10.2）
DEFAULT_INDUSTRY_CODE = "DEFAULT"
FORESTRY_INDUSTRY_CODE = "FOR"

# 术语词典的领域归属，用于查询扩展时限定范围
TERM_DOMAIN_FINANCE = "finance"
TERM_DOMAIN_ESG = "esg"
TERM_DOMAIN_FORESTRY = "forestry"


class Industry(Base):
    """行业表：行业注册（9.1）。

    默认包 + 行业包叠加的结构（10.2）：任何任务都先套用默认包，再叠加命中行业的包。
    """

    __tablename__ = "industry"

    industry_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IndicatorApplicability(Base):
    """指标适用性矩阵表，主键「指标编码 + 行业编码」（9.2）。

    以存货类指标为例：营收增速与存货增速的背离在制造业是重要风险信号，但金融、
    互联网不存在存货科目，该指标不适用。系统在此标记不适用，由规则引擎在计算前
    直接跳过，既不产生无意义结果，也不因分母缺失而报错（10.1）。

    本表只覆盖财务异常指标与 ESG 维度，不通用于 field_registry 的 53 个字段。
    """

    __tablename__ = "indicator_applicability"
    __table_args__ = (
        Index("ix_applicability_industry", "industry_code"),
    )

    indicator_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    industry_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    is_applicable: Mapped[bool] = mapped_column(Boolean, default=True)
    # 该行业的阈值覆盖值；实际判定区间在 threshold 表，此处为轻量覆盖
    threshold_override: Mapped[dict | None] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TermDictionary(Base):
    """术语词典表（9.2、10.4）。

    承担两件事：检索侧的查询扩展与实体归并。同一家公司在不同来源中可能以中文
    全称、英文全称、简称或曾用名出现，靠这里归并至统一公司标识，避免跨文档分析时
    出现实体割裂。公司别名另有专门的 company_alias 表，本表负责通用术语。
    """

    __tablename__ = "term_dictionary"
    __table_args__ = (
        Index("ix_term_dictionary_zh", "term_zh"),
        Index("ix_term_dictionary_en", "term_en"),
        Index("ix_term_dictionary_domain", "domain", "industry_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    term_zh: Mapped[str] = mapped_column(String(255))
    term_en: Mapped[str | None] = mapped_column(String(255))
    # 同义词、简称、曾用名，供查询扩展一并召回
    synonyms: Mapped[dict | None] = mapped_column(JSON)
    domain: Mapped[str] = mapped_column(String(16))
    # 空表示全行业通用术语；非空表示该行业包专属
    industry_code: Mapped[str | None] = mapped_column(String(32))
    definition: Mapped[str | None] = mapped_column(LONGTEXT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
