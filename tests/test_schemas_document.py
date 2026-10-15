"""文档域出入参契约测试。

守住两条：
1. 块标识只能由 (文档标识, 页号, 块序号) 派生，调用方无法自填一个与坐标矛盾的标识。
   表上唯一约束是 (document_id, page_no, block_index)，block_id 列本身自由，
   允许自填的话填错不会被任何约束拦下，而由它派生的锚点此后全部失效。
2. 识别来源的块必须带识别置信度——扫描页的置信度要参与下游证据可靠性评估，
   缺失会让 OCR 结果被当成原生文本层同等可信。
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import make_block_id
from app.schemas.document import BBox, DocumentBlockCreate, DocumentCreate

BASE_DOC = {
    "company_id": 1,
    "doc_type": "annual_report",
    "file_name": "2025年年度报告.pdf",
    "file_path": "data/raw/2025.pdf",
    "file_hash": "0" * 64,
}


def _doc(**overrides: object) -> dict:
    return {**BASE_DOC, **overrides}


class TestBlockIdDerivation:
    def test_block_id_derived_from_position(self, doc_code: str) -> None:
        block = DocumentBlockCreate(
            doc_code=doc_code, page_no=42, block_index=3, block_type="table"
        )
        assert block.block_id == f"{doc_code}:42:3"

    def test_block_id_matches_make_block_id(self, doc_code: str) -> None:
        """构造侧与共用函数必须一致，否则两条链路分叉。"""
        block = DocumentBlockCreate(
            doc_code=doc_code, page_no=7, block_index=0, block_type="text"
        )
        assert block.block_id == make_block_id(doc_code, 7, 0)

    def test_cannot_accept_caller_supplied_block_id(self, doc_code: str) -> None:
        """block_id 不是入参，传了应当被忽略而不是覆盖派生值。"""
        block = DocumentBlockCreate(
            doc_code=doc_code,
            page_no=42,
            block_index=3,
            block_type="text",
            block_id="完全不对的标识",  # type: ignore[call-arg]
        )
        assert block.block_id == f"{doc_code}:42:3"

    def test_doc_code_validated_on_block(self) -> None:
        with pytest.raises(ValidationError):
            DocumentBlockCreate(
                doc_code="600519.SH", page_no=1, block_index=0, block_type="text"
            )

    @pytest.mark.parametrize("page_no,block_index", [(0, 0), (-1, 0), (1, -1), (10000, 0)])
    def test_position_bounds(self, doc_code: str, page_no: int, block_index: int) -> None:
        with pytest.raises(ValidationError):
            DocumentBlockCreate(
                doc_code=doc_code,
                page_no=page_no,
                block_index=block_index,
                block_type="text",
            )


class TestOcrContract:
    def test_ocr_block_requires_confidence(self, doc_code: str) -> None:
        with pytest.raises(ValidationError):
            DocumentBlockCreate(
                doc_code=doc_code, page_no=1, block_index=0, block_type="text", is_ocr=True
            )

    def test_ocr_block_accepts_confidence(self, doc_code: str) -> None:
        block = DocumentBlockCreate(
            doc_code=doc_code,
            page_no=1,
            block_index=0,
            block_type="text",
            is_ocr=True,
            ocr_confidence=0.93,
        )
        assert block.ocr_confidence == 0.93

    def test_native_block_needs_no_confidence(self, doc_code: str) -> None:
        block = DocumentBlockCreate(
            doc_code=doc_code, page_no=1, block_index=0, block_type="text"
        )
        assert block.is_ocr is False
        assert block.ocr_confidence is None

    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_confidence_range(self, doc_code: str, bad: float) -> None:
        with pytest.raises(ValidationError):
            DocumentBlockCreate(
                doc_code=doc_code,
                page_no=1,
                block_index=0,
                block_type="text",
                is_ocr=True,
                ocr_confidence=bad,
            )


class TestBBox:
    def test_valid_bbox(self) -> None:
        box = BBox(x0=0.08, y0=0.31, x1=0.92, y1=0.44)
        assert box.x1 > box.x0 and box.y1 > box.y0

    def test_rejects_inverted_x(self) -> None:
        with pytest.raises(ValidationError):
            BBox(x0=0.9, y0=0.1, x1=0.2, y1=0.5)

    def test_rejects_inverted_y(self) -> None:
        with pytest.raises(ValidationError):
            BBox(x0=0.1, y0=0.9, x1=0.5, y1=0.2)

    @pytest.mark.parametrize("bad", [-0.01, 1.01])
    def test_rejects_out_of_range(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            BBox(x0=0.0, y0=0.0, x1=bad, y1=1.0)

    def test_is_frozen(self) -> None:
        box = BBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0)
        with pytest.raises(ValidationError):
            box.x0 = 0.5  # type: ignore[misc]

    def test_zero_area_allowed(self) -> None:
        """单点或单行块是合法的，不能因为 x0==x1 就拒。"""
        BBox(x0=0.5, y0=0.5, x1=0.5, y1=0.5)


class TestDocumentCreate:
    @pytest.mark.parametrize(
        "bad_code", ["600519.SH", "岳阳林纸", "CN:600963", "DOC#1", "CN 600963", ""]
    )
    def test_rejects_illegal_doc_code(self, bad_code: str) -> None:
        with pytest.raises(ValidationError):
            DocumentCreate(doc_code=bad_code, **_doc())  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "good", ["CN_600963_2025_ANNUAL", "EN-HOLMEN-2024", "doc123", "A_B_C_1"]
    )
    def test_accepts_legal_doc_code(self, good: str) -> None:
        assert DocumentCreate(doc_code=good, **_doc()).doc_code == good

    def test_rejects_unknown_doc_type(self) -> None:
        with pytest.raises(ValidationError):
            DocumentCreate(doc_code="DOC1", **_doc(doc_type="passport"))

    @pytest.mark.parametrize("period", ["FY", "H1", "Q1", "Q2", "Q3", "Q4"])
    def test_accepts_quarter_periods(self, period: str) -> None:
        """季度粒度靠 period 承载，不新增编码，故 Q1–Q4 必须放行。"""
        assert DocumentCreate(doc_code="DOC1", **_doc(period=period)).period == period

    def test_rejects_unknown_period(self) -> None:
        with pytest.raises(ValidationError):
            DocumentCreate(doc_code="DOC1", **_doc(period="H2"))
