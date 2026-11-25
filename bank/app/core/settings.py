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

settings = Settings()