import json
import uuid
from collections.abc import Generator
from typing import Any

from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk
from sqlalchemy.orm import Session

from app.agent.prompt_layer import (
    build_personalized_prompt,
    build_rag_system_prompt,
    build_stream_chain_context,
)
from app.db.tables import ChatMessage
from app.services.session_service import SessionService


def _sse_data(payload: dict[str, Any]) -> str:
    """将事件对象编码为一帧 SSE 文本。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

class StreamChatService:
    """负责流式推送、历史重建与最终落库。"""

    @staticmethod
    def stream_chat(
        db: Session,
        user_id: int,
        session_id: int,
        session_model: int,
        request_text: str,
        select_model: int = 0,
        provider: str = "deepseek",
        agent_name: str | None = None,
        scene: str | None = None,
    ) -> StreamingResponse:
        #1) 会话归属校验，不存在则抛 404。
        SessionService.get_session_or_404(
            db=db,
            user_id=user_id,
            session_id=session_id,
            session_model=session_model,
        )

        # 2) 预写入消息占位行：先落库拿到 row.id，供历史记忆截断用。
        row = ChatMessage(
            user_id=user_id,
            session_id=session_id,
            select_model=select_model,
            request_id=uuid.uuid4().hex,
            request_text=request_text,
            response_text="",
            request_segments=[],
            response_segments=[],
            response_payload=None,
            status=0,
            interview_id=None,
            file_extracted_text="",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        # 3) 构建个性化提示词：有 agent_name 才查模板；否则使用通用兜底，不拼接数据库模板。
        if agent_name and scene:
            system_prompt = build_personalized_prompt(
                db=db,
                user_id=user_id,
                agent_name=agent_name,
                scene=scene,
            )
        else:
            system_prompt = None

        #通用兜底
        system_prompt = build_rag_system_prompt(
            base_prompt=system_prompt
        )
        retrieved_chunks = []

        chain, stream_inputs = build_stream_chain_context(
            db=db,
            user_id=user_id,
            session_id=session_id,
            session_model=session_model,
            request_text=request_text,
            provider=provider,
        )

        def event_generator() -> Generator[str, None, None]:
            response_text = ""
            error_message = ""
            sources = [
                {
                    "chunk_id": c.get("chunk_id"),
                    "resource_id": c.get("resource_id"),
                    "chunk_index": c.get("chunk_index"),
                    "file_name": c.get("file_name", ""),
                    "score": round(c.get("score", 0), 4),
                    "text": c.get("text", ""),
                }
                for c in retrieved_chunks
            ]

            source_refs = [
                {
                    "chunk_id": c.get("chunk_id"),
                    "score": round(c.get("score", 0), 4),
                }
                for c in retrieved_chunks
                if c.get("chunk_id")
            ]

            yield _sse_data({"type": "start", "message_id": row.id})
            try:
                for chunk in chain.stream(stream_inputs):
                    delta = StreamChatService._extract_text_delta(chunk)
                    if not delta:
                        continue
                    response_text += delta
                    yield _sse_data({"type": "delta", "text": delta})
            except Exception as exc:
                error_message = str(exc)
            finally:
                row.response_text = response_text
                row.reference_sources = source_refs
                db.add(row)
                db.commit()

                if response_text and not error_message:
                    print("#把本轮追加进工作记忆，并按意图异步更新画像。")
            if error_message:
                yield _sse_data({"type": "error", "message": error_message})#只发事件、不改状态码
            yield _sse_data({"type": "done","response_text": response_text, "sources": sources})             


        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )    


        
    @staticmethod
    def _extract_text_delta(chunk: Any) -> str:
        """从 LangChain 链式调用返回的增量块中提取文本。"""
        if isinstance(chunk, AIMessageChunk):
            return chunk.content or ""
        return ""