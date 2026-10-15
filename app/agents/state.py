"""编排图共享状态。字段定义与技术架构文档第 7.1 节一致。

并行分支会同时写 results / evidence，因此这两类字段必须声明合并策略，
否则并发写入会互相覆盖。
"""

import operator
from typing import Annotated, Any, Literal, TypedDict


def merge_dict(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {**a, **b}


class TaskState(TypedDict, total=False):
    # 任务元信息
    task_id: str
    user_query: str
    run_mode: Literal["copilot", "autonomous"]
    task_type: str | None
    granularity: Literal["L1", "L2", "L3", "L4"]
    boundaries: dict[str, Any]
    version_snapshot: dict[str, Any]

    # 执行计划
    plan: list[dict[str, Any]]
    cursor: dict[str, Any]

    # 各能力产出（并行写入，需合并）
    results: Annotated[dict[str, Any], merge_dict]
    evidence: Annotated[dict[str, Any], merge_dict]

    # 异常与人工决定（追加语义）
    anomalies: Annotated[list[dict[str, Any]], operator.add]
    decisions: Annotated[list[dict[str, Any]], operator.add]

    # 各节点重试余量
    retry_budget: Annotated[dict[str, int], merge_dict]

    # 最终结果
    composed: dict[str, Any] | None
