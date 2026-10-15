"""共享测试夹具。

用于测试的文档标识与锚点取自真实数据（岳阳林纸 2025 年报），避免用 "DOC1" 这类
占位串掩盖真实编码规则下的问题。
"""

import pytest

# 真实公司：岳阳林纸，上交所 600963
REAL_DOC_CODE = "CN_600963_2025_ANNUAL"
REAL_BLOCK_ID = f"{REAL_DOC_CODE}:42:3"
REAL_CELL_REF = "表1R3C2"


@pytest.fixture
def doc_code() -> str:
    return REAL_DOC_CODE


@pytest.fixture
def block_id() -> str:
    return REAL_BLOCK_ID
