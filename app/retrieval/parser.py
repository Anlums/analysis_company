"""文档解析：PDF → 带稳定标识的块序列。

这是「结论可回指原文」的生成端。接口按技术架构文档 8.1 的流水线切分，但当前
只实现前段：文件读取 → 逐页取文本 → 块序列生成与标识分配。版面分析（区分正文／
标题／表格／图表）与 OCR 属于后续阶段，接入 PaddleOCR 与 Unstructured 时替换
`_extract_page_text` 即可，块标识的生成规则与下游全部不受影响。

确定性是唯一不可退让的性质：同一份文件无论解析多少次，块标识序列必须逐字相同。
因此本模块不含随机量、时间戳，也不依赖任何环境状态；块序号按版面顺序枚举，
页号按文档顺序从 1 起。
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.models.document import BLOCK_TEXT
from app.schemas.common import make_block_id

logger = logging.getLogger(__name__)

# 空行分段：一个或多个「只含空白的行」视为段间分隔。
# 只按单个换行切会把一句话打碎成没有上下文的多块，故必须要求成对换行。
_BLANK_LINE = re.compile(r"\n[ \t\r\f\v]*\n")
# 归一化时把任意连续空白折成单个空格，供检索匹配使用
_WHITESPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedBlock:
    """解析出的单个块。不可变——它同时是解析结果与证据锚点的锚定对象。"""

    page_no: int
    block_index: int
    block_type: str
    raw_text: str
    normalized_text: str
    bbox: dict | None = None
    is_ocr: bool = False
    ocr_confidence: float | None = None

    def block_id(self, doc_code: str) -> str:
        return make_block_id(doc_code, self.page_no, self.block_index)


@dataclass(frozen=True)
class ParsedDocument:
    page_count: int
    blocks: tuple[ParsedBlock, ...]
    # 抽取失败被跳过的页码。必须显式带出来：一页流损坏不该让整份文档一块都拿不到，
    # 但也不能静默跳过——那会让「文档解析成功」与「文档其实缺了好几页」长得一样。
    failed_pages: tuple[int, ...] = ()


def split_page_blocks(text: str) -> tuple[str, ...]:
    """把一页的文本切成块。

    纯函数：只依赖输入内容，不含随机量。空白页返回空元组——空块过不了下游的证据
    校验，产出它只会白白占用锚点空间。
    """
    if not text:
        return ()
    parts = _BLANK_LINE.split(text)
    return tuple(stripped for part in parts if (stripped := part.strip()))


def normalize_text(text: str) -> str:
    """生成供检索匹配的归一化文本。

    原文一字不动（证据比对要求逐字一致），归一化只用于匹配：统一全角半角、合并
    连续空白。证券代码、科目名这类精确匹配信号在两种形态下都能命中，但把全角
    数字与半角数字对齐能显著提高召回。
    """
    return _WHITESPACE_RUN.sub(" ", unicodedata.normalize("NFKC", text)).strip()


def _extract_page_text(page: object) -> str:
    """取单页文本。

    必须用 layout 模式，不能用默认的 plain。plain 把版面压成一维行流，空行全部丢失
    （实测 244 页年报中 "\\n\\n" 出现 0 次），段落边界无从恢复，切块会退化成「一页一块」；
    它还会把标签拦腰截断（"公司注册地址的历史变更情" 与 "况" 分成两行）。
    layout 模式保留缩进与空行，实测同一页空行数从 0 恢复到 14。

    接 PaddleOCR / Unstructured 时替换这里，其余流程不变。
    """
    text = page.extract_text(extraction_mode="layout")  # type: ignore[attr-defined]
    return text or ""


def parse_pdf(path: Path | str) -> ParsedDocument:
    """解析 PDF 为块序列。

    不做语种判定、不做版面分类，只做结构还原与位置记录（8.1：解析只做结构还原，
    不解释语义，以保证同一份文档无论被哪个任务调用结果完全一致）。

    逐页隔离：单页内容流损坏（截断、无法解码）只跳过该页并记入 failed_pages，
    不让整份文档失败。实测 244 页文档中只要有一页流损坏，不隔离的话一块都拿不到。
    """
    reader = PdfReader(str(path))
    blocks: list[ParsedBlock] = []
    failed_pages: list[int] = []

    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = _extract_page_text(page)
        except Exception as exc:  # noqa: BLE001  单页损坏不应拖垮整份文档
            logger.warning("第 %d 页抽取失败，已跳过：%s", page_no, exc)
            failed_pages.append(page_no)
            continue

        for block_index, raw in enumerate(split_page_blocks(text)):
            blocks.append(
                ParsedBlock(
                    page_no=page_no,
                    block_index=block_index,
                    block_type=BLOCK_TEXT,
                    raw_text=raw,
                    normalized_text=normalize_text(raw),
                )
            )

    return ParsedDocument(
        page_count=len(reader.pages),
        blocks=tuple(blocks),
        failed_pages=tuple(failed_pages),
    )
