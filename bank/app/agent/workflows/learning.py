
import json

from bank.app.agent.workflows.common import invoke_json
from bank.app.agent.workflows.state import LearningWorkflowState
from bank.app.services.prompt_template_service import AGENT_CONFIG, prompt_template_manager
from typing import Any



def build_learning_graph(llm=None, checkpointer=None, db: Any = None):
    """构建完整学习图：出题 -> 中断等待答案 -> 评分 -> 完成。"""
    from langgraph.graph import END, StateGraph

    builder = StateGraph(LearningWorkflowState)
    builder.add_node("generate_quiz", create_generate_quiz_node(llm, db)) #出题节点
    builder.add_node("wait_user_answer", create_wait_user_answer_node())
    builder.add_node("evaluate_answer", create_evaluate_and_review_node(llm, db))
    builder.add_node("finalize_result", create_finalize_learning_result_node())
    builder.set_entry_point("generate_quiz")
    builder.add_edge("generate_quiz", "wait_user_answer")
    builder.add_edge("wait_user_answer", "evaluate_answer")
    builder.add_edge("evaluate_answer", "finalize_result")
    builder.add_edge("finalize_result", END)
    return builder.compile(checkpointer=checkpointer)


# ============================================================
# 1)出题节点 
# ============================================================

def create_generate_quiz_node(llm=None, db: Any = None):
    """创建出题节点。"""

    def node(state: LearningWorkflowState) -> dict[str, Any]:
        data = invoke_json(llm, _build_dynamic_quiz_prompt(state, db), provider="deepseek")
        questions = [
            item
            for item in ensure_list(data.get("questions"))
            if isinstance(item, dict) and _is_valid_question(item)
        ]
        quiz = {
            "title": str(data.get("title") or "学习练习"),
            "description": str(data.get("description") or "请完成以下题目。"),
            "question_count": len(questions),
            "questions": questions,
        }
        return {"quiz": quiz, "status": "waiting_answer"}

    return node

#动态构建出题提示词
def _build_dynamic_quiz_prompt(state: LearningWorkflowState, db: Any = None) -> str:
    template = _get_template_prompt(db, "quiz_generate_workflow")
    if not template:
        return _build_quiz_prompt(state)
    question_count = _state_get(state, "question_count") or "用户未指定时默认 5 题"
    return _render_prompt_template(
        template,
        {
            "request_text": _state_get(state, "request_text", ""),
            "question_count": question_count,
        },
    )

def _get_template_prompt(db: Any, agent_name: str) -> str | None:
    """从提示词表获取模板；失败时返回 None，让调用方走硬编码兜底。"""
    if db is None:
        return None
    scene = AGENT_CONFIG.get(agent_name, {}).get("scene")
    if not scene:
        return None
    return prompt_template_manager.get_full_prompt(agent_name, scene, db)

def _build_quiz_prompt(state: LearningWorkflowState) -> str:
    return f"""
你是出题题库 Agent。请根据用户学习要求生成一套练习题。

用户要求：{_state_get(state, "request_text", "")}
题目数量：{_state_get(state, "question_count") or "用户未指定时默认 5 题"}

只输出 JSON，不要输出 Markdown，不要输出 HTML。
JSON 格式必须如下：
{{
  "title": "练习标题",
  "description": "练习说明",
  "question_count": 5,
  "questions": [
    {{
      "id": "q1",
      "type": "radio",
      "stem": "题干",
      "options": [{{"value": "A", "label": "选项内容"}}],
      "required": true,
      "points": 20
    }}
  ]
}}

约束：
1. type 只能是 radio、checkbox、textarea。
2. radio 表示单选题，checkbox 表示多选题，textarea 表示简答题。
3. radio 和 checkbox 必须提供 options，textarea 的 options 为空数组。
4. 每题 id 使用 q1、q2 递增。
5. points 总分建议合计 100。
6. 不要输出答案，不要输出解析。
""".strip()

def _state_get(state: LearningWorkflowState | dict[str, Any], key: str, default: Any = None) -> Any:
    """兼容 Pydantic 状态对象和 dict 状态的字段读取。"""
    if isinstance(state, dict):
        return state.get(key, default)
    return getattr(state, key, default)

