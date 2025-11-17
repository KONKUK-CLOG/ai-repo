"""FastAPI application entry point."""
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.server.routers import health, diffs, agent, auth
from src.server.settings import settings
from src.background.scheduler import start_scheduler, shutdown_scheduler, run_task_now
from src.server.deps import get_java_service_identity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# FastAPI 생명주기 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 코드"""
    # 시작 시
    logger.info("Starting application...")
    
    # 백그라운드 스케줄러 시작
    start_scheduler()
    logger.info("Background scheduler started")
    
    yield
    
    # 종료 시
    logger.info("Shutting down application...")
    shutdown_scheduler()
    logger.info("Background scheduler stopped")


# Create FastAPI app
app = FastAPI(
    title="TS-LLM-MCP Bridge",
    description="REST API bridge for TypeScript client to Python MCP tools",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan  # 생명주기 추가
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)  # Auth router (no API key required)
app.include_router(diffs.router)
app.include_router(agent.router)

# 조건부: 개발 환경에서만 직접 툴 실행 엔드포인트 활성화
if settings.ENABLE_DIRECT_TOOLS:
    from src.server.routers import commands
    app.include_router(commands.router)
    logger.warning("⚠️  Direct tool execution endpoints enabled (development mode)")


@app.get("/")
async def root():
    """Root endpoint.
    
    Returns:
        Welcome message with API info
    """
    return {
        "message": "TS-LLM-MCP Bridge API",
        "version": "1.0.0",
        "docs": "/docs"
    }


# Admin endpoints for manual triggers
@app.post("/api/v1/admin/wal-recovery")
async def trigger_wal_recovery(
    _: dict = Depends(get_java_service_identity),
):
    """수동으로 WAL 복구 트리거 (관리자 전용)
    
    실패한 WAL 작업을 즉시 재시도합니다.
    """
    asyncio.create_task(run_task_now("wal_recovery"))
    return {"message": "WAL recovery task triggered"}


@app.post("/api/v1/admin/wal-cleanup")
async def trigger_wal_cleanup(
    _: dict = Depends(get_java_service_identity),
):
    """수동으로 WAL 정리 트리거 (관리자 전용)
    
    7일 이상 된 성공한 WAL 엔트리를 삭제합니다.
    """
    asyncio.create_task(run_task_now("wal_cleanup"))
    return {"message": "WAL cleanup task triggered"}


@app.get("/api/v1/admin/wal-stats")
async def get_wal_stats(
    _: dict = Depends(get_java_service_identity),
):
    """WAL 통계 조회
    
    Returns:
        전체 WAL 엔트리 수, 상태별 카운트
    """
    from src.background.wal import wal
    stats = await wal.get_statistics()
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.server.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=True
    )

