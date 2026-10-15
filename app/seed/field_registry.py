"""字段注册表种子数据：文档登记的 46 个字段 + 7 个依据两大计划书补齐的字段，共 53 个。

46 个来自《数据字段编码注册表》，内容与文档逐条一致，仅两处建模调整：
  1. 定性条目的单位记为 NULL，不用文档里的“文本”二字——单位列存非单位值会让
     下游的类型判断出错，定性由 is_qualitative 表达。
  2. industry_scope 由编码前缀推出：FOR 前缀为林业包，其余为全行业通用（ALL）。

另 7 个是为补设计文档已明确要求、而注册表漏登的口径缺口：
  BS_AR_FIN、IS_INTEREST_INCOME —— 指标②⑨ 的取数口径（见各条 downstream_usage）
  META_* 5 个 —— 财务分析智能体计划书第二章「会计口径识别」的输入，
                  该章是指标计算的前置过滤单元，注册表此前没有任何字段承载它。
META_ 是新增的类别前缀，原编码规则只列了 BS/IS/CF/ENV/SOC/GOV/FOR，
需回填进《数据字段编码注册表》使编码规则自洽。

季度数据不新增编码：财务分析智能体计划书 3.2.3 要求还原单季度并算环比，
但季度值与年度值是同一批字段在不同报告期的取值，用 field_value.period
（已是 VARCHAR(16)）承载 Q1–Q4 即可，表结构与编码清单都不用动。

注册表规定编码一经登记不复用、新增字段须先登记，所以这里是 upsert 语义：
重复执行只更新名称与用途，不会重复插入，也不会删掉本表已有而此处没有的字段。

环境/社会/治理 16 个字段目前只是常用指标子集，与 CASS-ESG 6.0 附录逐条对齐后
在此处继续追加即可，不需要动表结构。
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.models.field import (
    CATEGORY_BS,
    CATEGORY_CF,
    CATEGORY_ENV,
    CATEGORY_FOR,
    CATEGORY_GOV,
    CATEGORY_IS,
    CATEGORY_META,
    CATEGORY_SOC,
    SCOPE_ALL,
    FieldRegistry,
)


def _field(
    code: str,
    name: str,
    unit: str | None,
    category: str,
    source: str,
    usage: str,
    *,
    qualitative: bool = False,
) -> dict[str, object]:
    return {
        "field_code": code,
        "name": name,
        "unit": None if qualitative else unit,
        "category": category,
        "source_location": source,
        "downstream_usage": usage,
        "is_qualitative": qualitative,
        "industry_scope": CATEGORY_FOR if category == CATEGORY_FOR else SCOPE_ALL,
        "is_active": True,
    }


FIELD_DEFINITIONS: tuple[dict[str, object], ...] = (
    # 一、财务字段（全行业通用，来源为年报三张主表及附注）
    _field(
        "BS_CASH", "货币资金", "元", CATEGORY_BS, "合并资产负债表",
        "指标⑨货币资金高且有息负债高、指标⑩现金资产占比过高",
    ),
    _field(
        "BS_AR", "应收账款", "元", CATEGORY_BS, "合并资产负债表及附注",
        "指标②营收增速 vs 应收账款增速",
    ),
    _field(
        "BS_AR_FIN", "应收款项融资", "元", CATEGORY_BS, "合并资产负债表",
        "指标②应收口径补全、指标①“票据占比提升”合理解释的核验依据",
    ),
    _field(
        "BS_OTHER_AR", "其他应收款", "元", CATEGORY_BS, "合并资产负债表及附注",
        "指标⑧其他应收款增速 vs 净利润增速",
    ),
    _field(
        "BS_INV", "存货", "元", CATEGORY_BS, "合并资产负债表",
        "指标④营收增速 vs 存货增速",
    ),
    _field(
        "BS_FA", "固定资产", "元", CATEGORY_BS, "合并资产负债表",
        "指标⑪投资现金流与资产变动不匹配",
    ),
    _field("BS_CIP", "在建工程", "元", CATEGORY_BS, "合并资产负债表", "指标⑪"),
    _field(
        "BS_GOODWILL", "商誉", "元", CATEGORY_BS, "合并资产负债表及附注",
        "指标⑫商誉高企及减值风险",
    ),
    _field(
        "BS_AP", "应付账款", "元", CATEGORY_BS, "合并资产负债表",
        "指标⑤应付账款增速 vs 营业成本增速",
    ),
    _field(
        "BS_IBD", "有息负债合计", "元", CATEGORY_BS,
        "短期借款、长期借款、应付债券、应付票据、一年内到期的非流动负债、租赁负债合计",
        "指标⑨",
    ),
    _field(
        "BS_ASSETS", "资产总计", "元", CATEGORY_BS, "合并资产负债表",
        "多项指标的规模分母",
    ),
    _field(
        "BS_EQUITY", "归属于母公司股东权益", "元", CATEGORY_BS, "合并资产负债表",
        "指标⑫商誉占净资产比",
    ),
    _field(
        "IS_REV", "营业收入", "元", CATEGORY_IS, "合并利润表",
        "指标②④⑤⑥的增速基数",
    ),
    _field("IS_COST", "营业成本", "元", CATEGORY_IS, "合并利润表", "指标⑤"),
    _field(
        "IS_EXP", "期间费用合计", "元", CATEGORY_IS,
        "销售、管理、研发、财务费用合计", "指标⑥期间费用率异常变动",
    ),
    _field(
        "IS_EBT", "利润总额", "元", CATEGORY_IS, "合并利润表",
        "指标⑦税负率（所得税费用/利润总额）",
    ),
    _field("IS_TAX", "所得税费用", "元", CATEGORY_IS, "合并利润表", "指标⑦"),
    _field(
        "IS_INTEREST_INCOME", "利息收入", "元", CATEGORY_IS,
        "合并利润表·财务费用附注", "指标⑨货币资金高且有息负债高（利息收入明显偏低）",
    ),
    _field("IS_NP", "净利润", "元", CATEGORY_IS, "合并利润表", "指标①③⑧"),
    _field(
        "IS_NPDED", "扣除非经常性损益后的净利润", "元", CATEGORY_IS,
        "合并利润表及附注", "指标③非经常性损益影响度",
    ),
    _field(
        "IS_NONREC", "非经常性损益合计", "元", CATEGORY_IS,
        "非经常性损益明细表", "指标③",
    ),
    _field(
        "CF_OPR", "经营活动产生的现金流量净额", "元", CATEGORY_CF,
        "合并现金流量表", "指标①利润增速 vs 经营现金流增速",
    ),
    _field(
        "CF_INV", "投资活动产生的现金流量净额", "元", CATEGORY_CF,
        "合并现金流量表", "指标⑪",
    ),
    _field(
        "CF_CAPEX", "购建长期资产支付的现金", "元", CATEGORY_CF,
        "合并现金流量表", "指标⑪",
    ),
    # 二、环境字段（ESG 报告环境绩效章节）
    _field(
        "ENV_GHG_S1", "温室气体排放量（范围一）", "吨CO2e", CATEGORY_ENV,
        "ESG 报告环境绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "ENV_GHG_S2", "温室气体排放量（范围二）", "吨CO2e", CATEGORY_ENV,
        "ESG 报告环境绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "ENV_ENERGY", "综合能源消耗量", "吨标准煤", CATEGORY_ENV,
        "ESG 报告环境绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "ENV_WATER", "总用水量", "立方米", CATEGORY_ENV,
        "ESG 报告环境绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "ENV_WASTE", "废弃物产生量", "吨", CATEGORY_ENV,
        "ESG 报告环境绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "ENV_WASTE_RATE", "废弃物回收利用率", "%", CATEGORY_ENV,
        "ESG 报告环境绩效章节", "七维评分·实质性",
    ),
    _field(
        "ENV_ASSUR", "第三方鉴证情况", None, CATEGORY_ENV,
        "ESG 报告鉴证声明", "置信度评估·第三方鉴证因素", qualitative=True,
    ),
    _field(
        "ENV_PENALTY", "环保行政处罚记录", None, CATEGORY_ENV,
        "ESG 报告及外部处罚名单", "漂绿检测·外部信息交叉核验", qualitative=True,
    ),
    # 三、社会与治理字段
    _field(
        "SOC_EMPLOYEE", "员工总数", "人", CATEGORY_SOC,
        "ESG 报告社会绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "SOC_SAFETY", "安全生产事故数", "起", CATEGORY_SOC,
        "ESG 报告社会绩效章节", "七维评分·实质性",
    ),
    _field(
        "SOC_TRAIN", "员工培训投入", "万元", CATEGORY_SOC,
        "ESG 报告社会绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "SOC_DONATION", "公益捐赠投入", "万元", CATEGORY_SOC,
        "ESG 报告社会绩效章节", "七维评分·完整性覆盖率",
    ),
    _field(
        "GOV_BOARD", "董事会会议次数", "次", CATEGORY_GOV,
        "ESG 报告治理章节", "七维评分·过程性",
    ),
    _field(
        "GOV_INDEP", "独立董事占比", "%", CATEGORY_GOV,
        "ESG 报告治理章节", "七维评分·过程性",
    ),
    _field(
        "GOV_ESG_COMM", "ESG 专门委员会设置", None, CATEGORY_GOV,
        "ESG 报告治理章节", "七维评分·过程性", qualitative=True,
    ),
    _field(
        "GOV_VIOLATION", "合规违规事件", None, CATEGORY_GOV,
        "ESG 报告及监管公告", "漂绿检测·外部信息交叉核验", qualitative=True,
    ),
    # 四、行业扩展字段（林业包，随行业包导入）
    _field(
        "FOR_BIO_CONS", "消耗性生物资产", "元", CATEGORY_FOR,
        "年报生物资产附注", "行业专属风险识别",
    ),
    _field(
        "FOR_BIO_PROD", "生产性生物资产", "元", CATEGORY_FOR,
        "年报生物资产附注", "行业专属风险识别",
    ),
    _field(
        "FOR_FOREST_AREA", "林地面积", "亩", CATEGORY_FOR,
        "年报及 ESG 报告", "行业专属风险识别",
    ),
    _field(
        "FOR_VOLUME", "林木蓄积量", "立方米", CATEGORY_FOR,
        "年报及 ESG 报告", "行业专属风险识别",
    ),
    _field(
        "FOR_MTG_AREA", "林权抵押面积", "亩", CATEGORY_FOR,
        "年报附注", "行业专属风险识别",
    ),
    _field(
        "FOR_MTG_AMT", "林权抵押金额", "元", CATEGORY_FOR,
        "年报附注", "行业专属风险识别",
    ),
    _field(
        "FOR_CARBON", "碳汇量", "吨CO2e", CATEGORY_FOR,
        "ESG 报告", "行业专属风险识别",
    ),
    _field(
        "FOR_CERT_AREA", "森林认证面积", "亩", CATEGORY_FOR,
        "ESG 报告", "行业专属风险识别",
    ),
    # 五、会计口径识别字段
    # 依据财务分析智能体计划书第二章。该章把「会计口径识别」定为财务异常识别的
    # 前置过滤单元，明确识别范围含会计政策变更、会计估计变更、前期差错更正、
    # 合并范围与列报变化四类，并要求「发生变更时优先使用追溯调整后的可比数据」。
    # 指标②④⑤⑥⑧ 全是增速型，取错基数即全盘皆错，此前注册表没有任何字段承载它。
    _field(
        "META_AUDIT_OPINION", "审计意见类型", None, CATEGORY_META,
        "审计报告", "主题综合亮灯·红灯升级条件（审计非标意见）", qualitative=True,
    ),
    _field(
        "META_ACCT_POLICY_CHANGE", "会计政策变更说明", None, CATEGORY_META,
        "财务报表附注·重要会计政策及会计估计", "会计口径识别·可比性判定", qualitative=True,
    ),
    _field(
        "META_ACCT_ESTIMATE_CHANGE", "会计估计变更说明", None, CATEGORY_META,
        "财务报表附注·重要会计政策及会计估计", "会计口径识别·可比性判定（未来适用法）",
        qualitative=True,
    ),
    _field(
        "META_PRIOR_ERROR", "前期差错更正说明", None, CATEGORY_META,
        "财务报表附注·前期差错更正", "会计口径识别·追溯重述，原披露数与更正数并存",
        qualitative=True,
    ),
    _field(
        "META_SCOPE_CHANGE", "合并范围与列报变化说明", None, CATEGORY_META,
        "财务报表附注·合并范围变更", "会计口径识别·同比与同行比较前单独说明",
        qualitative=True,
    ),
)

# 可被种子覆盖的列。field_code 是主键不入列，is_active 不动——停用字段是人工决定，
# 不该被一次重跑种子悄悄改回 True。
_UPDATABLE = (
    "name",
    "unit",
    "category",
    "source_location",
    "downstream_usage",
    "is_qualitative",
    "industry_scope",
)


def seed_field_registry(session: Session) -> int:
    """把注册表字段 upsert 进 field_registry，返回本次写入的行数。"""
    stmt = mysql_insert(FieldRegistry).values(list(FIELD_DEFINITIONS))
    # updated_at 必须显式给：ON DUPLICATE KEY UPDATE 不触发模型的 onupdate
    session.execute(
        stmt.on_duplicate_key_update(
            **{col: stmt.inserted[col] for col in _UPDATABLE},
            updated_at=func.now(),
        )
    )
    session.commit()
    return len(FIELD_DEFINITIONS)


def main() -> None:
    from sqlalchemy import func, select

    from app.core.database import SessionLocal

    with SessionLocal() as session:
        count = seed_field_registry(session)
        total = session.execute(
            select(func.count()).select_from(FieldRegistry)
        ).scalar_one()
        print(f"upsert {count} 个字段，field_registry 现有 {total} 行")


if __name__ == "__main__":
    main()
