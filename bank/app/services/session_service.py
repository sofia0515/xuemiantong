"""会话管理与面试详情查询服务。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import raise_error
from app.db.tables import Session as SessionModel


class SessionService:
    """会话与面试查询相关服务。"""
    @staticmethod
    def get_session_or_404(
        db: Session, user_id: int, session_id: int, session_model: int | None = None
    ) -> SessionModel:
        """按 user_id + session_id (+session_model) 获取会话，不存在则抛 404。"""
        stmt = select(SessionModel).where(
            SessionModel.id == session_id,
            SessionModel.user_id == user_id,
        )
        if session_model is not None:
            stmt = stmt.where(SessionModel.session_model == session_model)
        session = db.scalar(stmt)
        if not session:
            raise_error(code=404, message="会话不存在")
        return session