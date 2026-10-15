"""任务域：任务与节点状态、智能体产出、版本快照（技术架构文档 9.1 表 18、9.2、11.1、11.2）。

任务节点表是执行链路可视化与问题定位的主要数据来源（9.2），因此除状态外还必须
记下输入引用、输出引用、耗时与重试次数——可观测性（11.2）要能回答
“这个结论是哪个能力、在哪一步、依据哪段原文得出的”。
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
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 运行模式（7.1）
RUN_MODE_COPILOT = "copilot"
RUN_MODE_AUTONOMOUS = "autonomous"

# 结果颗粒度（4.1：L1–L4 由各能力自行生成，调度统一接收后按层级组织）
GRANULARITY_L1 = "L1"
GRANULARITY_L2 = "L2"
GRANULARITY_L3 = "L3"
GRANULARITY_L4 = "L4"

# 任务与节点状态
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_WAITING_HUMAN = "waiting_human"
STATUS_SUCCEEDED = "succeeded"
STATUS_DEGRADED = "degraded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


class Task(Base):
    """任务主表。

    parent_task_id 支撑基于已有结果的追问（4.1：追问可能完全不新增能力调用）。
    版本快照独立存储，多个任务可引用同一快照，避免版本信息重复存储（9.2）。
    """

    __tablename__ = "task"
    __table_args__ = (
        Index("ix_task_status", "status", "created_at"),
        Index("ix_task_session", "session_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_code: Mapped[str] = mapped_column(String(64), unique=True)
    parent_task_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("task.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64))
    user_query: Mapped[str | None] = mapped_column(LONGTEXT)
    task_type: Mapped[str | None] = mapped_column(String(32))
    run_mode: Mapped[str] = mapped_column(String(16), default=RUN_MODE_COPILOT)
    granularity: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(24), default=STATUS_PENDING)
    # 企业范围、年度范围、允许重试次数（7.1 boundaries）
    boundaries: Mapped[dict | None] = mapped_column(JSON)
    version_snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("version_snapshot.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaskNode(Base):
    """任务节点表：每个能力节点的执行情况（9.2）。

    node_code 对应编排图节点名（understand/plan/dispatch/run_extract/...，见 7.2），
    capability_code 对应该节点调用的能力池能力。调度节点与能力节点都落这张表，
    前者 capability_code 为空。
    """

    __tablename__ = "task_node"
    __table_args__ = (
        # 9.3：任务节点表按任务标识与状态建立复合索引，支撑执行链路查询
        Index("ix_task_node_lookup", "task_id", "status"),
        Index("ix_task_node_capability", "capability_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("task.id", ondelete="CASCADE")
    )
    node_code: Mapped[str] = mapped_column(String(32))
    capability_code: Mapped[str | None] = mapped_column(String(64))
    agent_code: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default=STATUS_PENDING)
    input_ref: Mapped[dict | None] = mapped_column(JSON)
    output_ref: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(LONGTEXT)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TaskOutput(Base):
    """产出表：各能力按 L1–L4 自行生成的颗粒度结果（4.1）。

    结果由承担职责的能力自行生成、调度统一接收后按层级组织，所以这里的 level
    是能力产出时就带上来的，不是调度事后补的。
    """

    __tablename__ = "task_output"
    __table_args__ = (
        Index("ix_task_output_lookup", "task_id", "level"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("task.id", ondelete="CASCADE")
    )
    task_node_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("task_node.id", ondelete="CASCADE"), index=True
    )
    capability_code: Mapped[str | None] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(4))
    content: Mapped[dict | None] = mapped_column(JSON)
    # 待核查标记随结果向上传递，最终呈现在结果视图中，不被静默丢弃（7.5）
    need_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VersionSnapshot(Base):
    """版本快照：任务创建时固化，执行全程只读快照指定的版本，不读“当前最新版本”（11.1）。

    这是「任意历史任务均可重放并复现当时结论」的载体，即便系统的规则与提示词
    已经更新。内容项与 11.1 逐条对应。
    """

    __tablename__ = "version_snapshot"
    __table_args__ = (
        UniqueConstraint("snapshot_code", name="uq_version_snapshot_code"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_code: Mapped[str] = mapped_column(String(64))
    llm_model: Mapped[str] = mapped_column(String(64))
    # 模型名称之外的推理参数（温度、top_p、max_tokens 等）
    llm_params: Mapped[dict | None] = mapped_column(JSON)
    # 各智能体提示词版本，形如 {"extract": "v0.1", "finance": "v0.2"}
    prompt_versions: Mapped[dict | None] = mapped_column(JSON)
    # 活跃规则集版本，形如 {"theme_compose": 3, "star_mapping": 1}
    rule_set_versions: Mapped[dict | None] = mapped_column(JSON)
    threshold_version: Mapped[str | None] = mapped_column(String(32))
    parser_version: Mapped[str | None] = mapped_column(String(32))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
