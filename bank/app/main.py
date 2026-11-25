#预热缓存
from app.db.database import engine, get_db
from fastapi import  FastAPI
from contextlib import asynccontextmanager
from app.services.prompt_template_service import prompt_template_manager

@asynccontextmanager
async def lifespan(_: FastAPI):
    # 预热 Redis：把生效中的提示词模板加载到缓存（Redis不可用时函数内部会自动跳过）
    db = next(get_db())
    try:
        prompt_template_manager.load_all_effective_to_redis(db)
    finally:
        db.close()
    yield

app = FastAPI(title="User CRUD API", version="1.0.0", lifespan=lifespan)