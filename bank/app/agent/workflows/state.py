"""学习工作流状态定义。"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

class WorkflowStatus(StrEnum):
    """学习工作流状态。"""

    CREATED = "created"
    GENERATING_QUIZ = "generating_quiz"
    WAITING_ANSWER = "waiting_answer"
    GRADING = "grading"
    COMPLETED = "completed"
    FAILED = "failed"
    
class LearningWorkflowState(BaseModel):
    """学习测评状态模型，支持跨请求分阶段补齐。"""

    run_id: str | None = Field(default=None, description="流程唯一标识，保存后生成")
    user_id: int = Field(description="用户ID")
    session_id: int = Field(description="会话ID")
    request_text: str = Field(description="用户出题需求文本")
    provider: str = Field(default="deepseek", description="大模型渠道标识")
    question_count: int | None = Field(default=5, description="出题数量")
    quiz: dict[str, Any] = Field(default_factory=dict, description="AI生成测评题目")
    answers: list[dict[str, Any]] = Field(default_factory=list, description="用户提交答案")
    evaluation: dict[str, Any] = Field(default_factory=dict, description="AI批改明细")
    score: int = Field(default=0, description="测评总分")
    weaknesses: list[str] = Field(default_factory=list, description="知识薄弱点")
    review: str = Field(default="", description="测评总结与学习建议")
    status: WorkflowStatus = Field(default=WorkflowStatus.CREATED, description="流程当前阶段")
    a2a_envelope: dict[str, Any] = Field(default_factory=dict, description="A2A 契约信封，供下游专家 Agent 消费")