"""Background tasks for WAL recovery and maintenance.

백그라운드 작업:
1. wal_recovery_task: 실패한 WAL 작업 재시도 (content 복원하여)
2. wal_cleanup_task: 오래된 WAL 엔트리 정리

주의:
- 서버는 사용자 로컬 파일에 접근 불가
- 전체 스캔/재인덱싱은 클라이언트(VSCode extension)가 수행
- WAL에 저장된 content로만 재시도 가능
"""
import asyncio
import logging
from datetime import datetime

from src.adapters import vector_db, graph_db
from src.server.settings import settings
from src.background.wal import wal

logger = logging.getLogger(__name__)


async def wal_recovery_task():
    """WAL 복구 작업: 실패한 작업 재시도
    
    WAL에 저장된 content를 복원하여 DB 업데이트 재시도
    - Vector DB: 임베딩 생성 및 Upsert
    - Graph DB: 코드 파싱 및 노드/관계 생성
    """
    logger.info("=== Starting WAL recovery task ===")
    
    try:
        # 실패한 작업 조회
        failed_ops = await wal.get_failed_operations()
        
        if not failed_ops:
            logger.info("No failed operations to recover")
            return
        
        logger.info(f"Found {len(failed_ops)} failed operations")
        
        recovered = 0
        failed = 0
        
        # 각 실패한 작업 재시도 (최대 10개)
        for op in failed_ops[:10]:
            try:
                logger.info(f"Retrying operation {op['id']} for {op['file']}")
                
                # WAL에서 content 복원
                content = await wal.get_content(op["id"])
                
                if not content:
                    logger.error(f"Cannot recover {op['file']} - content not found")
                    failed += 1
                    continue
                
                operation_type = op.get("operation", "upsert")
                
                if operation_type == "upsert":
                    # Vector DB 재시도
                    try:
                        await vector_db.upsert_embeddings(
                            collection=settings.VECTOR_DB_COLLECTION,
                            documents=[{
                                "file": op["file"],
                                "content": content,
                                "status": "recovered"
                            }]
                        )
                        logger.info(f"✅ Vector DB recovered for {op['file']}")
                    except Exception as e:
                        logger.error(f"❌ Vector DB recovery failed: {e}")
                        raise
                    
                    # Graph DB 재시도
                    try:
                        await graph_db.update_code_graph(
                            files=[op["file"]],
                            contents={op["file"]: content}
                        )
                        logger.info(f"✅ Graph DB recovered for {op['file']}")
                    except Exception as e:
                        logger.error(f"❌ Graph DB recovery failed: {e}")
                        raise
                
                elif operation_type == "delete":
                    # 삭제 작업 재시도
                    try:
                        await vector_db.delete_embeddings(
                            collection=settings.VECTOR_DB_COLLECTION,
                            file_paths=[op["file"]]
                        )
                        await graph_db.delete_file_nodes([op["file"]])
                        logger.info(f"✅ Deletion recovered for {op['file']}")
                    except Exception as e:
                        logger.error(f"❌ Deletion recovery failed: {e}")
                        raise
                
                # 성공 표시
                await wal.mark_success(op["id"])
                recovered += 1
                logger.info(f"Successfully recovered {op['file']}")
                
            except Exception as e:
                logger.error(f"Failed to recover operation {op['id']}: {e}")
                await wal.mark_failure(op["id"], str(e))
                failed += 1
        
        logger.info(f"=== WAL recovery completed: {recovered} recovered, {failed} failed ===")
        
    except Exception as e:
        logger.error(f"WAL recovery task failed: {e}", exc_info=True)


async def wal_cleanup_task():
    """WAL 정리 작업: 7일 이상 된 성공 엔트리 제거"""
    logger.info("=== Starting WAL cleanup task ===")
    
    try:
        await wal.cleanup_old_entries(days=7)
        
        # 통계 출력
        stats = await wal.get_statistics()
        logger.info(f"WAL stats: {stats}")
        
    except Exception as e:
        logger.error(f"WAL cleanup task failed: {e}", exc_info=True)

