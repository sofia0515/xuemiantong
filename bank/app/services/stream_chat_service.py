from collections.abc import Generator

from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from app.agent.prompt_layer import build_personalized_prompt, build_rag_system_prompt, build_stream_chain_context
from typing import Any
import json
from langchain_core.messages import AIMessageChunk

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
        #构建个性化提示词：有 agent_name 才查模板；否则使用通用兜底，不拼接数据库模板。
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

        chain, stream_inputs = build_stream_chain_context(
            db=db,
            user_id=user_id,
            session_id=session_id,
            session_model=session_model,
            request_text=request_text,
            provider=provider,
        )

        def event_generator() -> Generator[str, None, None]:
            try:
                for chunk in chain.stream(stream_inputs):
                    if not isinstance(chunk, AIMessageChunk) or not chunk.content:
                        continue
                    response_text += chunk.content
                    yield _sse_data({"type": "delta", "text": chunk.content})
            except Exception as exc:
                yield _sse_data({"type": "error", "message": str(exc)})


        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )    


        
