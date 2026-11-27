"""
core 对外导出：统一异常、统一抛错函数、统一异常处理注册。
"""

from .exceptions import AppException, raise_error

__all__ = [
    "AppException",
    "raise_error"
]
