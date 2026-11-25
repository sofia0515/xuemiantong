from typing import Optional
from sqlalchemy.orm import Session
from app.db.tables import UserProfile



class UserProfileService:
    """用户个人信息服务。"""

    @staticmethod
    def get_profile_dict(db: Session, user_id: int) -> dict:
        """读取用户信息转字典（缺失字段使用默认值）"""
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        
        return {
            "target_job": profile.target_job if profile and profile.target_job else "未指定",
            "years_experience": profile.years_experience if profile and profile.years_experience else "未指定",
            "target_level": profile.target_level if profile and profile.target_level else "未指定",
            "target_skills": profile.target_skills if profile and profile.target_skills else [],
            "weak_topics": profile.weak_topics if profile and profile.weak_topics else [],
            "learning_goal": profile.learning_goal if profile and profile.learning_goal else "未指定",
            "learning_style": profile.learning_style if profile and profile.learning_style else "未指定",
            "interview_focus": profile.interview_focus if profile and profile.interview_focus else [],
            "long_term_summary": profile.long_term_summary if profile and profile.long_term_summary else "未指定",
        }

    @staticmethod
    def format_profile_for_injection(profile_dict: dict) -> dict:
        """格式化用户信息用于提示词注入（数组→文本）
        
        转换规则：["Python", "FastAPI"] → "Python、FastAPI"
        """
        target_skills = profile_dict.get("target_skills", [])
        target_skills_str = "、".join(target_skills) if isinstance(target_skills, list) and target_skills else "未指定"
        
        weak_topics = profile_dict.get("weak_topics", [])
        weak_topics_str = "、".join(weak_topics) if isinstance(weak_topics, list) and weak_topics else "未指定"
        
        interview_focus = profile_dict.get("interview_focus", [])
        interview_focus_str = "、".join(interview_focus) if isinstance(interview_focus, list) and interview_focus else "未指定"
        
        return {
            "target_job": str(profile_dict.get("target_job", "未指定")),
            "years_experience": str(profile_dict.get("years_experience", "未指定")),
            "target_level": str(profile_dict.get("target_level", "未指定")),
            "target_skills": target_skills_str,
            "weak_topics": weak_topics_str,
            "learning_goal": str(profile_dict.get("learning_goal", "未指定")),
            "learning_style": str(profile_dict.get("learning_style", "未指定")),
            "interview_focus": interview_focus_str,
            "long_term_summary": str(profile_dict.get("long_term_summary", "未指定")),
        }
