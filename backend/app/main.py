"""
Oasis Curator - FastAPI 应用入口

启动命令：uvicorn app.main:app --reload
交互文档：http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine, Base

# 导入所有模型，确保 create_all 能发现它们
from app.models import tenant, user  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时自动建表"""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Oasis Curator API",
    description="绿洲馆长 - 多租户 AI 文档平台后端服务",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "Oasis Curator"}