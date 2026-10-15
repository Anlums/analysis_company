"""能力池注册与编排检查点存储。

技术架构文档 9.4 要求原型期在 MySQL 中建检查点表与检查点写入表，并实现编排框架的
检查点存储接口。两张表的列名与类型对齐 LangGraph 的 BaseCheckpointSaver 契约，
落库前经 serde 序列化为 (type, blob) 二元组，所以存的是 BLOB 而非结构化列——
序列化格式由框架决定，用结构化列会在框架升级时被卡住。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 承载智能体（4.2 五智能体总览）
AGENT_DISPATCH = "dispatch"
AGENT_EXTRACT = "extract"
AGENT_FINANCE = "finance"
AGENT_ESG = "esg"
AGENT_BILINGUAL = "bilingual"

# 能力池成员只有四个业务能力，综合调度是调度发起方，不进入能力池（4.2）
CAPABILITY_POOL_AGENTS = (
    AGENT_EXTRACT,
    AGENT_FINANCE,
    AGENT_ESG,
    AGENT_BILINGUAL,
)


class Capability(Base):
    """能力池登记表（7.6）。

    登记内容原样对应 7.6：能力标识、承载智能体、职责边界、输入要求、输出契约、
    可调用工具、适用场景、不可用场景、异常上报类型与版本标识。

    这张表在 9.1 表 18 的域划分里没有列出，但 4.1、7.6、10.3 三处都描述了登记内容，
    且「调度节点依据能力池中的依赖声明动态生成就绪判定」要求它可查询，故补建。
    """

    __tablename__ = "capability"

    capability_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_code: Mapped[str] = mapped_column(String(32), index=True)
    # 职责边界：哪些事属于本能力、哪些不属于，调度据此判断任务是否需要调用它
    responsibility: Mapped[str | None] = mapped_column(String(1024))
    input_requirements: Mapped[dict | None] = mapped_column(JSON)
    output_contract: Mapped[dict | None] = mapped_column(JSON)
    callable_tools: Mapped[dict | None] = mapped_column(JSON)
    applicable_scenarios: Mapped[str | None] = mapped_column(String(1024))
    inapplicable_scenarios: Mapped[str | None] = mapped_column(String(1024))
    anomaly_types: Mapped[dict | None] = mapped_column(JSON)
    # 上游依赖的能力标识，调度据此做就绪判定（7.3 汇合依赖靠前置集合实现）
    depends_on: Mapped[dict | None] = mapped_column(JSON)
    version: Mapped[str] = mapped_column(String(32), default="v0.1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class OrchestrationCheckpoint(Base):
    """检查点表：序列化后的状态快照与元数据（9.4）。

    列名与 LangGraph 对齐：thread_id 承载任务线程，checkpoint_ns 区分命名空间
    （子图与主图各占一个），checkpoint_id 单调递增标识本步。
    """

    __tablename__ = "orchestration_checkpoint"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(String(128))
    # serde 输出的类型标签与序列化后的快照本体
    type: Mapped[str | None] = mapped_column(String(64))
    checkpoint: Mapped[bytes] = mapped_column(LONGBLOB)
    checkpoint_metadata: Mapped[bytes | None] = mapped_column(LONGBLOB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CheckpointWrite(Base):
    """检查点写入表：各任务通道的中间写入（9.4）。

    一个检查点内，多个并行分支各自往自己的通道写值，idx 是同一 task 内的写入序号。
    不额外建索引：主键 (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) 的最左
    前缀已覆盖框架按线程 + 检查点取写入的查询。
    """

    __tablename__ = "checkpoint_write"

    thread_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(String(128), primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(64))
    value: Mapped[bytes | None] = mapped_column(LONGBLOB)
    task_path: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
