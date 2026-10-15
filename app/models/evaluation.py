"""标注与评估域：人工标注、错误案例库、评估样本与指标（技术架构文档 9.1 表 18、11.5）。

技术架构文档只给出这一域的用途与四层评估的量化指标，没有逐表列字段，因此这里的
列按 11.5 表 21 的指标口径倒推，属于推断而非文档明定，口径可能随评估方案细化而调整。
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
    SmallInteger,
    String,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 11.5 表 21 的四层测试
LAYER_PARSE = "parse"
LAYER_EXTRACT = "extract"
LAYER_ANALYZE = "analyze"
LAYER_E2E = "e2e"

# 11.5 列出的评估指标。metric_code 一律取自此处，避免同一指标出现多种写法。
METRIC_BLOCK_BOUNDARY_ACC = "block_boundary_accuracy"      # 块边界准确率
METRIC_TABLE_STRUCTURE_ACC = "table_structure_accuracy"    # 表格结构还原准确率
METRIC_OCR_CONFIDENCE_DIST = "ocr_confidence_distribution"  # 识别置信度分布
METRIC_FIELD_PRECISION = "field_precision"                 # 字段级准确率
METRIC_FIELD_RECALL = "field_recall"                       # 字段级召回率
METRIC_FIELD_F1 = "field_f1"                               # 字段级 F1 值
METRIC_RECALC_AGREEMENT = "recalc_agreement"               # 与人工复算一致率
METRIC_ANNOTATOR_KAPPA = "annotator_kappa"                 # 标注一致性系数
METRIC_TASK_SUCCESS_RATE = "task_success_rate"             # 任务成功率
METRIC_AVG_DURATION = "avg_duration"                       # 平均耗时
METRIC_HUMAN_INTERVENTIONS = "human_interventions"         # 人工介入次数
METRIC_ANOMALY_RATE = "anomaly_rate"                       # 异常发生率


class Annotation(Base):
    """人工标注表：抽取结果的金标准。

    抽取层要算字段级准确率、召回率与 F1（11.5），必须有独立于模型输出的人工标注
    作对照；同一字段多人标注时用 annotator 区分，分析层的标注一致性系数按同一
    (document, field, period) 下多位标注者的分歧计算。
    """

    __tablename__ = "annotation"
    __table_args__ = (
        Index("ix_annotation_lookup", "company_id", "field_code", "fiscal_year", "period"),
        Index("ix_annotation_document", "document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    document_id: Mapped[int | None] = mapped_column(BigInteger)
    field_code: Mapped[str] = mapped_column(String(64))
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    period: Mapped[str] = mapped_column(String(16))
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    value_text: Mapped[str | None] = mapped_column(LONGTEXT)
    evidence_id: Mapped[str | None] = mapped_column(String(128))
    annotator: Mapped[str] = mapped_column(String(64))
    is_gold: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ErrorCase(Base):
    """错误案例库。

    7.2 的 archive_case 节点把纠错反馈写进这里，12.2 第六阶段交付错误案例库。
    expected/actual 分开存而不是只留一句描述的用意是：案例要能直接当回归测试样本跑，
    只存文字描述的话还得人工重新构造输入。
    """

    __tablename__ = "error_case"
    __table_args__ = (
        Index("ix_error_case_capability", "capability_code", "case_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    capability_code: Mapped[str | None] = mapped_column(String(64))
    case_type: Mapped[str] = mapped_column(String(32))
    input_ref: Mapped[dict | None] = mapped_column(JSON)
    expected: Mapped[str | None] = mapped_column(LONGTEXT)
    actual: Mapped[str | None] = mapped_column(LONGTEXT)
    root_cause: Mapped[str | None] = mapped_column(LONGTEXT)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EvalSample(Base):
    """评估样本表：一次评估所针对的对象。

    layer 决定这个样本走哪一层测试（11.5），document_id / task_id 二选一：
    解析与抽取层针对单份文档，分析层与端到端针对一次任务执行。
    """

    __tablename__ = "eval_sample"
    __table_args__ = (
        Index("ix_eval_sample_layer", "layer", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sample_code: Mapped[str] = mapped_column(String(64), unique=True)
    layer: Mapped[str] = mapped_column(String(16))
    document_id: Mapped[int | None] = mapped_column(BigInteger)
    task_id: Mapped[int | None] = mapped_column(BigInteger)
    company_id: Mapped[int | None] = mapped_column(BigInteger)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EvalMetric(Base):
    """评估指标表：样本在某个指标上的取值（9.1、11.5）。

    指标名以 metric_code 为准，metric_name 只作展示。置信度分布这类非标量结果
    放 detail 里，主值仍留在 metric_value，便于跨样本排序与门槛判断。
    """

    __tablename__ = "eval_metric"
    __table_args__ = (
        Index("ix_eval_metric_lookup", "layer", "metric_code"),
        Index("ix_eval_metric_sample", "eval_sample_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    eval_sample_id: Mapped[int | None] = mapped_column(BigInteger)
    layer: Mapped[str] = mapped_column(String(16))
    metric_code: Mapped[str] = mapped_column(String(64))
    metric_name: Mapped[str | None] = mapped_column(String(128))
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    unit: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict | None] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
