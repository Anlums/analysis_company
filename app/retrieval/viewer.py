"""块序列查看器。

开发期工具，不参与覆盖率统计（见 pyproject.toml 的 coverage omit）。

用法：
    uv run python -m app.retrieval.viewer docs
    uv run python -m app.retrieval.viewer blocks CN_600963_2025_ANNUAL --page 24
    uv run python -m app.retrieval.viewer search 研发投入 --limit 10
    uv run python -m app.retrieval.viewer show CN_600963_2025_ANNUAL:24:1
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document, DocumentBlock


def _ensure_utf8() -> None:
    """Windows 终端默认 GBK，中文块内容会乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _width(text: str) -> int:
    """终端显示宽度。CJK 是全角，占两列，按字符数对齐会错位。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - _width(text))


def _document_id(session: Session, doc_code: str) -> int:
    doc_id = session.execute(
        select(Document.id).where(Document.doc_code == doc_code)
    ).scalar_one_or_none()
    if doc_id is None:
        codes = session.execute(select(Document.doc_code)).scalars().all()
        raise SystemExit(f"没有文档 {doc_code!r}。可选：{', '.join(codes)}")
    return doc_id


def _print_block(block: DocumentBlock, width: int = 100) -> None:
    text = (block.raw_text or "").replace("\n", " ⏎ ")
    if len(text) > width:
        text = text[:width] + "…"
    flag = " [识别]" if block.is_ocr else ""
    print(f"  {block.block_id:34s} p{block.page_no:<4} #{block.block_index:<3}{flag} {text}")


def cmd_docs(session: Session, _args: argparse.Namespace) -> None:
    rows = session.execute(
        select(
            Document.doc_code,
            Document.doc_type,
            Document.fiscal_year,
            Document.period,
            Document.lang,
            Document.page_count,
            func.count(DocumentBlock.id),
        )
        .join(DocumentBlock, DocumentBlock.document_id == Document.id, isouter=True)
        .group_by(Document.id)
        .order_by(Document.doc_code)
    ).all()

    cols = (("文档标识", 26), ("类型", 20), ("年度", 6), ("期", 4), ("语", 4), ("页", 6), ("块", 7))
    print("".join(_pad(name, w) for name, w in cols))
    print("-" * sum(w for _, w in cols))
    for code, dtype, year, period, lang, pages, blocks in rows:
        cells = (
            (code, 26), (dtype or "", 20), (str(year or ""), 6),
            (period or "", 4), (lang or "", 4), (str(pages or 0), 6), (str(blocks), 7),
        )
        print("".join(_pad(value, w) for value, w in cells))
    print(f"\n共 {len(rows)} 份文档，{sum(r[6] for r in rows)} 个块")


def cmd_blocks(session: Session, args: argparse.Namespace) -> None:
    doc_id = _document_id(session, args.doc_code)
    stmt = select(DocumentBlock).where(DocumentBlock.document_id == doc_id)

    if args.block_id:
        target = session.execute(
            select(DocumentBlock).where(DocumentBlock.block_id == args.block_id)
        ).scalar_one_or_none()
        if target is None:
            raise SystemExit(f"没有块 {args.block_id!r}")
        stmt = stmt.where(
            DocumentBlock.page_no.between(target.page_no - args.context,
                                          target.page_no + args.context)
            if args.context else
            DocumentBlock.page_no == target.page_no
        )
    elif args.page:
        stmt = stmt.where(DocumentBlock.page_no == args.page)

    stmt = stmt.order_by(DocumentBlock.page_no, DocumentBlock.block_index).limit(args.limit)
    blocks = list(session.execute(stmt).scalars())
    if not blocks:
        print("没有匹配的块")
        return

    last_page = None
    for block in blocks:
        if block.page_no != last_page:
            print(f"\n--- 第 {block.page_no} 页 ---")
            last_page = block.page_no
        _print_block(block, args.width)
    print(f"\n共显示 {len(blocks)} 个块")


def cmd_search(session: Session, args: argparse.Namespace) -> None:
    # 用归一化文本匹配：全角半角、连续空白已被折平，用户按直觉输入即可命中
    pattern = f"%{args.keyword}%"
    stmt = select(DocumentBlock).join(
        Document, Document.id == DocumentBlock.document_id
    ).where(
        or_(DocumentBlock.normalized_text.like(pattern), DocumentBlock.raw_text.like(pattern))
    )
    if args.doc_code:
        stmt = stmt.where(Document.doc_code == args.doc_code)
    blocks = list(
        session.execute(
            stmt.order_by(DocumentBlock.document_id, DocumentBlock.page_no,
                          DocumentBlock.block_index).limit(args.limit)
        ).scalars()
    )
    if not blocks:
        print(f"没有命中 {args.keyword!r} 的块")
        return
    doc_codes = {
        d.id: d.doc_code
        for d in session.execute(
            select(Document).where(Document.id.in_({b.document_id for b in blocks}))
        ).scalars()
    }
    for block in blocks:
        text = (block.raw_text or "").replace("\n", " ⏎ ")
        if len(text) > args.width:
            text = text[:args.width] + "…"
        print(f"  {doc_codes[block.document_id]:<24} {block.block_id:34s} {text}")
    print(f"\n命中 {len(blocks)} 个块（上限 {args.limit}）")


def cmd_show(session: Session, args: argparse.Namespace) -> None:
    block = session.execute(
        select(DocumentBlock).where(DocumentBlock.block_id == args.block_id)
    ).scalar_one_or_none()
    if block is None:
        raise SystemExit(f"没有块 {args.block_id!r}")

    doc = session.get(Document, block.document_id)
    print(f"块标识      {block.block_id}")
    print(f"所属文档    {doc.doc_code if doc else '?'}  （{doc.file_name if doc else ''}）")
    print(f"位置        第 {block.page_no} 页 第 {block.block_index} 块")
    print(f"类型        {block.block_type}   识别来源 {'是' if block.is_ocr else '否'}")
    print(f"坐标框      {block.bbox}")
    print(f"\n原文：\n{block.raw_text}")
    print(f"\n归一化文本：\n{block.normalized_text}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viewer", description="块序列查看器")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("docs", help="列出所有文档及其块数").set_defaults(func=cmd_docs)

    p_blocks = sub.add_parser("blocks", help="按文档浏览块")
    p_blocks.add_argument("doc_code")
    p_blocks.add_argument("--page", type=int, help="只看某一页")
    p_blocks.add_argument("--block-id", help="以某个块为中心显示上下文")
    p_blocks.add_argument("--context", type=int, default=1, help="上下文页数，默认 1")
    p_blocks.add_argument("--limit", type=int, default=200)
    p_blocks.add_argument("--width", type=int, default=100, help="每条截断宽度")
    p_blocks.set_defaults(func=cmd_blocks)

    p_search = sub.add_parser("search", help="按关键词搜块")
    p_search.add_argument("keyword")
    p_search.add_argument("--doc", dest="doc_code", help="限定在某份文档内")
    p_search.add_argument("--limit", type=int, default=30)
    p_search.add_argument("--width", type=int, default=100)
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="看单个块的完整内容")
    p_show.add_argument("block_id")
    p_show.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> None:
    _ensure_utf8()
    args = build_parser().parse_args(argv)
    with SessionLocal() as session:
        args.func(session, args)


if __name__ == "__main__":
    main()
