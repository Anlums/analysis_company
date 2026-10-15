"""全局统一响应外壳，以及跨域共用的标识契约。

文档标识（doc_code）的字符集在这里定义一次。它同时被三处使用：document 表的主键列、
company_code 的拼装来源、以及证据锚点的第一段。三处各写一遍校验规则必然漂移，
一旦写入侧比解析侧宽松，就会出现「库里有这个文档，但它的锚点解析不出来」——
而且不报错，只是前端高亮和人工复核静默失效。
"""

import re
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

# 文档标识只允许 ASCII 字母数字、下划线、连字符。冒号是锚点分隔符、井号是单元格引用
# 分隔符，这两个字符出现会让锚点无法反解；点号常见于 A 股代码写法（600519.SH），
# 同样排除，以免 doc_code 用了它之后锚点链断裂。
DOC_CODE_PATTERN = r"[A-Za-z0-9_\-]+"
DOC_CODE_RE = re.compile(rf"^{DOC_CODE_PATTERN}$")

# 字段编码：类别前缀_指标缩写，全大写下划线分隔（《数据字段编码注册表》编码规则）
FIELD_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


def check_doc_code(value: str) -> str:
    """校验文档标识字符集，供 document / company / evidence 三处共用。"""
    if not DOC_CODE_RE.fullmatch(value):
        raise ValueError(
            f"文档标识 {value!r} 含非法字符，只允许 ASCII 字母数字、下划线、连字符"
            "（冒号与井号是锚点分隔符，点号见 A 股代码写法，均不可用）"
        )
    return value


def make_block_id(doc_code: str, page_no: int, block_index: int) -> str:
    """块标识的唯一构造入口。

    块标识必须由文档标识、页码与页内序号确定性生成（9.2），且要与证据锚点的解析
    规则严格互逆——分开写构造与解析两套逻辑，迟早会出现「库里存的块标识解析不出来」
    或「解析后与原文串不等」的情况，而且都不报错。
    """
    return f"{check_doc_code(doc_code)}:{page_no}:{block_index}"


class PageMeta(BaseModel):
    total: int
    page: int
    limit: int


class ApiResponse(BaseModel, Generic[T]):
    """全局统一响应外壳，所有接口的出参都包在这一层里。"""

    success: bool = True
    data: T | None = None
    error: str | None = None
    meta: PageMeta | None = None
