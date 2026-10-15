"""Pydantic 出入参统一出口。

只覆盖 API 实际暴露的实体：任务、文档、证据、字段值、公司。配置域、准则映射域、
标注与评估域的表当前没有对外接口，等对应模块开工时再补各自的出入参。
"""

from app.schemas.common import ApiResponse, PageMeta
from app.schemas.company import (
    CompanyAliasCreate,
    CompanyAliasRead,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    CompanyWithAliases,
)
from app.schemas.document import (
    BBox,
    ChunkRead,
    DocumentBlockCreate,
    DocumentBlockRead,
    DocumentCreate,
    DocumentRead,
)
from app.schemas.evidence import (
    ConclusionEvidenceCreate,
    ConclusionEvidenceRead,
    EvidenceAnchor,
    EvidenceRead,
    EvidenceWithAnchor,
)
from app.schemas.field import (
    FieldDefinitionIn,
    FieldRegistryRead,
    FieldValueRead,
    FieldValueUpsert,
    FieldValueWithMeta,
    to_field_value_with_meta,
)
from app.schemas.task import (
    CapabilityRead,
    TaskBoundaries,
    TaskCreate,
    TaskDetail,
    TaskNodeRead,
    TaskOutputRead,
    TaskRead,
    VersionSnapshotRead,
)

__all__ = [
    "ApiResponse",
    "BBox",
    "CapabilityRead",
    "ChunkRead",
    "CompanyAliasCreate",
    "CompanyAliasRead",
    "CompanyCreate",
    "CompanyRead",
    "CompanyUpdate",
    "CompanyWithAliases",
    "ConclusionEvidenceCreate",
    "ConclusionEvidenceRead",
    "DocumentBlockCreate",
    "DocumentBlockRead",
    "DocumentCreate",
    "DocumentRead",
    "EvidenceAnchor",
    "EvidenceRead",
    "EvidenceWithAnchor",
    "FieldDefinitionIn",
    "FieldRegistryRead",
    "FieldValueRead",
    "FieldValueUpsert",
    "FieldValueWithMeta",
    "PageMeta",
    "TaskBoundaries",
    "TaskCreate",
    "TaskDetail",
    "TaskNodeRead",
    "TaskOutputRead",
    "TaskRead",
    "VersionSnapshotRead",
    "to_field_value_with_meta",
]
