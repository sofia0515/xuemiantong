from sqlalchemy import BigInteger, ForeignKey, Index, JSON, String, DateTime, func, UniqueConstraint
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.dialects.mysql import MEDIUMTEXT
import time
from datetime import datetime


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

class Session(Base):
    """会话表：承载用户的学习/面试/笔记会话。"""

    __tablename__ = "sessions"
    __table_args__ = {"comment": "会话表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False, comment="用户 FK"
    )
    session_model: Mapped[int] = mapped_column(
        nullable=False, comment="会话模式：0=学习，1=面试，2=笔记")
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="标题")
    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=_unix_ts,
        comment="创建时间 Unix 秒",
    )

class ChatMessage(Base):
    """消息表：记录用户请求与模型响应。"""

    __tablename__ = "chat_messages"
    __table_args__ = (
        # 按会话拉取消息并按时间排序时走索引，避免全表扫。
        Index("idx_session_id_created_at", "session_id", "created_at"),
        {"comment": "消息表"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="主键")
    user_id: Mapped[int] = mapped_column(ForeignKey(
        "users.id"), nullable=False, comment="用户 FK")
    session_id: Mapped[int] = mapped_column(ForeignKey(
        "sessions.id"), nullable=False, comment="会话 FK")
    select_model: Mapped[int] = mapped_column(
        nullable=False,
        comment="选择模式：0=默认，1=知识精讲，2=刷题，3=简历优化，4=模拟面试，5=面试复盘",
    )
    request_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False, comment="请求唯一标识"
    )
    # MEDIUMTEXT：单条请求/回复可能很长。
    request_text: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=False, comment="用户请求文本")
    response_text: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=False, comment="模型响应文本")
    # 仅存附件段信息（file/image/audio），不存聊天正文文本。
    request_segments: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, comment="用户请求附件段 JSON")
    # 仅存附件段信息（file/image/audio），不存聊天正文文本。
    response_segments: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, comment="模型响应附件段 JSON")
    response_payload: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="模型响应结构化载荷 JSON")
    reference_sources: Mapped[list[dict] | None] = mapped_column(
        JSON, nullable=True, comment="本次回答引用的知识片段来源")
    # 消息状态：0=常规聊天；1=面试转写入口消息。
    status: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
        comment="消息状态：0常规聊天，1面试转写入口",
    )
    # 关联面试记录ID，status=1 时可用。
    interview_id: Mapped[int | None] = mapped_column(
        nullable=True,
        index=True,
        comment="面试记录ID（status=1 时可用）",
    )
    file_extracted_text: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=True, comment="从文件中总结的文本(对话上下文用)")
    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=_unix_ts,
        comment="创建时间 Unix 秒",
    )
class Resource(Base):
    """资源治理总表：统一管理文件、图片、音频元数据。"""

    __tablename__ = "resources"
    __table_args__ = (
        UniqueConstraint("file_hash", "user_id", name="uk_file_hash_user_id"),
        # 业务分类查询索引：用于 list 用户的简历 / 学习资料等。
        Index("idx_user_id_doc_category", "user_id", "doc_category"),
        {"comment": "资源治理总表（单表方案）"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="资源主键ID",
    )
    resource_type: Mapped[int] = mapped_column(
        nullable=False, comment="资源类型：0=文件，1=图片，2=音频"
    )
    storage_scene: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
        comment="存储场景：0=长过期，1=短过期，2=只提取内容不存原文件，3=永久存储",
    )
    upload_purpose: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        server_default="0",
        comment="上传用途：0=普通资源，1=用户头像",
    )
    file_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名")
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="文件MD5")
    storage_path: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="存储路径")
    doc_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="文档业务分类：resume/study_material/general（仅文件类型有意义）",
    )
    user_id: Mapped[int] = mapped_column(ForeignKey(
        "users.id"), nullable=False, comment="上传用户ID")
    expire_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="过期时间")
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        comment="创建时间",
    )
    
class KnowledgeChunk(Base):
    """知识库片段表：存每个文本切片的原文与顺序，作为 Qdrant 的数据源。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("idx_resource_id", "resource_id"),
        Index("idx_vector_id", "vector_id"),
        {"comment": "知识库片段表：Qdrant 向量库的权威原文存储"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="主键")
    resource_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("resources.id"),
        nullable=False,
        comment="关联资源 FK（resources.id）",
    )
    chunk_index: Mapped[int] = mapped_column(
        nullable=False, comment="片段顺序编号，从 0 开始")
    text: Mapped[str] = mapped_column(
        MEDIUMTEXT, nullable=False, comment="片段原文（权威来源）")
    char_count: Mapped[int] = mapped_column(
        nullable=False, comment="片段字符数")
    vector_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="对应 Qdrant Point 的 UUID（双向关联键）",
    )
    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=_unix_ts,
        comment="创建时间 Unix 秒",
    )
