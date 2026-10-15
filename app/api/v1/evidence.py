"""证据接口：按锚点获取原文片段。

技术架构文档 6.1 表 14 把「证据按锚点获取」归在数据接口下。这是 5.2 证据溯源视图的
后端支撑：前端点击结论时，拿这条接口返回的页码与归一化坐标框去 PDF 上绘制高亮。

锚点走查询参数而不放进路径：锚点形如「文档标识:页号:块序号#表序R行C列」，其中的
「#」是 URL 的片段分隔符，放进路径必须转义，而转义在前后端之间极易漏掉一处，
漏掉的表现是后端只收到「#」之前的部分、锚点静默残缺。
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.retrieval.evidence import SourceBlock, resolve_anchor, resolve_anchors
from app.schemas.common import ApiResponse
from app.schemas.evidence import (
    AnchorBatchRequest,
    AnchorBatchResponse,
    SourceBlockRead,
)

router = APIRouter(prefix="/evidence", tags=["证据"])


def _to_read(block: SourceBlock) -> SourceBlockRead:
    return SourceBlockRead(**asdict(block))


@router.get(
    "/anchor",
    response_model=ApiResponse[SourceBlockRead],
    summary="按锚点取原文块",
)
def get_evidence_by_anchor(
    anchor: str = Query(..., description="形如 CN_600963_2025_ANNUAL:24:4#表1R3C2"),
    db: Session = Depends(get_db),
) -> ApiResponse[SourceBlockRead]:
    try:
        block = resolve_anchor(db, anchor)
    except ValueError as exc:
        # 格式非法是调用方的错，与「锚点合法但块不存在」必须分开报
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    if block is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"锚点 {anchor} 合法，但库中没有对应原文块（可能文档已重解析）",
        )
    return ApiResponse(data=_to_read(block))


@router.post(
    "/resolve",
    response_model=ApiResponse[AnchorBatchResponse],
    summary="批量按锚点取原文块",
)
def resolve_evidence_batch(
    payload: AnchorBatchRequest,
    db: Session = Depends(get_db),
) -> ApiResponse[AnchorBatchResponse]:
    """一次取回一条结论挂载的全部证据（5.2）。

    结果顺序与请求一致，取不到的条目为 null——过滤掉会让调用方无法把结果与请求对齐。
    任一锚点格式非法则整批拒绝：部分成功会让调用方以为拿到的都对得上。
    """
    try:
        blocks = resolve_anchors(db, payload.anchors)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    return ApiResponse(
        data=AnchorBatchResponse(
            blocks=[_to_read(b) if b is not None else None for b in blocks]
        )
    )
