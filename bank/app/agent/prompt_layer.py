"""提示词层：统一组装 Prompt 模板"""
from langchain_core.messages import SystemMessage
from app.agent.llm import get_chat_model
from sqlalchemy.orm import Session
from typing import Optional
from app.services.user_profile_service import UserProfileService
from app.services.prompt_template_service import prompt_template_manager
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable
from typing import Any, Optional

from bank.app.services.memory_service import MemoryService

def build_personalized_prompt(
    db: Session,
    user_id: int,
    agent_name: str,
    scene: str,
) -> Optional[str]:
    """
    构建个性化提示词 - 完整的三层处理流程。
    流程：验证 → 格式化 → 注入
    """
    try:
        user_info = UserProfileService.get_profile_dict(db, user_id)
        validated_info = validate_user_info(user_info) # 验证用户信息
        formatted_info = UserProfileService.format_profile_for_injection(validated_info)# 格式化用户信息（数组→文本）
        
        full_prompt = prompt_template_manager.get_full_prompt(agent_name, scene, db)# 获取完整提示词模板
        if not full_prompt:
            return None
        
        personalized_prompt = inject_user_info_to_template(full_prompt, formatted_info) # 注入用户信息到提示词模板
        
        return personalized_prompt
        
    except Exception as e:
        raise RuntimeError(f"构建个性化提示词失败: {e}")


def validate_user_info(user_info_dict: dict) -> dict:
    """第一层：验证 - 检查用户信息的有效性和安全性。"""
    FORBIDDEN_KEYWORDS = ["<script", "javascript:", "onclick", "prompt(", "eval("]
    MAX_LENGTH = {
        "target_job": 128,
        "years_experience": 64,
        "target_level": 32,
    }
    
    validated = {}
    for key, value in user_info_dict.items():
        if value is None:
            validated[key] = ""
            continue
        
        value_str = str(value)
        
        if key in MAX_LENGTH:
            max_len = MAX_LENGTH[key]
            if len(value_str) > max_len:
                value_str = value_str[:max_len]
        
        for keyword in FORBIDDEN_KEYWORDS:
            if keyword.lower() in value_str.lower():
                raise ValueError(f"用户信息包含禁用内容: {keyword}")
        
        validated[key] = value_str
    
    return validated

def inject_user_info_to_template(
    template_content: str, # 参数1：完整的模板内容（含占位符）
    user_info_dict: dict,# 参数2：用户信息字典（格式化后的）
) -> str:
    """第三层：执行提示词注入 - 替换模板中的占位符为用户信息。"""
    prompt_content = template_content
    
    # 遍历字典的每个键值对
    for key, value in user_info_dict.items():
        # 构造占位符：{target_job}
        placeholder = "{" + key + "}"
        # 检查占位符是否存在
        if placeholder in prompt_content:
            # 替换占位符
            prompt_content = prompt_content.replace(placeholder, str(value))
    
    return prompt_content # 返回替换完成的提示词    

def build_rag_system_prompt(
    base_prompt: Optional[str],
    retrieved_text: str,
) -> Optional[str]:
    """在用户画像 prompt 后追加知识库参考资料使用规则，不直接拼接资料内容。"""
    if not base_prompt:
        base_prompt = "你是一个简洁、可靠的通用助手。请用自然语言直接回答，不要包装成 JSON。"

    if not retrieved_text:
        return (
            base_prompt
            + "\n\n本次未检索到相关参考资料。"
            + "请基于上下文常识回答；若问题需要具体资料但你不确定，请明确告知用户。"
        )

    return (
        base_prompt
        + "\n\n本轮用户问题前会提供【参考资料】。"
        + "参考资料仅作为事实依据，请优先基于参考资料回答用户问题。"
        + "如果参考资料中没有相关信息，请直接告知用户而不要编造。"
        + "若回答中引用了参考资料，请在末尾加上一句引导语，例如‘我的回答基于您提供的资料，您可以在下方查看来源’。"
    )

def build_stream_chain_context(
    db: Session,
    user_id: int,
    session_id: int,
    current_message_id: int,
    provider: str,
    request_text: str,
    system_prompt: Optional[str] = None,
    rag_context: str = "",
    session_model: int | None = None,
) -> tuple[Runnable, dict[str, Any]]:
    """组装流式链路上下文，返回可执行链与输入变量。"""
    # 1) 统一记忆入口：返回已合并的最终历史，可能来自工作记忆、短期记忆或后续长期记忆。
    memory_context = MemoryService(db).load_context(
        user_id=user_id,
        session_id=session_id,
        before_message_id=current_message_id,
        session_model=session_model,
        query=request_text,
    )
    history_messages = memory_context["history_messages"]
    # 系统提示词的文字单独收走，对话列表里只留用户和 AI 的来回。
    memory_system_prompt = [
        str(message.content).strip()
        for message in history_messages
        if isinstance(message, SystemMessage) and str(message.content).strip()
    ]
    if memory_system_prompt:
        history_messages = [message for message in history_messages if not isinstance(message, SystemMessage)]

    # 2) system_prompt 为 None 时使用默认兜底提示词，确保链路始终可用。
    if system_prompt is None:
        system_prompt = "你是一个简洁、可靠的单Agent助手。优先直接回答问题，不要包装成 JSON。"
    if memory_system_prompt:
        system_prompt = "\n\n".join(([system_prompt, *memory_system_prompt]))
    
    # 转义 system_prompt 中的花括号，防止 ChatPromptTemplate 把 JSON 内容误解析为变量占位符。
    safe_system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
    if rag_context:
        request_text = rag_context + "\n\n【用户问题】\n" + request_text

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", safe_system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{user_input}"),
        ]
    )

    chain = prompt | get_chat_model(provider=provider)
    stream_inputs = {
        # "history": history_messages,
        "user_input": request_text,
    }
    return chain, stream_inputs


def format_retrieved_chunks(chunks: list[dict]) -> str:
    """把检索结果格式化为本轮用户问题的参考资料上下文。"""
    if not chunks:
        return ""

    lines = ["【参考资料】"]
    for i, chunk in enumerate(chunks, start=1):
        lines.append(f"[来源 {i}] 文件：{chunk['file_name']}")
        lines.append(chunk["text"])
        lines.append("")
    return "\n".join(lines).strip()