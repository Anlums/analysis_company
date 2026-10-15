"""ORM 模型统一出口。

Alembic 迁移与 Base.metadata 都依赖此处的导入副作用：模型不被导入就不进 metadata，
autogenerate 会认为该表不存在并生成删表语句。

按技术架构文档 9.1 表 18 的域划分组织：
  公司域      company.py      Company, CompanyAlias
  文档域      document.py     Document, DocumentBlock, Chunk, ChunkBlock
  证据域      evidence.py     Evidence, ConclusionEvidence
  字段表      field.py        FieldRegistry, FieldValue          （9.1 未列，补缺）
  任务域      task.py         Task, TaskNode, TaskOutput, VersionSnapshot
  能力与编排  capability.py   Capability, OrchestrationCheckpoint, CheckpointWrite
  准则映射域  standard.py     StandardMapping, MappingRecord, AnnotationLibrary
  配置域      industry.py     Industry, IndicatorApplicability, TermDictionary
              rules.py        RuleSet, Threshold, WeightScheme
  标注评估域  evaluation.py   Annotation, ErrorCase, EvalSample, EvalMetric
  审计域      audit.py        AuditLog
              meta.py         PromptVersion, LlmCallCache
"""

from app.models.audit import AuditLog
from app.models.capability import Capability, CheckpointWrite, OrchestrationCheckpoint
from app.models.company import Company, CompanyAlias
from app.models.document import Chunk, ChunkBlock, Document, DocumentBlock
from app.models.evaluation import Annotation, ErrorCase, EvalMetric, EvalSample
from app.models.evidence import ConclusionEvidence, Evidence
from app.models.field import FieldRegistry, FieldValue
from app.models.industry import IndicatorApplicability, Industry, TermDictionary
from app.models.meta import LlmCallCache, PromptVersion
from app.models.rules import RuleSet, Threshold, WeightScheme
from app.models.standard import AnnotationLibrary, MappingRecord, StandardMapping
from app.models.task import Task, TaskNode, TaskOutput, VersionSnapshot

__all__ = [
    "Annotation",
    "AnnotationLibrary",
    "AuditLog",
    "Capability",
    "CheckpointWrite",
    "Chunk",
    "ChunkBlock",
    "Company",
    "CompanyAlias",
    "ConclusionEvidence",
    "Document",
    "DocumentBlock",
    "ErrorCase",
    "EvalMetric",
    "EvalSample",
    "Evidence",
    "FieldRegistry",
    "FieldValue",
    "IndicatorApplicability",
    "Industry",
    "LlmCallCache",
    "MappingRecord",
    "OrchestrationCheckpoint",
    "PromptVersion",
    "RuleSet",
    "StandardMapping",
    "Task",
    "TaskNode",
    "TaskOutput",
    "TermDictionary",
    "Threshold",
    "VersionSnapshot",
    "WeightScheme",
]
