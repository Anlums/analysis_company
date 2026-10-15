"""公司域：公司主数据与别名（技术架构文档 9.1 表 18）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Company(Base):
    """公司主数据。

    company_code 是人工可读的业务标识（用于 doc_code 拼装与排查），但跨域引用一律走
    数值代理键 company.id —— 别把 "000663" 这类字符串写进下游的 company_id 列，
    MySQL 会静默转成 663。
    """

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_code: Mapped[str] = mapped_column(String(64), unique=True)
    name_cn: Mapped[str | None] = mapped_column(String(255))
    name_en: Mapped[str | None] = mapped_column(String(255))
    stock_code: Mapped[str | None] = mapped_column(String(32))
    market: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(16))
    # 行业包代码。面向全行业，林业包记 FOR，非林业公司留空。
    industry_code: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    aliases: Mapped[list["CompanyAlias"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanyAlias(Base):
    """公司别名：简称、外文名、曾用名、报告中的简称写法。

    混合检索的元数据过滤与事实对齐的同义词扩展都要查这张表。
    """

    __tablename__ = "company_alias"
    __table_args__ = (
        UniqueConstraint("company_id", "alias", name="uq_company_alias"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("company.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(255))
    lang: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="aliases")
