"""文档入库测试。

入库把解析结果落进 document / document_block，是锚点链路真正成立的时刻。
这里要守住三件事：

1. doc_code 必须能被 EvidenceAnchor 解析。它是锚点的第一段，库建好之后再改
   会让所有已落库文档的证据链失效，所以格式在写入前就要与解析侧对齐。
2. 幂等。重跑入不了重复行——解析是一件会反复重跑的事（换解析器版本、补字段、
   修 bug），每次重跑都堆一份数据会让块标识冲突或翻倍。
3. 块数与解析结果一致，且块标识与解析器产出逐字相同。
"""

from pathlib import Path

import pytest

from app.retrieval.ingest import build_doc_code, ingest_document, DocumentSpec
from app.retrieval.parser import parse_pdf
from app.schemas.evidence import EvidenceAnchor
from tests.conftest import TEST_COMPANY_CODE


class TestBuildDocCode:
    def test_annual_report(self) -> None:
        assert build_doc_code("CN_600963", 2025, "annual_report") == "CN_600963_2025_ANNUAL"

    def test_interim_report(self) -> None:
        assert build_doc_code("CN_600963", 2026, "interim_report") == "CN_600963_2026_H1"

    def test_esg_report(self) -> None:
        assert build_doc_code("SE_HOLMEN", 2025, "esg_report") == "SE_HOLMEN_2025_ESG"

    def test_audit_report(self) -> None:
        assert build_doc_code("CN_600963", 2025, "audit_report") == "CN_600963_2025_AUDIT"

    @pytest.mark.parametrize(
        "company,year,doc_type",
        [
            ("CN_600963", 2025, "annual_report"),
            ("SE_HOLMEN", 2026, "interim_report"),
            ("SE_HOLMEN", 2025, "esg_report"),
        ],
    )
    def test_doc_code_is_anchor_parseable(self, company: str, year: int, doc_type: str) -> None:
        """跨模块契约：写入侧的文档标识必须能被锚点解析侧读回来。

        这条不成立的话，库里的文档一条证据都回指不了，而且写入时不报任何错。
        """
        doc_code = build_doc_code(company, year, doc_type)
        anchor = EvidenceAnchor.parse(f"{doc_code}:42:3")
        assert anchor.doc_code == doc_code
        assert str(anchor) == f"{doc_code}:42:3"

    def test_rejects_unknown_doc_type(self) -> None:
        with pytest.raises(ValueError):
            build_doc_code("CN_600963", 2025, "annual_report_summary")

    def test_rejects_out_of_range_year(self) -> None:
        with pytest.raises(ValueError):
            build_doc_code("CN_600963", 1899, "annual_report")


class TestDocumentSpec:
    def test_doc_code_derived_from_fields(self, sample_pdf: Path) -> None:
        spec = DocumentSpec(
            company_code="CN_600963",
            doc_type="annual_report",
            fiscal_year=2025,
            period="FY",
            lang="zh",
            path=sample_pdf,
        )
        assert spec.doc_code == "CN_600963_2025_ANNUAL"


@pytest.mark.db
class TestIngestDocument:
    """对着真实 MySQL 跑。样本用小 PDF，避免每次都解析 244 页年报。"""

    def test_ingest_writes_document_and_blocks(self, db_session, sample_pdf, company_id) -> None:
        spec = DocumentSpec(
            company_code=TEST_COMPANY_CODE,
            doc_type="annual_report",
            fiscal_year=2025,
            period="FY",
            lang="zh",
            path=sample_pdf,
        )
        result = ingest_document(db_session, spec, company_id=company_id)
        assert result.created is True
        assert result.block_count == 3

        parsed = parse_pdf(sample_pdf)
        from app.models.document import DocumentBlock
        from sqlalchemy import select

        stored = list(
            db_session.execute(
                select(DocumentBlock)
                .where(DocumentBlock.document_id == result.document_id)
                .order_by(DocumentBlock.page_no, DocumentBlock.block_index)
            ).scalars()
        )
        assert [b.block_id for b in stored] == [b.block_id(spec.doc_code) for b in parsed.blocks]
        assert [b.raw_text for b in stored] == [b.raw_text for b in parsed.blocks]

    def test_ingest_is_idempotent(self, db_session, sample_pdf, company_id) -> None:
        spec = DocumentSpec(
            company_code=TEST_COMPANY_CODE,
            doc_type="annual_report",
            fiscal_year=2024,
            period="FY",
            lang="zh",
            path=sample_pdf,
        )
        first = ingest_document(db_session, spec, company_id=company_id)
        second = ingest_document(db_session, spec, company_id=company_id)
        assert second.created is False
        assert second.document_id == first.document_id

        from app.models.document import DocumentBlock
        from sqlalchemy import func, select

        total = db_session.execute(
            select(func.count()).select_from(DocumentBlock)
            .where(DocumentBlock.document_id == first.document_id)
        ).scalar_one()
        assert total == first.block_count

    def test_ingest_sets_parse_status(self, db_session, sample_pdf, company_id) -> None:
        from app.models.document import Document, PARSE_SUCCEEDED

        spec = DocumentSpec(
            company_code=TEST_COMPANY_CODE,
            doc_type="annual_report",
            fiscal_year=2023,
            period="FY",
            lang="zh",
            path=sample_pdf,
        )
        result = ingest_document(db_session, spec, company_id=company_id)
        doc = db_session.get(Document, result.document_id)
        assert doc is not None
        assert doc.parse_status == PARSE_SUCCEEDED
        assert doc.parse_version
        assert doc.parsed_at is not None
        assert doc.page_count == 3

    def test_blocks_carry_normalized_text(self, db_session, sample_pdf, company_id) -> None:
        from app.models.document import DocumentBlock
        from sqlalchemy import select

        spec = DocumentSpec(
            company_code=TEST_COMPANY_CODE,
            doc_type="annual_report",
            fiscal_year=2022,
            period="FY",
            lang="zh",
            path=sample_pdf,
        )
        result = ingest_document(db_session, spec, company_id=company_id)
        blocks = list(
            db_session.execute(
                select(DocumentBlock).where(DocumentBlock.document_id == result.document_id)
            ).scalars()
        )
        assert all(b.normalized_text for b in blocks)
        assert all(b.raw_text is not None for b in blocks)
