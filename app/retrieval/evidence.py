"""证据按锚点取原文——技术架构文档 8.5 的「定向锚点获取」模式。

三种检索模式按用途严格区分：需要确定答案时用定向获取或条件查询，只有需要从大量
文本中找出相关片段时才用语义检索。本模块是前者：按块标识直接读取块记录，精确命中，
不参与相关性排序。用语义检索去取本可精确获取的内容，既降低准确率也浪费开销。

5.2 规定了证据溯源需要返回的内容：文档标识、页码、归一化坐标框、原文片段；表格类
额外携带单元格引用，使前端能把高亮施加到具体单元格而非整张表格。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentBlock
from app.schemas.evidence import EvidenceAnchor


@dataclass(frozen=True)
class SourceBlock:
    """证据回指的原文块，前端据此定位并高亮。"""

    block_id: str
    doc_code: str
    document_id: int
    file_name: str
    page_no: int
    block_index: int
    block_type: str
    raw_text: str
    # 归一化坐标框。坐标以页面尺寸归一化存储，高亮在任意缩放比例下都能正确对齐（5.2）。
    # 当前解析器只做文本切块、还没有版面分析，故恒为 None；前端需容忍它为空。
    bbox: dict | None
    is_ocr: bool
    ocr_confidence: float | None
    # 表格类证据的单元格引用，形如「表1R3C2」；非表格证据为空
    cell_ref: str | None = None


def _to_source_block(
    block: DocumentBlock, doc: Document, cell_ref: str | None
) -> SourceBlock:
    return SourceBlock(
        block_id=block.block_id,
        doc_code=doc.doc_code,
        document_id=doc.id,
        file_name=doc.file_name,
        page_no=block.page_no,
        block_index=block.block_index,
        block_type=block.block_type,
        raw_text=block.raw_text or "",
        bbox=block.bbox,
        is_ocr=block.is_ocr,
        ocr_confidence=block.ocr_confidence,
        cell_ref=cell_ref,
    )


def resolve_anchor(session: Session, anchor: str) -> SourceBlock | None:
    """按锚点取原文块。

    返回 None 表示锚点合法但库里没有这个块——例如文档被重解析、旧块已被替换。
    锚点格式非法则抛 ValueError：静默返回 None 会让前端的证据高亮无声消失，
    而这两种情况的处理方式完全不同。
    """
    return resolve_anchors(session, [anchor])[0]


def resolve_anchors(session: Session, anchors: Sequence[str]) -> list[SourceBlock | None]:
    """批量取回，顺序与入参一一对应，取不到的条目占位 None。

    批量而非逐个查询：返回一条结论时要一并带上它关联的全部证据（5.2），
    逐个查会把一次响应变成 N 次往返。

    单元格引用不参与查找——块标识只到块级，单元格是叠加在上面的定位信息。
    """
    parsed = [EvidenceAnchor.parse(a) for a in anchors]
    if not parsed:
        return []

    block_ids = {a.block_anchor for a in parsed}
    rows = session.execute(
        select(DocumentBlock, Document)
        .join(Document, Document.id == DocumentBlock.document_id)
        .where(DocumentBlock.block_id.in_(block_ids))
    ).all()
    found = {block.block_id: (block, doc) for block, doc in rows}

    return [
        _to_source_block(*found[anchor.block_anchor], anchor.cell_ref)
        if anchor.block_anchor in found
        else None
        for anchor in parsed
    ]
