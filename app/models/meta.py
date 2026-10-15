"""可复现性支撑：提示词版本表与大模型调用缓存表（技术架构文档 9.2 审计域）。

全部计算由大模型承担，温度固定为 0，相同输入必须得到相同输出。
这两张表是这一承诺的落地载体：提示词版本固化进任务的 version_snapshot，
调用缓存按提示词哈希命中，使复现不必重新付费调用。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PromptVersion(Base):
    """各智能体提示词的版本、内容哈希与内容。

    版本一旦被任务引用就不再修改，改动必须发新版本，否则历史任务无法复现。
    """

    __tablename__ = "prompt_version"
    __table_args__ = (
        UniqueConstraint("agent_code", "version", name="uq_prompt_agent_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(LONGTEXT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LlmCallCache(Base):
    """大模型调用缓存。

    技术架构文档 9.2 写的是“以提示词哈希与模型标识为键”，9.3 又要求“按提示词哈希
    建立唯一索引”。两者取前者做唯一约束、后者退化为普通索引：换模型时同一提示词
    的响应必须分开缓存，否则会拿旧模型的输出冒充新模型的结果。
    """

    __tablename__ = "llm_call_cache"
    __table_args__ = (
        UniqueConstraint("prompt_hash", "model", name="uq_cache_prompt_model"),
        Index("ix_cache_prompt_hash", "prompt_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prompt_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    response: Mapped[str] = mapped_column(LONGTEXT)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime)
