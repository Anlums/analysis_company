"""配置域（二）：阈值方案、规则集、ESG 权重方案（技术架构文档 9.1 表 18、9.2、10.2）。

这三张表是「规则可配置」的载体：业务配置不通过环境变量管理，而是作为配置数据
存于数据库，支持运行时切换与版本回滚（6.4）。规则集与权重方案都带版本号，
版本快照引用具体版本号，因此历史任务回查时拿到的是当时那版规则，不是最新版。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 线索等级：财务分析计划书 3.4.1 把每条指标分弱/中/强三档触发
CLUE_WEAK = "weak"
CLUE_MEDIUM = "medium"
CLUE_STRONG = "strong"

# 规则集类型
RULE_THEME_COMPOSE = "theme_compose"      # 表3 综合风险合成规则（六大主题 → 四级信号灯）
RULE_STAR_MAPPING = "star_mapping"        # ESG 七维总分 → 星级
RULE_ANOMALY_CAUSE = "anomaly_cause"      # 行业包第五项：典型异常成因框架
RULE_SIGNAL_LIGHT = "signal_light"        # 财务四级信号灯合成


class Threshold(Base):
    """阈值表，主键「指标编码 + 线索等级 + 行业范围」（9.2）。

    行业范围为空表示全局默认值，非空表示对该行业的覆盖。这样林业包只需为噪声偏大的
    指标写覆盖行，其余沿用默认，不必整表复制（10.1）。

    lower_bound/upper_bound 表达区间型判定（如「差值 10%–20%」）；条件里带「方向相反」
    这类非区间判定的，数值列留空、条件写在 condition 里，原文措辞留在 raw_text 便于核对。
    """

    __tablename__ = "threshold"
    __table_args__ = (
        Index("ix_threshold_industry", "industry_scope"),
    )

    indicator_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    clue_level: Mapped[str] = mapped_column(String(16), primary_key=True)
    # 空串而非 NULL 作主键的一部分：MySQL 唯一索引对 NULL 不去重，用 NULL 会让同一
    # 组合重复插入而不报错，全局默认阈值会出现多行
    industry_scope: Mapped[str] = mapped_column(String(32), primary_key=True, default="")
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    # 非区间型判定的完整条件，如 {"type": "opposite_direction"}
    condition: Mapped[dict | None] = mapped_column(JSON)
    # 计划书里的原文表述，便于人工核对阈值有没有录错
    raw_text: Mapped[str | None] = mapped_column(String(512))
    note: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RuleSet(Base):
    """规则集表：主题合成规则、星级映射规则、典型异常成因框架（9.2）。

    携带版本号与生效时间，支持历史版本回查。生效期用 effective_from/effective_to
    表示，to 为空表示仍在生效；同一 (类型, 行业, 版本) 唯一，改规则发文号而非改行。
    """

    __tablename__ = "rule_set"
    __table_args__ = (
        UniqueConstraint(
            "rule_type", "industry_code", "version", name="uq_rule_set_version"
        ),
        Index("ix_rule_set_active", "rule_type", "industry_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_type: Mapped[str] = mapped_column(String(32))
    # 空串而非 NULL：MySQL 唯一索引对 NULL 不去重，用 NULL 会让「全局通用规则」这一形态
    # （恰恰是主用形态）在同一版本号下重复插入而不报错，版本快照按 (类型, 版本) 回查
    # 就会取到多行，复现结果不再确定。与 threshold.industry_scope 同一处理。
    # server_default 用 text("''") 而非字符串字面量：MySQL 把默认值读回来是 TextClause，
    # 两边不同型会让 alembic check 永远报 modify_default 漂移
    industry_code: Mapped[str] = mapped_column(
        String(32), default="", server_default=text("''")
    )
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    effective_from: Mapped[datetime] = mapped_column(DateTime)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WeightScheme(Base):
    """权重方案表：ESG 七维权重及分行业方案（9.2）。

    七维取自 ESG 对比智能体计划书的评分体系，默认权重 15/20/25/10/15/10/5。
    专家模式允许自定义权重，调整后实时重算并按样本内分位数归一化，因此同一
    方案必须能整组取回，不能把七个权重散落到别处。
    """

    __tablename__ = "weight_scheme"
    __table_args__ = (
        UniqueConstraint(
            "scheme_code", "industry_code", name="uq_weight_scheme_industry"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scheme_code: Mapped[str] = mapped_column(String(64))
    # 空串而非 NULL，原因同 RuleSet.industry_code
    industry_code: Mapped[str] = mapped_column(
        String(32), default="", server_default=text("''")
    )
    weight_process: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    weight_materiality: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    weight_completeness: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    weight_balance: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    weight_comparability: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    weight_readability: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    weight_accessibility: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
