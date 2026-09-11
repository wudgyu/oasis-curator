"""
Oasis Curator - FastAPI 应用入口

启动命令：uvicorn app.main:app --reload
交互文档：http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database import engine, Base

# 导入所有模型，确保 create_all 能发现它们
from app.models import tenant, organization, role, user, document, conversation  # noqa: F401

# 导入 API 路由
from app.api.auth import router as auth_router
from app.api.tenants import router as tenants_router
from app.api.orgs import router as orgs_router
from app.api.users import router as users_router
from app.api.roles import router as roles_router
from app.api.iam_config import router as iam_router
from app.api.documents import router as documents_router
from app.api.qa import router as qa_router
from app.api.conversations import router as conversations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时自动建表"""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.APP_NAME + " API",
    description="绿洲馆长 - 多租户 AI 文档平台后端服务",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS 中间件：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router)
app.include_router(tenants_router)
app.include_router(orgs_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(iam_router)
app.include_router(documents_router)
app.include_router(qa_router)
app.include_router(conversations_router)


@app.get("/api/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": settings.APP_NAME}