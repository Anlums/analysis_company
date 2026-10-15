"""证据接口测试。

接口层要守住的是两种失败必须被分开报：锚点**格式非法**是调用方的错（422），
锚点**合法但块不存在**是数据状态问题（404）。混成一个的话，前端无法判断该提示用户
改输入，还是该提示证据已失效。
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.retrieval.ingest import DocumentSpec, ingest_document

API = "/api/v1/evidence"


@pytest.fixture
def client(db_session):
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def ingested(db_session, company_id, sample_pdf):
    spec = DocumentSpec(
        company_code="CN_999999",
        doc_type="annual_report",
        fiscal_year=2025,
        period="FY",
        lang="en",
        path=sample_pdf,
    )
    ingest_document(db_session, spec, company_id=company_id)
    return spec.doc_code


@pytest.mark.db
class TestAnchorEndpoint:
    def test_returns_source_block(self, client, ingested) -> None:
        resp = client.get(f"{API}/anchor", params={"anchor": f"{ingested}:1:0"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["block_id"] == f"{ingested}:1:0"
        assert data["doc_code"] == ingested
        assert "Accounts receivable" in data["raw_text"]

    def test_response_carries_highlight_fields(self, client, ingested) -> None:
        """5.2 要求前端能定位并高亮：文档标识、页码、坐标框、原文四者齐备。"""
        resp = client.get(f"{API}/anchor", params={"anchor": f"{ingested}:1:0"})
        data = resp.json()["data"]
        for field in ("doc_code", "page_no", "bbox", "raw_text", "file_name"):
            assert field in data, f"缺少定位/展示所需字段：{field}"
        assert data["page_no"] == 1

    def test_anchor_is_echoed_back_parsed(self, client, ingested) -> None:
        resp = client.get(f"{API}/anchor", params={"anchor": f"{ingested}:1:0"})
        anchor = resp.json()["data"]["anchor"]
        assert anchor["doc_code"] == ingested
        assert anchor["page_no"] == 1
        assert anchor["block_index"] == 0

    def test_cell_ref_passes_through(self, client, ingested) -> None:
        """表格证据的单元格引用要透出，前端据此把高亮落到单元格而非整表。"""
        resp = client.get(f"{API}/anchor", params={"anchor": f"{ingested}:1:0#表1R3C2"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["block_id"] == f"{ingested}:1:0"
        assert data["cell_ref"] == "表1R3C2"

    def test_missing_block_is_404(self, client, ingested) -> None:
        resp = client.get(f"{API}/anchor", params={"anchor": f"{ingested}:99:99"})
        assert resp.status_code == 404
        assert "库中没有对应原文块" in resp.json()["detail"]

    @pytest.mark.parametrize("bad", ["不是锚点", "DOC:1", "DOC:1:2:3", ""])
    def test_malformed_anchor_is_422(self, client, bad: str) -> None:
        resp = client.get(f"{API}/anchor", params={"anchor": bad})
        assert resp.status_code == 422

    def test_missing_anchor_param_is_422(self, client) -> None:
        assert client.get(f"{API}/anchor").status_code == 422


@pytest.mark.db
class TestBatchEndpoint:
    def test_returns_blocks_in_request_order(self, client, ingested) -> None:
        anchors = [f"{ingested}:1:1", f"{ingested}:1:0"]
        resp = client.post(f"{API}/resolve", json={"anchors": anchors})
        assert resp.status_code == 200
        blocks = resp.json()["data"]["blocks"]
        assert [b["block_id"] for b in blocks] == anchors, "顺序必须与请求一致"

    def test_unresolvable_entries_kept_as_null(self, client, ingested) -> None:
        """占位而不是过滤：一条证据失效不能让后面全部错位。"""
        anchors = [f"{ingested}:1:0", f"{ingested}:99:99", f"{ingested}:3:0"]
        resp = client.post(f"{API}/resolve", json={"anchors": anchors})
        blocks = resp.json()["data"]["blocks"]
        assert len(blocks) == 3
        assert blocks[1] is None
        assert blocks[0] is not None and blocks[2] is not None

    def test_empty_list_rejected(self, client) -> None:
        """空列表没有意义，且会让「取不到」与「没请求」长得一样。"""
        assert client.post(f"{API}/resolve", json={"anchors": []}).status_code == 422

    def test_oversized_batch_rejected(self, client) -> None:
        resp = client.post(f"{API}/resolve", json={"anchors": ["DOC:1:0"] * 201})
        assert resp.status_code == 422

    def test_any_malformed_anchor_rejects_whole_batch(self, client, ingested) -> None:
        """部分成功会让调用方以为拿到的都对得上，宁可整批拒绝。"""
        resp = client.post(
            f"{API}/resolve", json={"anchors": [f"{ingested}:1:0", "坏锚点"]}
        )
        assert resp.status_code == 422

    def test_batch_of_one_works(self, client, ingested) -> None:
        resp = client.post(f"{API}/resolve", json={"anchors": [f"{ingested}:1:0"]})
        assert resp.status_code == 200
        assert len(resp.json()["data"]["blocks"]) == 1
