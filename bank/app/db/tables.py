from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.dialects.mysql import MEDIUMTEXT
import time


# 创建基类
Base = declarative_base()

def _unix_ts() -> int:
    """返回当前 Unix 秒时间戳。"""
    return int(time.time())

class UserProfile(Base):
    """用户个人信息表：存储已提取的用户信息（来源：简历解析或表单填写）"""

    __tablename__ = "user_profiles"
    __table_args__ = (
        Index("idx_user_id", "user_id"),
        {"comment": "用户个人信息表"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="主键")
    
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), 
        nullable=False, unique=True, 
        comment="用户FK（一对一关系）")
    
    target_job: Mapped[str | None] = mapped_column(
        String(128), nullable=True, 
        comment="目标岗位，如'Python后端工程师'")
    
    years_experience: Mapped[str | None] = mapped_column(
        String(64), nullable=True, 
        comment="工作经验，如'3年'")
    
    target_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True, 
        comment="目标等级：初级/中级/高级")
    
    target_skills: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, 
        comment="已掌握技能 JSON数组")
    
    weak_topics: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, 
        comment="薄弱点 JSON数组")
    
    learning_goal: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="当前学习目标，如'准备中级后端面试'")
    
    learning_style: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="学习偏好，如'喜欢案例驱动'")
    
    interview_focus: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True,
        comment="面试重点 JSON数组")
    
    long_term_summary: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="长期画像摘要，用于 Prompt 展示")
    
    created_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, 
        default=_unix_ts,
        comment="创建时间 Unix秒")
    
    updated_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, 
        default=_unix_ts, onupdate=_unix_ts,
        comment="更新时间 Unix秒")

class PromptTemplate(Base):
    """提示词模板版本管理表：统一管理各智能体的提示词模板，支持版本控制和复用。"""

    __tablename__ = "prompt_templates"
    __table_args__ = (
        Index("idx_agent_scene", "agent_name", "scene"),
        {"comment": "提示词模板版本管理表"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="模板ID")
    agent_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="智能体名称，公共模板此字段为空")
    scene: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="业务场景")
    template_type: Mapped[int] = mapped_column(
        default=1,
        server_default="1",
        comment="模板类型：1-私有 2-公共",
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="模板名称")
    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="版本变更说明")
    template_content: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=False, comment="提示词正文（含变量占位）")
    variables: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment='模板变量JSON列表，如["target_job","weak_points"]',
    )
    version: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default="1", comment="版本号，整数自增")
    is_active: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
        comment="是否生效：1-是 0-否",
    )
    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=_unix_ts,
        comment="创建时间 Unix 秒",
    )


