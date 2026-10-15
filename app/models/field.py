"""字段注册表与字段值表。

《数据字段编码注册表》定义 46 个字段的编码、名称、单位与下游用途，是智能体间数据契约。
技术架构文档 9.1 的八个域里没有承载这些字段值的表，本模块补上这一环，设计取舍见下。

采用长表而非宽表：注册表明确“编码一经登记即不复用”“行业扩展字段随行业包导入”，
宽表每接一个行业包都要改表结构做迁移，与 10.2 行业包机制冲突。
长表下新增行业包只是插数据，且定性条目与定量条目能共用一张表。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 类别前缀（注册表编码规则“类别前缀_指标缩写”）
CATEGORY_BS = "BS"
CATEGORY_IS = "IS"
CATEGORY_CF = "CF"
CATEGORY_ENV = "ENV"
CATEGORY_SOC = "SOC"
CATEGORY_GOV = "GOV"
CATEGORY_FOR = "FOR"
# 会计口径识别字段。注册表原编码规则只列了 BS/IS/CF/ENV/SOC/GOV/FOR，
# 会计口径不是报表科目，塞进任何一类都会误导下游，故扩展此前缀。
CATEGORY_META = "META"

# industry_scope 取值：全行业通用字段用 ALL，行业包字段用行业代码
SCOPE_ALL = "ALL"


class FieldRegistry(Base):
    """字段字典。编码即主键——注册表规定编码唯一且不复用，不需要另设代理键。

    下游一律按编码取数、不按名称匹配，所以这里的 name 只用于展示。
    """

    __tablename__ = "field_registry"

    field_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    # 标准单位。金额为元、面积为亩、体积为立方米、温室气体为吨CO2e、能源为吨标准煤。
    # 单位换算在抽取环节完成，落库的已是标准单位，故 field_value 不再重复存单位。
    unit: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(8), index=True)
    source_location: Mapped[str | None] = mapped_column(String(255))
    downstream_usage: Mapped[str | None] = mapped_column(String(512))
    # 定性条目 value 为文本，不参与数值计算，只供语义判断与外部交叉核验
    is_qualitative: Mapped[bool] = mapped_column(Boolean, default=False)
    industry_scope: Mapped[str] = mapped_column(String(16), default=SCOPE_ALL, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class FieldValue(Base):
    """字段值：公司 × 报告期 × 字段编码。

    唯一约束让重复抽取走 upsert 而不是堆历史行，跨企业对比与期间筛选
    （技术架构文档 8.5 结构化条件查询）才能直接查这张表。
    值的历史留痕靠 task_id 与版本快照，不靠堆行。
    """

    __tablename__ = "field_value"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "fiscal_year", "period", "field_code", name="uq_field_value_scope"
        ),
        Index("ix_field_value_lookup", "field_code", "fiscal_year", "period"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    period: Mapped[str] = mapped_column(String(16))
    field_code: Mapped[str] = mapped_column(
        String(64), ForeignKey("field_registry.field_code", ondelete="RESTRICT")
    )
    # 定量走 value_num，定性走 value_text，由 field_registry.is_qualitative 区分。
    # 注解必须是 Decimal 而非 float：Numeric 回读得到 Decimal，写成 float 会让
    # 下游 value_num * 0.05 这类运算在运行时抛 TypeError。
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    value_text: Mapped[str | None] = mapped_column(LONGTEXT)
    evidence_id: Mapped[str | None] = mapped_column(String(128), index=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    # 未绑定证据锚点的字段按 8.3 不得进入上层结果，此标记供人工复核队列取用
    need_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
