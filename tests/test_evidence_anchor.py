"""证据锚点契约测试。

锚点是「结论可回指原文」的唯一凭据。这一层要守住的性质按重要性排序：

1. 往返一致 —— str(parse(s)) == s。块标识是确定性生成的字符串，若解析会改写它
   （去前导零、截断尾随空白），锚点就查不到块，而且不报错。
2. 块级锚点与单元格锚点可互相派生 —— 前端高亮按块定位，表格证据再精到单元格。
3. 非法输入一律拒绝 —— 宁可报错也不要静默接受一个下游解不开的锚点。
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import make_block_id
from app.schemas.evidence import EvidenceAnchor

ROUND_TRIP_CASES = [
    "CN_600963_2025_ANNUAL:42:3",
    "CN_600963_2025_ANNUAL:1:0",
    "EN_HOLMEN_2024_ANNUAL:7:12",
    "CN_600963_2025_ANNUAL:42:3#表1R3C2",
    "EN_UPM_2023_SUSTAINABILITY:120:5#表12R88C7",
]


@pytest.mark.parametrize("anchor", ROUND_TRIP_CASES)
def test_round_trip_is_lossless(anchor: str) -> None:
    """解析再渲染必须逐字相同，这是锚点可回指的前提。"""
    assert str(EvidenceAnchor.parse(anchor)) == anchor


@pytest.mark.parametrize("anchor", ROUND_TRIP_CASES)
def test_round_trip_preserves_block_anchor(anchor: str) -> None:
    parsed = EvidenceAnchor.parse(anchor)
    assert parsed.block_anchor == anchor.split("#", 1)[0]


def test_block_anchor_drops_cell_ref(doc_code: str) -> None:
    anchor = EvidenceAnchor.parse(f"{doc_code}:42:3#表1R3C2")
    assert anchor.cell_ref == "表1R3C2"
    assert anchor.block_anchor == f"{doc_code}:42:3"


def test_block_anchor_equals_make_block_id(doc_code: str) -> None:
    """锚点反解出的块标识必须与构造侧生成的一致，否则两条链路会分叉。"""
    anchor = EvidenceAnchor.parse(f"{doc_code}:42:3#表1R3C2")
    assert anchor.block_anchor == make_block_id(doc_code, 42, 3)


REJECT_CASES = [
    ("CN600:42", "缺少块序号"),
    ("CN:600:42:3", "文档标识含冒号"),
    ("DOC:0:3", "页号不得为 0"),
    ("DOC:42", "只有两段"),
    ("DOC:42:3:extra", "段数过多"),
    ("DOC:007:03", "前导零会破坏往返一致"),
    ("DOC:42:3\n", "尾随换行"),
    ("岳阳林纸:42:3", "中文文档标识"),
    ("600519.SH:42:3", "A 股点号写法"),
    ("", "空串"),
    ("DOC:42:3#R3C2", "单元格引用缺「表N」前缀"),
]


@pytest.mark.parametrize("raw,reason", REJECT_CASES)
def test_rejects_malformed_anchor(raw: str, reason: str) -> None:
    with pytest.raises(ValueError):
        EvidenceAnchor.parse(raw)


def test_doc_code_with_dot_rejected_constructing_directly() -> None:
    """直接构造也要拦——写入侧宽松会让库里存下解析不出的标识。"""
    with pytest.raises(ValidationError):
        EvidenceAnchor(doc_code="600519.SH", page_no=1, block_index=0)


def test_cell_ref_format_enforced() -> None:
    with pytest.raises(ValidationError):
        EvidenceAnchor(doc_code="DOC", page_no=1, block_index=0, cell_ref="R3C2")
    with pytest.raises(ValidationError):
        EvidenceAnchor(doc_code="DOC", page_no=1, block_index=0, cell_ref="表0R3C2")


def test_anchor_is_frozen() -> None:
    """锚点不可变：它是证据链的一环，改了就没法追溯。"""
    anchor = EvidenceAnchor(doc_code="DOC", page_no=1, block_index=0)
    with pytest.raises(ValidationError):
        anchor.page_no = 2  # type: ignore[misc]
