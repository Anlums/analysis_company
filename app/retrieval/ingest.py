"""文档入库：把解析结果落进 document / document_block。

技术架构文档 8.1 流水线的落库环节。批量插入而非逐条 flush——单份年报就有近三千个块，
逐条写会把入库时间从秒级拖到分钟级。11 份文档预计三万余块。

doc_code 由 (公司标识, 会计年度, 文档类型) 拼成，且必须与证据锚点的解析规则互逆。
这条约束在 build_doc_code 里一次满足，调用方无法绕过——库建好之后 doc_code 再改，
已落库文档的证据链会全部失效，而且不报任何错。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pypdf
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import (
    DOC_ANNUAL_REPORT,
    DOC_AUDIT_REPORT,
    DOC_ESG_REPORT,
    DOC_INTERIM_REPORT,
    PARSE_SUCCEEDED,
    Document,
    DocumentBlock,
)
from app.retrieval.parser import parse_pdf
from app.schemas.common import check_doc_code

# 解析器版本。写入 document.parse_version，用于分辨「哪些文档是旧解析器产出、需重解析」。
#
# 必须带上 pypdf 版本，不能只写自己的版本号：实测 pypdf 6.0 与 6.20 解析同一份年报，
# 块的**数量与标识完全相同**（2865 个，逐页一致），但 79.9% 的块**文本不同**——断行与
# 空格插入算法变了。锚点照旧解析成功、照旧打得开，指向的内容却已经变了，且不报任何错。
# 把库版本编进 parse_version 是唯一能让这种漂移可见的办法。
PARSE_VERSION = f"v0.1-pypdf{pypdf.__version__}-layout"

# 文档类型 → 编码后缀。后缀进 doc_code，故必须 ASCII 且短。
DOC_TYPE_SUFFIX: dict[str, str] = {
    DOC_ANNUAL_REPORT: "ANNUAL",
    DOC_INTERIM_REPORT: "H1",
    DOC_ESG_REPORT: "ESG",
    DOC_AUDIT_REPORT: "AUDIT",
}

MIN_YEAR = 1990
MAX_YEAR = 2100


def build_doc_code(company_code: str, fiscal_year: int, doc_type: str) -> str:
    """拼装文档标识。

    结果同时要满足两头：锚点解析侧只接受 ASCII 字母数字下划线连字符；人工排查
    证据链时要能一眼读懂是哪家公司哪一年。故用「公司标识_年度_类型」。
    """
    suffix = DOC_TYPE_SUFFIX.get(doc_type)
    if suffix is None:
        raise ValueError(
            f"未知文档类型 {doc_type!r}，可选：{sorted(DOC_TYPE_SUFFIX)}"
        )
    if not MIN_YEAR <= fiscal_year <= MAX_YEAR:
        raise ValueError(f"会计年度 {fiscal_year} 超出 {MIN_YEAR}–{MAX_YEAR}")
    return f"{check_doc_code(company_code)}_{fiscal_year}_{suffix}"


@dataclass(frozen=True)
class DocumentSpec:
    company_code: str
    doc_type: str
    fiscal_year: int
    period: str
    lang: str
    path: Path

    @property
    def doc_code(self) -> str:
        return build_doc_code(self.company_code, self.fiscal_year, self.doc_type)


@dataclass(frozen=True)
class IngestResult:
    document_id: int
    doc_code: str
    created: bool
    replaced: bool
    page_count: int
    block_count: int


def file_digest(path: Path) -> str:
    """文件内容哈希，用于判定是否已解析过（11.3 解析结果缓存）。"""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _block_rows(document_id: int, spec: DocumentSpec, parsed) -> list[dict]:
    return [
        {
            "block_id": block.block_id(spec.doc_code),
            "document_id": document_id,
            "page_no": block.page_no,
            "block_index": block.block_index,
            "block_type": block.block_type,
            "raw_text": block.raw_text,
            "normalized_text": block.normalized_text,
            "is_ocr": block.is_ocr,
            "ocr_confidence": block.ocr_confidence,
        }
        for block in parsed.blocks
    ]


def ingest_document(
    session: Session,
    spec: DocumentSpec,
    *,
    company_id: int,
    parse_version: str = PARSE_VERSION,
) -> IngestResult:
    """解析并落库单份文档。幂等：文件未变则不重复写。

    文件内容变了（哈希不同）则删旧块重建。旧块上的证据记录会因此悬空——这是对的：
    源文件换了，基于旧块的结论本就不该继续成立。调用方据此决定是否重跑分析。
    """
    if not spec.path.exists():
        raise FileNotFoundError(f"源文件不存在：{spec.path}")

    digest = file_digest(spec.path)
    existing = session.execute(
        select(Document).where(Document.doc_code == spec.doc_code)
    ).scalar_one_or_none()

    if existing is not None and existing.file_hash == digest:
        count = session.execute(
            select(func.count()).select_from(DocumentBlock)
            .where(DocumentBlock.document_id == existing.id)
        ).scalar_one()
        return IngestResult(
            document_id=existing.id,
            doc_code=spec.doc_code,
            created=False,
            replaced=False,
            page_count=existing.page_count or 0,
            block_count=count,
        )

    replaced = existing is not None
    if existing is not None:
        # document_block 有 ON DELETE CASCADE，删父行即清块
        session.execute(delete(Document).where(Document.id == existing.id))
        session.flush()

    parsed = parse_pdf(spec.path)
    document = Document(
        doc_code=spec.doc_code,
        company_id=company_id,
        doc_type=spec.doc_type,
        fiscal_year=spec.fiscal_year,
        period=spec.period,
        lang=spec.lang,
        file_name=spec.path.name,
        file_path=str(spec.path),
        file_hash=digest,
        file_size=spec.path.stat().st_size,
        page_count=parsed.page_count,
        parse_status=PARSE_SUCCEEDED,
        parse_version=parse_version,
        parsed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(document)
    session.flush()

    rows = _block_rows(document.id, spec, parsed)
    if rows:
        session.execute(insert(DocumentBlock), rows)
    session.commit()

    return IngestResult(
        document_id=document.id,
        doc_code=spec.doc_code,
        created=not replaced,
        replaced=replaced,
        page_count=parsed.page_count,
        block_count=len(rows),
    )


# ---------------------------------------------------------------- 首批入库计划

CN_CODE = "CN_600963"
SE_CODE = "SE_HOLMEN"

CN_DIR_NAME = "岳阳林纸股份有限公司"
SE_DIR_NAME = "Holmen"


def build_plan() -> tuple[DocumentSpec, ...]:
    """首批入库的 11 份文档。

    「年报摘要」六份刻意排除：它是与主报告内容重复的节本，且现有 doc_type 枚举
    （annual / interim / esg / audit）里没有对应类别，为它新开一类属于契约变更，
    不该顺手做。

    文件路径逐个写死而非 glob：选样是要能一眼看清、可复现的，glob 会在数据集
    增删文件时静默改变范围。
    """
    if not settings.dataset_dir:
        raise RuntimeError("APP_DATASET_DIR 未配置，见 .env")
    base = Path(settings.dataset_dir)
    if not base.is_dir():
        raise RuntimeError(f"数据集目录不存在：{base}")

    cn_dir = base / "国内" / CN_DIR_NAME
    se_dir = base / "国外" / SE_DIR_NAME

    def cn_annual(year: int) -> Path:
        return cn_dir / f"岳阳林纸：岳阳林纸股份有限公司{year}年年度报告.pdf"

    def cn_interim(year: int) -> Path:
        return cn_dir / f"岳阳林纸：岳阳林纸股份有限公司{year}年半年度报告.pdf"

    def holmen(year: int) -> Path:
        return se_dir / f"Annual Report {year} including sustainability report.pdf"

    annual_years = (2021, 2022, 2023, 2024, 2025)

    return (
        *(
            DocumentSpec(CN_CODE, DOC_ANNUAL_REPORT, y, "FY", "zh", cn_annual(y))
            for y in annual_years
        ),
        DocumentSpec(CN_CODE, DOC_INTERIM_REPORT, 2026, "H1", "zh", cn_interim(2026)),
        *(
            DocumentSpec(SE_CODE, DOC_ANNUAL_REPORT, y, "FY", "en", holmen(y))
            for y in annual_years
        ),
    )


def main() -> None:
    from app.core.database import SessionLocal
    from app.models.company import Company
    from app.seed.companies import seed_companies

    plan = build_plan()
    print(f"计划入库 {len(plan)} 份文档\n")

    with SessionLocal() as session:
        seed_companies(session)
        ids = dict(session.execute(select(Company.company_code, Company.id)).all())

        total_blocks = 0
        for i, spec in enumerate(plan, start=1):
            if not spec.path.exists():
                print(f"[{i}/{len(plan)}] 跳过（文件不存在）{spec.path.name}")
                continue
            result = ingest_document(session, spec, company_id=ids[spec.company_code])
            total_blocks += result.block_count
            state = "重建" if result.replaced else ("新建" if result.created else "已存在")
            print(
                f"[{i}/{len(plan)}] {state}  {result.doc_code}  "
                f"{result.page_count} 页 / {result.block_count} 块"
            )

    print(f"\n合计 {total_blocks} 个块")


if __name__ == "__main__":
    main()
