"""文档与数据库的一致性。

《数据字段编码注册表》是智能体间数据契约的基准，而 field_registry 是它的落库形态。
两者一旦漂移，「以文档为准」这条约定就名存实亡——而且漂移是静默的：库照常工作，
只是抽取的字段与文档对不上。

这个项目已经踩过两次：META_ 前缀在库里建了却没登记进文档的编码规则；单位写法
文档用「吨CO₂e」（下标 2）而库里是「吨CO2e」（ASCII）。两次都不是程序错误，
是文档与实现分头演进的结果，所以需要一条测试守着。

文档在仓库外（OneDrive 里），拿不到时整组跳过。
"""

import re
from pathlib import Path

import pytest

DOC_PATH = Path(
    r"D:\OneDrive\图片\Desktop\分析公司项目\数据字段编码注册表.docx"
)

FIELD_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]+")


@pytest.fixture(scope="module")
def registry_doc():
    if not DOC_PATH.exists():
        pytest.skip(f"注册表文档不在本机：{DOC_PATH}")
    from docx import Document

    return Document(DOC_PATH)


def _doc_field_rows(registry_doc) -> dict[str, list[str]]:
    """把文档各表里的字段行读成 {编码: [编码, 名称, 数据类型, 单位, 来源位置, 下游用途]}。"""
    rows: dict[str, list[str]] = {}
    for table in registry_doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if len(cells) != 6:
                continue
            if not FIELD_CODE_RE.fullmatch(cells[0]):
                continue  # 表头或说明行
            rows[cells[0]] = cells
    return rows


@pytest.mark.slow
class TestRegistryMatchesDatabase:
    def test_document_lists_every_registered_field(self, registry_doc, db_session) -> None:
        """文档与库的字段集合必须完全相同——多一个少一个都是契约破裂。"""
        from sqlalchemy import select

        from app.models.field import FieldRegistry

        doc_codes = set(_doc_field_rows(registry_doc))
        db_codes = set(db_session.execute(select(FieldRegistry.field_code)).scalars())

        assert doc_codes - db_codes == set(), "文档里有、库中没有的编码"
        assert db_codes - doc_codes == set(), "库里有、文档中未登记的编码"

    def test_field_attributes_match(self, registry_doc, db_session) -> None:
        """名称、单位、来源位置、下游用途必须逐字一致。

        单位用「—」表示定性条目，落库时为空值，比较前先归一。
        """
        from sqlalchemy import select

        from app.models.field import FieldRegistry

        doc_rows = _doc_field_rows(registry_doc)
        db_rows = {
            r.field_code: r
            for r in db_session.execute(select(FieldRegistry)).scalars()
        }

        mismatches: list[str] = []
        for code, cells in sorted(doc_rows.items()):
            row = db_rows.get(code)
            if row is None:
                continue
            _, name, _dtype, unit, source, usage = cells
            expected_unit = "" if unit == "—" else unit
            if name != row.name:
                mismatches.append(f"{code} 名称：文档={name!r} 库={row.name!r}")
            if expected_unit != (row.unit or ""):
                mismatches.append(f"{code} 单位：文档={unit!r} 库={row.unit!r}")
            if source != (row.source_location or ""):
                mismatches.append(f"{code} 来源位置：文档={source!r} 库={row.source_location!r}")
            if usage != (row.downstream_usage or ""):
                mismatches.append(f"{code} 下游用途：文档={usage!r} 库={row.downstream_usage!r}")

        assert not mismatches, "文档与库存在差异：\n" + "\n".join(mismatches)

    def test_qualitative_fields_have_no_unit(self, registry_doc, db_session) -> None:
        """定性条目在两头都不应有单位：单位列存非单位值会让下游类型判断出错。"""
        from sqlalchemy import select

        from app.models.field import FieldRegistry

        doc_rows = _doc_field_rows(registry_doc)
        db_rows = {
            r.field_code: r
            for r in db_session.execute(select(FieldRegistry)).scalars()
        }
        for code, cells in doc_rows.items():
            if cells[2] != "文本":
                continue
            row = db_rows.get(code)
            assert row is not None, f"{code} 不在库中"
            assert row.is_qualitative, f"{code} 文档标文本但库里不是定性"
            assert row.unit is None, f"{code} 定性字段不该有单位，库里是 {row.unit!r}"
            assert cells[3] == "—", f"{code} 文档单位列应为「—」，实际 {cells[3]!r}"
