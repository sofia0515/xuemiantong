"""长期记忆服务：基于 UserProfile 实现。

核心流程：
1. 读取：轻量模型判断是否需要用户画像；需要时再判断用户关心哪组字段（goal/ability/preference/interview），只拼接对应字段注入 Prompt。
2. 写入：轻量模型判断是否需要更新画像；需要时后台线程调用 DeepSeek 抽取字段并合并入库。
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.db.tables import UserProfile
from app.services.long_term_memory_corpus import (
    PROFILE_READ_PATTERNS,
    PROFILE_UPDATE_PATTERNS,
    ALL_SECTIONS,
)



class LongTermMemory:
    """长期记忆：读取画像、判断读写意图、异步更新画像。"""
    def __init__(self, db: Session):
        self.db = db

    def load_memory_context(
        self,
        user_id: int,
        session_model: int | None = None,
        query: str = "",
        enable_long_term: bool | None = None,
        limit: int = 6,
    ) -> dict:
        """按需读取用户画像，并返回可注入 Prompt 的文本。"""
        del session_model, limit
        should_load = (
            enable_long_term
            if enable_long_term is not None
            else self.should_read(query, user_id)
        )
        if not should_load:
            return {"profile": None, "memory_text": ""}

        profile = self._get_profile(user_id)
        sections = self.resolve_sections(query)
        memory_text = self.build_memory_text(profile, sections)
        print(f"[长期记忆] 读取画像：用户ID={user_id}，字段范围={sorted(sections)}，注入文本长度={len(memory_text)}")
        return {"profile": profile, "memory_text": memory_text}
    
    @staticmethod
    def should_read(query:str,user_id:int| None = None) -> bool:
        """判断本轮是否需要读取长期画像：明确个性化诉求优先，其次使用轻量语义分类。"""
        if LongTermMemory._looks_like_profile_read(query):
            print(f"[长期记忆] 读取意图：用户ID={user_id}，结果=read_profile，来源=规则")
            return True
        #todo: 轻量模型判断是否需要用户画像
        return False

    @staticmethod
    def _looks_like_profile_read(query: str) -> bool:
        """规则兜底：识别明确要求结合用户画像、实际情况、薄弱点或目标的请求。"""
        text = (query or "").strip()
        if not text:
            return False
        return any(pattern.search(text) for pattern in PROFILE_READ_PATTERNS)

    @staticmethod
    def should_write(user_message: str, user_id: int | None = None) -> bool:
        """判断本轮是否需要更新长期画像：明确画像事实优先，其次使用轻量语义分类。"""
        if LongTermMemory._looks_like_profile_update(user_message):
            print(f"[长期记忆] 写入意图：用户ID={user_id}，结果=write_profile，来源=规则")
            return True
        #todo: 轻量模型判断是否需要更新画像
        return False
    
    @staticmethod
    def _looks_like_profile_update(user_message: str) -> bool:
        """规则兜底：识别用户明确陈述的岗位、经验、目标、薄弱点、技能和学习偏好。"""
        text = (user_message or "").strip()
        if not text:
            return False
        return any(pattern.search(text) for pattern in PROFILE_UPDATE_PATTERNS)

    def _get_profile(self, user_id: int) -> UserProfile | None:
        """读取用户画像。"""
        return self.db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))

    @staticmethod
    def resolve_sections(query: str) -> set[str]:
        """判断本轮更需要哪组画像字段；不确定时读取全部。"""
        #todo: 轻量模型判断用户关心哪组字段
        return set()

    @staticmethod
    def build_memory_text(cls, profile: UserProfile | None, sections: set[str]) -> str:
        """把 UserProfile 转成 SystemMessage 文本。"""
        if profile is None:
            return ""

        lines: list[str] = []
        if "goal" in sections:
            cls._append_text(lines, "目标岗位", profile.target_job)
            cls._append_text(lines, "目标级别", profile.target_level)
            cls._append_text(lines, "工作经验", profile.years_experience)
            cls._append_text(lines, "学习目标", profile.learning_goal)
        if "ability" in sections:
            cls._append_list(lines, "已掌握技能", profile.target_skills)
            cls._append_list(lines, "薄弱点", profile.weak_topics)
        if "preference" in sections:
            cls._append_text(lines, "学习偏好", profile.learning_style)
        if "interview" in sections:
            cls._append_list(lines, "面试重点", profile.interview_focus)
        if sections == ALL_SECTIONS:
            cls._append_text(lines, "长期摘要", profile.long_term_summary)

        if not lines:
            return ""
        return "\n".join([
            "【用户长期画像】",
            *lines,
            "请仅将这些信息作为回答背景，不要主动说明你读取了长期记忆。",
        ])
    
   
