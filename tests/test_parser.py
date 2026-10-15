"""块序列生成测试。

解析器是「结论可回指原文」的源头，它唯一不可退让的性质是**确定性**：
同一份 PDF 无论解析多少次、无论谁解析，块标识序列必须逐字相同。否则任何一次
解析器升级都会让既有结论的证据链失效——而且失效是静默的，锚点只是查不到块。

这里把解析拆成两层分别测：
  split_page_blocks  纯函数，页文本 → 块文本，可穷举边界情况
  parse_pdf          读取 PDF 并按页装配，用一个受控的小 PDF 验证装配规则
"""

import pytest

from app.retrieval.parser import ParsedBlock, ParsedDocument, parse_pdf, split_page_blocks
from app.schemas.common import make_block_id


class TestSplitPageBlocks:
    """页文本切块。切法必须只依赖输入内容，不含任何随机量。"""

    def test_empty_page_yields_no_blocks(self) -> None:
        assert split_page_blocks("") == ()

    @pytest.mark.parametrize("blank", ["   ", "\n", "\n\n\n", " \t \n \t "])
    def test_whitespace_only_page_yields_no_blocks(self, blank: str) -> None:
        """空白页不能产出空文本块——空块过不了下游的证据校验，只会污染锚点空间。"""
        assert split_page_blocks(blank) == ()

    def test_single_paragraph(self) -> None:
        assert split_page_blocks("应收账款 1,234,567.89") == ("应收账款 1,234,567.89",)

    def test_blank_line_separates_blocks(self) -> None:
        text = "第一段\n\n第二段"
        assert split_page_blocks(text) == ("第一段", "第二段")

    def test_multiple_blank_lines_count_as_one_separator(self) -> None:
        text = "第一段\n\n\n\n第二段"
        assert split_page_blocks(text) == ("第一段", "第二段")

    def test_single_newline_does_not_split(self) -> None:
        """同一段落内的换行不切块，否则一段话会被打碎成没有上下文的多块。"""
        assert split_page_blocks("上行\n下行") == ("上行\n下行",)

    def test_leading_and_trailing_whitespace_trimmed(self) -> None:
        assert split_page_blocks("  \n\n  内容  \n\n  ") == ("内容",)

    def test_order_is_preserved(self) -> None:
        text = "\n\n".join(f"第{i}段" for i in range(5))
        assert split_page_blocks(text) == tuple(f"第{i}段" for i in range(5))

    def test_is_deterministic(self) -> None:
        text = "甲\n\n乙\n\n丙"
        assert split_page_blocks(text) == split_page_blocks(text)

    def test_does_not_mutate_input(self) -> None:
        """不可变：切块是纯函数，输入字符串不该被改动。"""
        text = "  甲  \n\n  乙  "
        original = str(text)
        split_page_blocks(text)
        assert text == original

    def test_rare_cjk_chars_survive(self) -> None:
        """年报里有生僻字，切块不能吞字符。"""
        text = "𠮷野家\n\n甪直镇 龘"
        assert split_page_blocks(text) == ("𠮷野家", "甪直镇 龘")


class TestParsedBlock:
    def test_block_id_matches_make_block_id(self, doc_code: str) -> None:
        block = ParsedBlock(
            page_no=42, block_index=3, block_type="text", raw_text="x", normalized_text="x"
        )
        assert block.block_id(doc_code) == make_block_id(doc_code, 42, 3)

    def test_block_is_frozen(self) -> None:
        """块一旦产出就不可变——它同时是解析结果和锚点的锚定对象。"""
        block = ParsedBlock(
            page_no=1, block_index=0, block_type="text", raw_text="x", normalized_text="x"
        )
        with pytest.raises(Exception):
            block.page_no = 2  # type: ignore[misc]


