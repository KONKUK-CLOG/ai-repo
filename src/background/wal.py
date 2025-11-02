"""Write-Ahead Log (WAL) for tracking all index updates.

WAL 패턴:
1. 모든 업데이트 작업을 로그에 먼저 기록
2. Content는 별도 파일로 저장 (효율성)
3. 작업 실행 후 성공/실패 상태 업데이트
4. 정기적으로 실패한 작업 재시도
5. 로그를 통한 감사 추적 및 복구
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class WriteAheadLog:
    """Write-Ahead Log 관리자
    
    구조:
    - data/wal.jsonl: 메타데이터 로그
    - data/wal_content/{id}.txt: 실제 파일 내용
    """
    
    def __init__(self, log_file: str = "data/wal.jsonl"):
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Content 저장 디렉토리
        self.content_dir = self.log_file.parent / "wal_content"
        self.content_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = asyncio.Lock()
    
    async def append(self, operation: Dict[str, Any]) -> str:
        """작업을 로그에 추가
        
        Args:
            operation: 작업 정보
                - type: "upsert" or "delete"
                - file: 파일 경로
                - content: 파일 내용 (upsert만, 별도 파일로 저장)
                - hash: 파일 해시
                
        Returns:
            로그 엔트리 ID
        """
        async with self._lock:
            log_id = f"{datetime.now().timestamp()}".replace(".", "_")
            
            # Content를 별도 파일로 저장
            content = operation.get("content", "")
            content_file_path = None
            
            if content:
                content_file = self.content_dir / f"{log_id}.txt"
                try:
                    content_file.write_text(content, encoding='utf-8')
                    content_file_path = f"wal_content/{log_id}.txt"
                    logger.debug(f"WAL: Saved content to {content_file_path}")
                except Exception as e:
                    logger.error(f"Failed to save content file: {e}")
                    # Content 저장 실패해도 메타데이터는 로깅
            
            log_entry = {
                "id": log_id,
                "timestamp": datetime.now().isoformat(),
                "operation": operation["type"],
                "file": operation["file"],
                "hash": operation.get("hash"),
                "content_file": content_file_path,  # 별도 파일 경로
                "content_length": len(content),
                "status": "pending"
            }
            
            # 메타데이터 로그 파일에 추가
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
            
            logger.debug(f"WAL: Logged {operation['type']} for {operation['file']}")
            return log_entry["id"]
    
    async def mark_success(self, entry_id: str):
        """작업 성공 표시"""
        await self._update_status(entry_id, "success")
    
    async def mark_failure(self, entry_id: str, error: str):
        """작업 실패 표시"""
        await self._update_status(entry_id, "failed", error)
    
    async def _update_status(self, entry_id: str, status: str, error: Optional[str] = None):
        """로그 엔트리 상태 업데이트"""
        async with self._lock:
            # 로그 파일 읽기
            if not self.log_file.exists():
                return
            
            lines = []
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 해당 엔트리 찾아서 업데이트
            updated = False
            with open(self.log_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip():
                        entry = json.loads(line)
                        if entry["id"] == entry_id:
                            entry["status"] = status
                            entry["completed_at"] = datetime.now().isoformat()
                            if error:
                                entry["error"] = error
                            updated = True
                        f.write(json.dumps(entry) + '\n')
            
            if updated:
                logger.debug(f"WAL: Updated {entry_id} to {status}")
    
    async def get_failed_operations(self) -> List[Dict[str, Any]]:
        """실패한 작업 목록 조회"""
        if not self.log_file.exists():
            return []
        
        failed_ops = []
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry["status"] == "failed":
                        failed_ops.append(entry)
        
        return failed_ops
    
    async def get_pending_operations(self) -> List[Dict[str, Any]]:
        """미완료 작업 목록 조회"""
        if not self.log_file.exists():
            return []
        
        pending_ops = []
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry["status"] == "pending":
                        pending_ops.append(entry)
        
        return pending_ops
    
    async def cleanup_old_entries(self, days: int = 7):
        """오래된 성공 엔트리 정리 (메타데이터 + content 파일)"""
        if not self.log_file.exists():
            return
        
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        
        async with self._lock:
            lines = []
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            kept = 0
            removed = 0
            removed_entry_ids = []
            
            with open(self.log_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip():
                        entry = json.loads(line)
                        entry_time = datetime.fromisoformat(entry["timestamp"])
                        
                        # 실패/대기 중인 것은 유지, 오래된 성공만 제거
                        if entry["status"] != "success" or entry_time > cutoff:
                            f.write(json.dumps(entry) + '\n')
                            kept += 1
                        else:
                            removed += 1
                            removed_entry_ids.append(entry["id"])
            
            # Content 파일도 삭제
            await self.cleanup_content_files(removed_entry_ids)
            
            logger.info(f"WAL cleanup: kept {kept}, removed {removed} entries")
    
    async def get_content(self, entry_id: str) -> Optional[str]:
        """로그 엔트리의 content 복원
        
        Args:
            entry_id: 로그 엔트리 ID
            
        Returns:
            파일 내용, 없으면 None
        """
        content_file = self.content_dir / f"{entry_id}.txt"
        
        if not content_file.exists():
            logger.warning(f"Content file not found: {content_file}")
            return None
        
        try:
            return content_file.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read content file {content_file}: {e}")
            return None
    
    async def get_operation_with_content(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """로그 엔트리에 content를 추가하여 반환
        
        Args:
            entry: 로그 엔트리 (메타데이터만)
            
        Returns:
            content가 포함된 완전한 operation
        """
        operation = entry.copy()
        
        if entry.get("content_file"):
            content = await self.get_content(entry["id"])
            if content:
                operation["content"] = content
        
        return operation
    
    async def get_statistics(self) -> Dict[str, int]:
        """로그 통계"""
        if not self.log_file.exists():
            return {"total": 0, "pending": 0, "success": 0, "failed": 0}
        
        stats = {"total": 0, "pending": 0, "success": 0, "failed": 0}
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    stats["total"] += 1
                    stats[entry["status"]] = stats.get(entry["status"], 0) + 1
        
        return stats
    
    async def cleanup_content_files(self, entry_ids: List[str]):
        """성공한 엔트리의 content 파일 삭제
        
        Args:
            entry_ids: 삭제할 엔트리 ID 리스트
        """
        for entry_id in entry_ids:
            content_file = self.content_dir / f"{entry_id}.txt"
            if content_file.exists():
                try:
                    content_file.unlink()
                    logger.debug(f"Deleted content file: {content_file}")
                except Exception as e:
                    logger.error(f"Failed to delete content file {content_file}: {e}")


# 전역 WAL 인스턴스
wal = WriteAheadLog()

