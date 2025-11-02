"""Background task scheduler using APScheduler.

스케줄러 관리:
- wal_recovery_task: 5분마다 실행 (실패한 WAL 작업 재시도)
- wal_cleanup_task: 1일마다 실행 (오래된 WAL 엔트리 정리)

주의:
- 전체 재인덱싱은 클라이언트(VSCode extension)가 주도
- 서버는 증분 업데이트만 처리
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

from src.background.tasks import wal_recovery_task, wal_cleanup_task

logger = logging.getLogger(__name__)

# 전역 스케줄러 인스턴스
scheduler: AsyncIOScheduler = None


def init_scheduler():
    """스케줄러 초기화 및 작업 등록"""
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return
    
    scheduler = AsyncIOScheduler()
    
    # 1. WAL 복구: 5분마다
    scheduler.add_job(
        wal_recovery_task,
        trigger=IntervalTrigger(minutes=5),
        id="wal_recovery",
        name="WAL Recovery",
        replace_existing=True,
        max_instances=1,  # 동시 실행 방지
        coalesce=True,    # 누락된 실행 병합
    )
    
    # 2. WAL 정리: 1일마다
    scheduler.add_job(
        wal_cleanup_task,
        trigger=IntervalTrigger(days=1),
        id="wal_cleanup",
        name="WAL Cleanup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    
    logger.info("Scheduler initialized with 2 background tasks")


def start_scheduler():
    """스케줄러 시작"""
    global scheduler
    
    if scheduler is None:
        init_scheduler()
    
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
        
        # 다음 실행 시간 로깅
        jobs = scheduler.get_jobs()
        for job in jobs:
            logger.info(f"Job '{job.name}' next run: {job.next_run_time}")


def shutdown_scheduler():
    """스케줄러 종료"""
    global scheduler
    
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down")


async def run_task_now(task_name: str):
    """특정 작업을 즉시 실행 (수동 트리거)
    
    Args:
        task_name: "wal_recovery", "wal_cleanup"
    """
    logger.info(f"Manually triggering task: {task_name}")
    
    if task_name == "wal_recovery":
        await wal_recovery_task()
    elif task_name == "wal_cleanup":
        await wal_cleanup_task()
    else:
        logger.error(f"Unknown task: {task_name}")