class TestParsePdfDeterminism:
    """确定性：这是解析器唯一不可退让的性质。"""

    def test_repeated_parse_gives_identical_block_ids(self, sample_pdf) -> None:
        first = parse_pdf(sample_pdf)
        second = parse_pdf(sample_pdf)
        assert [b.block_id("DOC") for b in first.blocks] == [
            b.block_id("DOC") for b in second.blocks
        ]

    def test_repeated_parse_gives_identical_text(self, sample_pdf) -> None:
        first = parse_pdf(sample_pdf)
        second = parse_pdf(sample_pdf)
        assert [b.raw_text for b in first.blocks] == [b.raw_text for b in second.blocks]

    def test_page_count_matches_document(self, sample_pdf) -> None:
        doc = parse_pdf(sample_pdf)
        assert doc.page_count == 3

    def test_block_ids_unique_across_document(self, sample_pdf) -> None:
        doc = parse_pdf(sample_pdf)
        ids = [b.block_id("DOC") for b in doc.blocks]
        assert len(ids) == len(set(ids))

    def test_page_numbers_are_one_based(self, sample_pdf) -> None:
        """页号从 1 起：锚点里的页号要直接对上 PDF 阅读器显示的页码。"""
        doc = parse_pdf(sample_pdf)
        assert min(b.page_no for b in doc.blocks) == 1

    def test_block_index_is_per_page_and_zero_based(self, sample_pdf) -> None:
        doc = parse_pdf(sample_pdf)
        by_page: dict[int, list[int]] = {}
        for b in doc.blocks:
            by_page.setdefault(b.page_no, []).append(b.block_index)
        for page_no, indices in by_page.items():
            assert indices == sorted(indices), f"第 {page_no} 页块序号未按版面顺序"
            assert min(indices) == 0, f"第 {page_no} 页块序号未从 0 起"

    def test_no_empty_text_blocks(self, sample_pdf) -> None:
        doc = parse_pdf(sample_pdf)
        assert all(b.raw_text.strip() for b in doc.blocks)

    def test_target_page_produces_no_blocks(self, sample_pdf) -> None:
        """第 2 页是空白页，不该产出任何块。"""
        doc = parse_pdf(sample_pdf)
        assert [b for b in doc.blocks if b.page_no == 2] == []

    def test_blocks_point_back_to_source_page(self, sample_pdf) -> None:
        """每块都要能定位回原文页——这是证据锚点成立的前提。"""
        doc = parse_pdf(sample_pdf)
        page1 = [b for b in doc.blocks if b.page_no == 1]
        assert any("Accounts receivable" in b.raw_text for b in page1)

    def test_page_three_content_lands_on_page_three(self, sample_pdf) -> None:
        doc = parse_pdf(sample_pdf)
        assert doc.blocks[-1].page_no == 3
        assert "Cash" in doc.blocks[-1].raw_text

    def test_paragraphs_become_separate_blocks(self, sample_pdf) -> None:
        doc = parse_pdf(sample_pdf)
        page1 = [b for b in doc.blocks if b.page_no == 1]
        assert len(page1) == 2
        assert page1[0].block_index == 0
        assert page1[1].block_index == 1


@pytest.mark.slow
class TestParseRealAnnualReport:
    """对着真实的 244 页年报跑一次，确认解析器在真实排版上不崩。

    标记 slow：单次解析约 15 秒，三个用例合计约 60 秒。文件不在本机时自动跳过，
    所以 CI 上不会因为这个标记而少跑东西。用 `-m "not slow"` 可跳过。
    """

    def test_real_report_parses(self, real_annual_report) -> None:
        doc = parse_pdf(real_annual_report)
        assert doc.page_count == 244
        assert len(doc.blocks) > 1000, "真实年报应产出上千个块"

    def test_real_report_block_ids_are_stable(self, real_annual_report) -> None:
        first = parse_pdf(real_annual_report)
        second = parse_pdf(real_annual_report)
        assert [b.block_id("X") for b in first.blocks] == [
            b.block_id("X") for b in second.blocks
        ]

    def test_real_report_page_numbers_within_range(self, real_annual_report) -> None:
        doc = parse_pdf(real_annual_report)
        assert all(1 <= b.page_no <= doc.page_count for b in doc.blocks)
