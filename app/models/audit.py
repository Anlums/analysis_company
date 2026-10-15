"""审计域：审计日志（技术架构文档 9.1 表 18、9.2、11.4）。

11.4 要求人工标注与规则配置等写操作鉴权，全部写操作记入审计日志，记录操作者、
动作与变更前后值。大模型调用缓存表同属审计域，已建在 meta.py。

记前后值而非只记动作，是为了让规则集、阈值这类配置的回滚有据可依——9.2 明确要求
规则集支持历史版本回查，光靠版本号在误改场景下还原不出改了哪一格。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, JSON, String, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 操作者类型（9.2：用户、智能体或系统）
OPERATOR_USER = "user"
OPERATOR_AGENT = "agent"
OPERATOR_SYSTEM = "system"


class AuditLog(Base):
    """审计日志表。

    target_type/target_id 指向被操作的对象，两者配合可查某个规则集或某条阈值的
    全部变更历史。执行链路本身的可观测性由 task_node 承担，本表只记写操作。
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_target", "target_type", "target_id"),
        Index("ix_audit_log_operator", "operator_type", "operator_id"),
        Index("ix_audit_log_time", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator_type: Mapped[str] = mapped_column(String(16))
    operator_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(128))
    before_value: Mapped[dict | None] = mapped_column(JSON)
    after_value: Mapped[dict | None] = mapped_column(JSON)
    # 鉴权失败或校验不通过的写操作同样留痕，否则无法区分“没做”和“被拒”
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[str | None] = mapped_column(LONGTEXT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