def _render_prompt_template(template: str, variables: dict[str, Any]) -> str:
    """用简单替换渲染提示词，避免 JSON 示例中的大括号被 format 误处理。"""
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value))
    return result.strip()

#处理模型返回
def ensure_list(value: Any) -> list[Any]:
    """把模型可能返回的空值或非列表值收敛成列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def _is_valid_question(question: dict[str, Any]) -> bool:
    """只接受前端可识别的表单题型。"""
    return str(question.get("type") or "").strip() in {"radio", "checkbox", "textarea"}


# ============================================================
# 2)中断节点
# ============================================================
def create_wait_user_answer_node():
    """创建等待用户提交答案的中断节点。"""

    def node(state: LearningWorkflowState) -> dict[str, Any]:
        from langgraph.types import interrupt

        answers = interrupt({"quiz": _state_get(state, "quiz", {})})
        return {"answers": ensure_list(answers), "status": "grading"}

    return node


# ============================================================
# 3)评分点评节点
# ============================================================
def create_evaluate_and_review_node(llm=None, db: Any = None):
    """创建评分点评节点。"""

    def node(state: LearningWorkflowState) -> dict[str, Any]:
        data = invoke_json(llm, _build_dynamic_evaluation_prompt(state, db), provider="deepseek")
        score = int(data.get("score") or 0)
        score = max(0, min(score, 100))
        weaknesses = [str(item) for item in ensure_list(data.get("weaknesses")) if str(item).strip()]
        evaluation = {"score": score, "items": ensure_list(data.get("items"))}
        review = str(data.get("display_text") or data.get("review") or "本次练习已完成，请根据错题继续复习。")
        return {
            "evaluation": evaluation,
            "score": score,
            "weaknesses": weaknesses,
            "review": review,
            # "a2a_envelope": envelope.model_dump(),
            "status": "completed",
        }

    return node

def _build_dynamic_evaluation_prompt(state: LearningWorkflowState, db: Any = None) -> str:
    template = _get_template_prompt(db, "learning_evaluator")
    if not template:
        return _build_evaluation_prompt(state)
    prompt = _render_prompt_template(
        template,
        {
            "quiz_json": _json_text(_state_get(state, "quiz", {})),
            "answers_json": _json_text(_state_get(state, "answers", [])),
        },
    )
    return f"""
{prompt}

补充要求：
1. display_text 必须是详细自然语言字符串，适合直接展示给用户。
2. display_text 必须包含总分、整体评价、逐题点评、参考答案或参考要点、薄弱点和学习建议。
3. display_text 不要输出 JSON 字符串，不要使用 Markdown 表格。
""".strip()    


def _build_evaluation_prompt(state: LearningWorkflowState) -> str:
    return f"""
你是学习测评 Agent。请根据题目和用户答案完成评分、点评和薄弱点提取。

题目：
{_json_text(_state_get(state, "quiz", {}))}

用户答案：
{_json_text(_state_get(state, "answers", []))}

只输出 JSON，不要输出 Markdown。
JSON 格式必须如下：
{{
  "score": 85,
  "items": [
    {{
      "question_id": "q1",
      "score": 20,
      "is_correct": true,
      "correct_answer": "标准答案或参考要点",
      "analysis": "本题点评"
    }}
  ],
  "weaknesses": ["薄弱点1", "薄弱点2"],
  "review": "给用户看的总评和学习建议",
  "display_text": "给前端直接展示的完整中文点评文本"
}}

要求：
1. score 是 0 到 100 的整数。
2. 每道题都必须评分并给出 analysis。
3. weaknesses 最多 5 个，使用短语。
4. review 用中文，简洁具体。
5. display_text 必须是详细自然语言字符串，适合直接展示给用户。
6. display_text 必须包含总分、整体评价、逐题点评、参考答案或参考要点、薄弱点和学习建议。
7. display_text 不要输出 JSON 字符串，不要使用 Markdown 表格。
""".strip()


def _json_text(value: Any) -> str:
    """生成给模型看的紧凑 JSON 文本。"""
    return json.dumps(value, ensure_ascii=False, indent=2)


# ============================================================
# 4)学习测评完成节点
# ============================================================
def create_finalize_learning_result_node():
    """创建学习测评完成节点。"""

    def node(state: LearningWorkflowState) -> dict[str, Any]:
        return {"status": "completed"}

    return node