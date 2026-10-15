"""首批入库的两家公司。

范围刻意收窄到「一家国内 + 一家国外」：先跑通链路再铺开。选样理由：

岳阳林纸（国内）——已有逐字段的可提取性分析基础，五份年报加一份半年报可覆盖
同比与环比所需的多个报告期。

Holmen（国外）——五份年报均含可持续报告，实测 140 页内含 Scope 1/2/3、能源、
水、废弃物、第三方鉴证与 FSC 认证。国内年报里这些环境量化数据一处都没有，
选它是为了让 ESG 对比智能体的取数链路有真实数据可跑。

company_code 会被拼进 doc_code，而 doc_code 是证据锚点的第一段、一旦落库就不能改
（改了历史结论的证据链即断），所以编码规则要一次定死：国别_标识。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models.company import Company, CompanyAlias

# 国别前缀，与 company.country 一致
COUNTRY_CN = "CN"
COUNTRY_SE = "SE"


@dataclass(frozen=True)
class CompanySeed:
    company_code: str
    name_cn: str
    name_en: str
    stock_code: str | None
    market: str | None
    country: str
    industry_code: str | None
    aliases: tuple[tuple[str, str], ...] = ()  # (别名, 语种)


COMPANIES: tuple[CompanySeed, ...] = (
    CompanySeed(
        company_code="CN_600963",
        name_cn="岳阳林纸股份有限公司",
        name_en="YUEYANG FOREST & PAPER CO.,LTD.",
        stock_code="600963",
        market="SSE",
        country=COUNTRY_CN,
        industry_code="FOR",
        aliases=(
            ("岳阳林纸", "zh"),
            ("YYLZ", "en"),
            ("泰格林纸", "zh"),
        ),
    ),
    CompanySeed(
        company_code="SE_HOLMEN",
        name_cn="霍尔门",
        name_en="Holmen AB",
        stock_code="HOLM-B",
        market="OMXSTO",
        country=COUNTRY_SE,
        industry_code="FOR",
        aliases=(
            ("Holmen", "en"),
            ("Holmen AB (publ)", "en"),
        ),
    ),
)

# 可被种子覆盖的列。company_code 是业务主键，不入更新列表——它被拼进 doc_code，
# 改了会让已落库文档的锚点全部失效。
_COMPANY_UPDATABLE = (
    "name_cn",
    "name_en",
    "stock_code",
    "market",
    "country",
    "industry_code",
)


def seed_companies(session: Session) -> int:
    """把公司主数据与别名 upsert 进库，返回公司数。"""
    stmt = mysql_insert(Company).values(
        [
            {
                "company_code": c.company_code,
                "name_cn": c.name_cn,
                "name_en": c.name_en,
                "stock_code": c.stock_code,
                "market": c.market,
                "country": c.country,
                "industry_code": c.industry_code,
            }
            for c in COMPANIES
        ]
    )
    session.execute(
        stmt.on_duplicate_key_update(
            **{col: stmt.inserted[col] for col in _COMPANY_UPDATABLE}
        )
    )
    session.flush()

    ids = dict(session.execute(select(Company.company_code, Company.id)).all())

    alias_rows = [
        {"company_id": ids[c.company_code], "alias": alias, "lang": lang}
        for c in COMPANIES
        for alias, lang in c.aliases
    ]
    if alias_rows:
        alias_stmt = mysql_insert(CompanyAlias).values(alias_rows)
        session.execute(
            alias_stmt.on_duplicate_key_update(lang=alias_stmt.inserted["lang"])
        )

    session.commit()
    return len(COMPANIES)


def main() -> None:
    from app.core.database import SessionLocal

    with SessionLocal() as session:
        count = seed_companies(session)
        total = session.execute(
            select(func.count()).select_from(Company)
        ).scalar_one()
        aliases = session.execute(
            select(func.count()).select_from(CompanyAlias)
        ).scalar_one()
        print(f"upsert {count} 家公司，company 现有 {total} 行，company_alias {aliases} 行")


if __name__ == "__main__":
    main()
