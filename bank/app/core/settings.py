from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str
    DEEPSEEK_MODEL: str
    DEEPSEEK_TEMPERATURE: float
    DEEPSEEK_MAX_TOKENS: int
    mysql_url: str   # SQLAlchemy 风格数据库连接串（如 mysql+pymysql://...）
    redis_host: str  # Redis 服务器地址
    redis_port: int  # Redis 服务器端口
    redis_db: int  # Redis 数据库编号
    redis_password: str  # Redis 密码
    qdrant_host: str  # Qdrant 服务地址
    qdrant_port: int  # Qdrant 服务端口
    working_memory_ttl_seconds: int  # 工作记忆 Redis TTL 秒数，默认 3 天
    instant_memory_max_chars: int  # 短期记忆注入 Prompt 前的字符预算上限
    instant_memory_limit: int  # 短期记忆最大条数，默认 8
    working_memory_ttl_seconds: int  # 工作记忆 Redis TTL 秒数，默认 28800 秒，即 8 小时
    volc_access_key: str  # 火山引擎 Access Key（OCR 调用，扫描版 PDF 兜底）
    volc_secret_key: str  # 火山引擎 Secret Key
    volc_region: str  # 火山引擎服务地域（如 cn-north-1）
    dashscope_api_key: str  # 阿里百炼千问模型秘钥
settings = Settings()