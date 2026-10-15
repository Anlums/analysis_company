"""共享测试夹具。

用于测试的文档标识与锚点取自真实数据（岳阳林纸 2025 年报），避免用 "DOC1" 这类
占位串掩盖真实编码规则下的问题。
"""

from pathlib import Path

import pytest

# 真实公司：岳阳林纸，上交所 600963
REAL_COMPANY_CODE = "CN_600963"
REAL_DOC_CODE = "CN_600963_2025_ANNUAL"
REAL_BLOCK_ID = f"{REAL_DOC_CODE}:42:3"
REAL_CELL_REF = "表1R3C2"

# 真实年报所在位置。在别处跑测试（CI、新同事机器）时该路径不存在，相关用例自动跳过。
REAL_REPORT = Path(
    r"D:\OneDrive\图片\Desktop\分析公司项目\数据来源\国内\岳阳林纸股份有限公司"
    r"\岳阳林纸：岳阳林纸股份有限公司2025年年度报告.pdf"
)


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(text: str) -> bytes:
    """把文本写成内容流。

    空行必须体现为真实的纵向留白（只推进游标不绘制），不能靠绘制空字符串——
    版面分析看的是坐标，看不到「画了个空串」，段落间距会被当成不存在。
    """
    if not text.strip():
        return b""
    parts = ["BT", "/F1 12 Tf", "14 TL", "72 720 Td"]
    for line in text.split("\n"):
        if line.strip():
            parts.append(f"({_escape_pdf_text(line)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def build_pdf(page_texts: list[str]) -> bytes:
    """按原始 PDF 语法拼一个最小可用文档，空串表示空白页。

    不引第三方 PDF 生成库：这里要的只是「页数、页序、空白页」可控，手写反而更稳，
    也不会因为生成库升级而让解析器的测试基线漂移。
    """
    n = len(page_texts)
    font_num = 3 + 2 * n
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n))

    objs: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        font_num: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(page_texts):
        page_num = 3 + 2 * i
        content_num = page_num + 1
        objs[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_num} 0 R "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> >>"
        ).encode("latin-1")
        stream = _content_stream(text)
        objs[content_num] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode("latin-1") + objs[num] + b"\nendobj\n"

    total = max(objs) + 1
    xref_at = len(out)
    out += f"xref\n0 {total}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for num in range(1, total):
        out += f"{offsets[num]:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {total} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


@pytest.fixture
def doc_code() -> str:
    return REAL_DOC_CODE


@pytest.fixture
def block_id() -> str:
    return REAL_BLOCK_ID


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """三页受控 PDF：第 1 页两个段落、第 2 页空白、第 3 页一个段落。

    空白页是刻意放的——空白页不产出块这条规则，在真实的年报里也常被触发
    （章节之间的隔页、扫描件里的空白页）。
    """
    path = tmp_path_factory.mktemp("pdf") / "sample.pdf"
    path.write_bytes(
        build_pdf(
            [
                "Accounts receivable 1,234,567.89\n\nInventory 5,059,574,633.52",
                "",
                "Cash 1,049,237,957.50",
            ]
        )
    )
    return path


@pytest.fixture(scope="session")
def real_annual_report() -> Path:
    if not REAL_REPORT.exists():
        pytest.skip(f"真实年报不在本机：{REAL_REPORT}")
    return REAL_REPORT


@pytest.fixture
def db_session():
    """带事务隔离的数据库会话。

    整个测试跑在一个最外层事务里，结束时回滚，所以测试数据不会残留在库里。
    入库逻辑自己会 commit（它要服务真实调用），配合 create_savepoint 让那些
    commit 只落到 savepoint 上，外层回滚依然能收干净。
    """
    from sqlalchemy.orm import Session

    from app.core.database import engine

    try:
        connection = engine.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MySQL 不可用，跳过数据库测试：{exc}")

    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def company_id(db_session) -> int:
    """在测试事务内建一家公司，返回其主键。"""
    from sqlalchemy import select

    from app.models.company import Company

    existing = db_session.execute(
        select(Company.id).where(Company.company_code == REAL_COMPANY_CODE)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    company = Company(
        company_code=REAL_COMPANY_CODE,
        name_cn="测试用公司",
        country="CN",
        industry_code="FOR",
    )
    db_session.add(company)
    db_session.flush()
    return company.id
