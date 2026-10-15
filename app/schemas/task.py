"""任务域出入参。

任务提加入参刻意保持精简：用户只给查询语句、运行模式与边界，调用哪些能力、以何种
依赖关系组合由综合调度智能体运行时决定（4.1），因此这里不允许调用方指定能力清单——
一旦开放这个入口，动态编排就退化成了固定流程。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.task import (
    GRANULARITY_L1,
    GRANULARITY_L2,
    GRANULARITY_L3,
    GRANULARITY_L4,
    RUN_MODE_AUTONOMOUS,
    RUN_MODE_COPILOT,
    STATUS_CANCELLED,
    STATUS_DEGRADED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_WAITING_HUMAN,
)

RUN_MODES = (RUN_MODE_COPILOT, RUN_MODE_AUTONOMOUS)
GRANULARITIES = (GRANULARITY_L1, GRANULARITY_L2, GRANULARITY_L3, GRANULARITY_L4)
TASK_STATUSES = (
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_WAITING_HUMAN,
    STATUS_SUCCEEDED,
    STATUS_DEGRADED,
    STATUS_FAILED,
    STATUS_CANCELLED,
)


class TaskBoundaries(BaseModel):
    """任务边界：企业范围、年度范围、允许重试次数（7.1）。"""

    company_ids: list[int] = []
    fiscal_years: list[int] = []
    max_retry_per_node: int = Field(default=2, ge=0, le=10)


class TaskCreate(BaseModel):
    user_query: str = Field(min_length=1)
    run_mode: str = RUN_MODE_COPILOT
    parent_task_id: int | None = Field(
        default=None, description="追问场景：基于已有任务的结论继续问"
    )
    session_id: str | None = Field(default=None, max_length=64)
    boundaries: TaskBoundaries = Field(default_factory=TaskBoundaries)

    @field_validator("run_mode")
    @classmethod
    def _check_mode(cls, v: str) -> str:
        if v not in RUN_MODES:
            raise ValueError(f"运行模式须为 {RUN_MODES} 之一")
        return v


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_code: str
    parent_task_id: int | None = None
    session_id: str | None = None
    user_query: str | None = None
    task_type: str | None = None
    run_mode: str
    granularity: str | None = None
    status: str
    boundaries: dict | None = None
    version_snapshot_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class TaskNodeRead(BaseModel):
    """节点执行情况。执行链路可视化与问题定位的主要数据来源（9.2）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    node_code: str
    capability_code: str | None = None
    agent_code: str | None = None
    status: str
    input_ref: dict | None = None
    output_ref: dict | None = None
    confidence: float | None = None
    retry_count: int
    error_code: str | None = None
    error_detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskOutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    task_node_id: int | None = None
    capability_code: str | None = None
    level: str
    content: dict | None = None
    need_review: bool
    created_at: datetime


class VersionSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    snapshot_code: str
    llm_model: str
    llm_params: dict | None = None
    prompt_versions: dict | None = None
    rule_set_versions: dict | None = None
    threshold_version: str | None = None
    parser_version: str | None = None
    embedding_model: str | None = None
    created_at: datetime


class CapabilityRead(BaseModel):
    """能力池登记内容（7.6）。调度据此做就绪判定，不体现执行顺序。"""

    model_config = ConfigDict(from_attributes=True)

    capability_code: str
    agent_code: str
    responsibility: str | None = None
    input_requirements: dict | None = None
    output_contract: dict | None = None
    callable_tools: dict | None = None
    applicable_scenarios: str | None = None
    inapplicable_scenarios: str | None = None
    anomaly_types: dict | None = None
    depends_on: dict | None = None
    version: str
    is_active: bool


class TaskDetail(TaskRead):
    """任务详情：状态 + 执行链路 + 分层结果。"""

    nodes: list[TaskNodeRead] = []
    outputs: list[TaskOutputRead] = []
    snapshot: VersionSnapshotRead | None = None
