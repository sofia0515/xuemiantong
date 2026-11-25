from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    DEEPSEEK_API_KEY: str
    DEEPSEEK_BASE_URL: str
    DEEPSEEK_MODEL: str
    DEEPSEEK_TEMPERATURE: float
    DEEPSEEK_MAX_TOKENS: int

settings = Settings()