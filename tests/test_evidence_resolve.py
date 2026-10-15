"""证据按锚点取原文。

技术架构文档 8.5 把检索分三种模式，并强调按用途严格区分。本模块实现的是**定向锚点
获取**：按块标识直接读取块记录，精确命中，不参与相关性排序。用语义检索去取本可精确
获取的内容，既降低准确率也浪费开销。

5.2 规定了返回内容：文档标识、页码、归一化坐标框、原文片段，表格类额外携带单元格
引用以便前端把高亮落到具体单元格。

要守住的点：
1. 锚点里的单元格引用不参与块查找——块标识只到块级，单元格是叠加在上面的定位信息。
2. 解析不出来的锚点必须报错，不能返回空导致前端静默失去高亮。
3. 批量取回时，取不到的条目要能被区分，而不是混在结果里。
"""

import pytest

from app.retrieval.evidence import resolve_anchor, resolve_anchors
from app.retrieval.ingest import DocumentSpec, ingest_document


@pytest.fixture
def ingested(db_session, company_id, sample_pdf, doc_code):
    """把三页样例 PDF 入库，返回 (doc_code, 期望的块标识列表)。"""
    spec = DocumentSpec(
        company_code="CN_999999",
        doc_type="annual_report",
        fiscal_year=2025,
        period="FY",
        lang="en",
        path=sample_pdf,
    )
    ingest_document(db_session, spec, company_id=company_id)
    # 样例 PDF：第 1 页两块、第 2 页空白、第 3 页一块
    return spec.doc_code, [f"{spec.doc_code}:1:0", f"{spec.doc_code}:1:1", f"{spec.doc_code}:3:0"]


@pytest.mark.db
class TestResolveAnchor:
    def test_resolves_block_anchor(self, db_session, ingested) -> None:
        doc_code, block_ids = ingested
        block = resolve_anchor(db_session, block_ids[0])
        assert block is not None
        assert block.block_id == block_ids[0]
        assert block.page_no == 1
        assert block.block_index == 0
        assert "Accounts receivable" in block.raw_text

    def test_returns_doc_code_and_file_name(self, db_session, ingested) -> None:
        """5.2：前端要拿文档标识去定位 PDF，缺了就没法渲染。"""
        doc_code, block_ids = ingested
        block = resolve_anchor(db_session, block_ids[0])
        assert block is not None
        assert block.doc_code == doc_code
        assert block.file_name.endswith(".pdf")

    def test_position_fields_present(self, db_session, ingested) -> None:
        """定位所需的三件套：页码、块序号、坐标框。坐标框当前为空，字段本身要在。"""
        _, block_ids = ingested
        block = resolve_anchor(db_session, block_ids[0])
        assert block is not None
        assert block.page_no >= 1
        assert block.block_index >= 0
        assert hasattr(block, "bbox")

    def test_cell_ref_does_not_affect_lookup(self, db_session, ingested) -> None:
        """锚点里的单元格引用是叠加信息，块查找只认块级标识。"""
        _, block_ids = ingested
        plain = resolve_anchor(db_session, block_ids[0])
        with_cell = resolve_anchor(db_session, f"{block_ids[0]}#表1R3C2")
        assert with_cell is not None and plain is not None
        assert with_cell.block_id == plain.block_id
        assert with_cell.cell_ref == "表1R3C2"
        assert plain.cell_ref is None

    def test_missing_block_returns_none(self, db_session, ingested) -> None:
        """锚点合法但库里没有这个块——比如文档被重解析过。返回 None 由调用方决定怎么报。"""
        doc_code, _ = ingested
        assert resolve_anchor(db_session, f"{doc_code}:99:99") is None

    @pytest.mark.parametrize("bad", ["不是锚点", "DOC:1", "DOC:1:2:3", "DOC:007:0"])
    def test_malformed_anchor_raises(self, db_session, bad: str) -> None:
        """格式错的锚点要报错，不能静默返回 None——那会让前端的高亮无声消失。"""
        with pytest.raises(ValueError):
            resolve_anchor(db_session, bad)


@pytest.mark.db
class TestResolveAnchors:
    def test_batch_preserves_order_and_missing(self, db_session, ingested) -> None:
        """5.2：返回结论时要一并带上其关联的全部证据，顺序须与请求一致。"""
        doc_code, block_ids = ingested
        requested = [block_ids[0], f"{doc_code}:99:99", block_ids[2]]
        results = resolve_anchors(db_session, requested)
        assert len(results) == 3
        assert results[0] is not None and results[0].block_id == block_ids[0]
        assert results[1] is None, "不存在的块应占位为 None，而不是被挤掉"
        assert results[2] is not None and results[2].block_id == block_ids[2]

    def test_batch_empty_input(self, db_session) -> None:
        assert resolve_anchors(db_session, []) == []

    def test_batch_all_found(self, db_session, ingested) -> None:
        _, block_ids = ingested
        results = resolve_anchors(db_session, block_ids)
        assert [r.block_id for r in results if r] == block_ids
