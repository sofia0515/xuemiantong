"""学习测评工作流服务。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import raise_error
from app.services.session_service import SessionService
from bank.app.agent.workflows.checkpoint import build_thread_config, get_workflow_checkpointer
from bank.app.db.tables import ChatMessage
from bank.app.services.retry_service import RetryExecutor
from bank.app.services.workflow_run_service import WorkflowRunService


LEARNING_WORKFLOW_TYPE = "learning_quiz"

class LearningWorkflowService:
    """负责学习工作流启动、提交和恢复。"""

    def __init__(self, db: Session, llm=None):
        self.db = db
        self.llm = llm


    @staticmethod
    def _plain_state(state: Any) -> dict[str, Any]:
        """将 LangGraph/Pydantic 状态转换为可落库的普通 dict。"""
        if hasattr(state, "model_dump"):
            data = state.model_dump(mode="json")
        else:
            data = dict(state or {})
        if data.get("status") is not None:
            data["status"] = str(data["status"])
        return data


# ============================================================
# 1)出题
# ============================================================
    def start(
        self,
        user_id: int,
        session_id: int,
        request_text: str,
        question_count: int | None = None,
        provider: str = "deepseek",
    ) -> dict[str, Any]:
        """启动学习测评：生成一套题并等待用户提交。"""
        # 检查会话是否存在
        SessionService.get_session_or_404(
            db=self.db,
            user_id=user_id,
            session_id=session_id,
            session_model=0,
        )

        run_id = uuid.uuid4().hex
        state = {
            "run_id": run_id,
            "user_id": user_id,
            "session_id": session_id,
            "request_text": request_text.strip(),
            "question_count": question_count,
            "provider": provider,
            "status": "created",
        }
        # 新建工作流并保存到数据库
        run = WorkflowRunService.create_run(
            db=self.db,
            user_id=user_id,
            session_id=session_id,
            workflow_type=LEARNING_WORKFLOW_TYPE,
            status="created",
            state=state,
            run_id=run_id,
        )
        try:
            # 执行出题图
            final_state = RetryExecutor.run(
                state=state,
                node_name="generate_quiz",
                operation=lambda: self._generate_quiz_state(run.run_id, state),
            )
        except Exception as exc:
            WorkflowRunService.mark_failed(self.db, run, state, "generate_quiz", str(exc))
            raise_error(code=500, message=f"生成学习题目失败: {exc}")

        final_state["run_id"] = run.run_id
        # 更新工作流状态为等待答案
        WorkflowRunService.update_run(self.db, run, "waiting_answer", final_state)
        quiz = final_state.get("quiz") or {}

        # 写入会话消息保存到数据库中
        self._create_learning_message(
            user_id=user_id,
            session_id=session_id,
            request_id=f"{run.run_id}:quiz",
            request_text=request_text.strip(),
            response_text="已完成出题，请完成后提交答案。",
            response_payload={
                "type": "learning_quiz",
                "version": 1,
                "run_id": run.run_id,
                "status": "waiting_answer",
                "quiz": quiz,
            },
        )
        return final_state
    
    def _generate_quiz_state(self, run_id: str, state: dict[str, Any]) -> dict[str, Any]:
        """执行出题图并返回最终状态。"""
        from app.agent.workflows.learning import build_learning_graph

        graph = build_learning_graph(self.llm, checkpointer=get_workflow_checkpointer(), db=self.db)
        config = build_thread_config(run_id)
        graph.invoke(state, config=config)
        return self._plain_state(graph.get_state(config).values)

    def _create_learning_message(
        self,
        *,
        user_id: int,
        session_id: int,
        request_id: str,
        request_text: str,
        response_text: str,
        response_payload: dict[str, Any] | None,
    ) -> ChatMessage:
        """把学习工作流结果写入会话消息，供前端历史列表渲染。"""
        row = ChatMessage(
            user_id=user_id,
            session_id=session_id,
            select_model=2,
            request_id=request_id,
            request_text=request_text,
            response_text=response_text,
            request_segments=[],
            response_segments=[],
            response_payload=response_payload,
            status=0,
            interview_id=None,
            file_extracted_text="",
        )
        self.db.add(row)
        self.db.commit()
        return row


# ============================================================
# 2)交卷
# ============================================================
    def submit_answer(
        self,
        user_id: int,
        run_id: str,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """提交整套题答案并完成评分点评。"""
        run = WorkflowRunService.get_run_or_404(self.db, user_id, run_id)
        if run.workflow_type != LEARNING_WORKFLOW_TYPE:
            raise_error(code=400, message="工作流类型不匹配")
        if run.status != "waiting_answer":
            raise_error(code=400, message="当前工作流不可提交答案")

        state = dict(run.state_json)
        state["answers"] = answers
        state["run_id"] = run.run_id
        state["status"] = "grading"
        WorkflowRunService.update_run(self.db, run, "grading", state)

        try:
            final_state = RetryExecutor.run(
                state=state,
                node_name="evaluate_answer",
                operation=lambda: self._evaluate_answer_state(run.run_id, answers),
            )
        except Exception as exc:
            WorkflowRunService.mark_failed(self.db, run, state, "evaluate_answer", str(exc))
            raise_error(code=500, message=f"学习答案评分失败: {exc}")

        final_state["run_id"] = run.run_id
        response_text = str(
            final_state.get("display_text")
            or final_state.get("review")
            or "本次练习已完成，请根据错题继续复习。"
        )
        WorkflowRunService.update_run(self.db, run, "completed", final_state)
        self._update_learning_message(
            user_id=user_id,
            session_id=run.session_id,
            run_id=run.run_id,
            request_text=str(state.get("request_text") or ""),
            response_text=response_text,
            response_payload=None,
        )
        return final_state

    def _evaluate_answer_state(self, run_id: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
        """执行评分图并返回最终状态。"""
        from langgraph.types import Command

        from app.agent.workflows.learning import build_learning_graph

        graph = build_learning_graph(self.llm, checkpointer=get_workflow_checkpointer(), db=self.db)
        config = build_thread_config(run_id)
        final_state = graph.invoke(Command(resume=answers), config=config)
        return self._plain_state(final_state)

    def _update_learning_message(
        self,
        *,
        user_id: int,
        session_id: int,
        run_id: str,
        request_text: str,
        response_text: str,
        response_payload: dict[str, Any] | None,
    ) -> None:
        """提交答案后更新同一条聊天消息，避免历史里同时保留表单和结果。"""
        row = self._get_learning_quiz_message(
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
        )
        if row is None:
            self._create_learning_message(
                user_id=user_id,
                session_id=session_id,
                request_id=f"{run_id}:quiz",
                request_text=request_text,
                response_text=response_text,
                response_payload=response_payload,
            )
            return

        row.response_text = response_text
        row.response_payload = response_payload
        self.db.commit()

    def _get_learning_quiz_message(
        self,
        *,
        user_id: int,
        session_id: int,
        run_id: str,
    ) -> ChatMessage | None:
        """获取出题阶段写入的聊天消息，用于提交答案后原地更新。"""
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id,
                ChatMessage.request_id == f"{run_id}:quiz",
            )
            .order_by(ChatMessage.id.desc())
        )
        return self.db.scalar(stmt)