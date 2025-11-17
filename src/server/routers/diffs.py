"""Diff application endpoints with WAL (Write-Ahead Log).

코드 변경사항(diff)을 벡터 DB와 그래프 DB에 증분 반영하는 엔드포인트를 제공합니다.

WAL 패턴 적용:
- 모든 업데이트를 로그에 먼저 기록
- 실패한 작업은 백그라운드에서 재시도
- 감사 추적 및 복구 메커니즘

주요 기능:
- 실시간 코드 인덱싱: VS Code 등의 IDE에서 파일 변경 감지 시 자동 인덱스 업데이트
- 2가지 입력 형식 지원: Unified diff (Git 표준) 또는 Files array (구조화)
- 증분 업데이트: 변경된 파일만 처리하여 효율성 극대화

엔드포인트:
- POST /api/v1/diffs/apply: 코드 diff를 벡터/그래프 인덱스에 반영

사용 케이스:
1. IDE 확장: 개발자가 코드 작성 시 실시간 인덱싱
2. Git 훅: 커밋 후 자동 인덱스 업데이트
3. CI/CD: 파이프라인에서 배포 전 인덱스 동기화
"""
from fastapi import APIRouter, Depends, HTTPException, status
from src.server.deps import get_current_user
from src.server.schemas import DiffApplyRequest, DiffApplyResult
from src.models.user import User
from src.server.settings import settings
from src.adapters import vector_db, graph_db
from src.background.wal import wal
import logging
import hashlib

router = APIRouter(prefix="/api/v1/diffs", tags=["diffs"])
logger = logging.getLogger(__name__)


@router.post("/apply", response_model=DiffApplyResult)
async def apply_diff(
    request: DiffApplyRequest,
    user: User = Depends(get_current_user)
) -> DiffApplyResult:
    """코드 diff를 벡터 DB와 그래프 DB에 적용합니다.
    
    이 엔드포인트는 코드 변경사항을 실시간으로 인덱스에 반영하여
    LLM이 최신 코드를 참조할 수 있도록 합니다.
    
    2가지 입력 모드 지원:
    1. unified: Git unified diff 패치 문자열 (Git 표준 형식)
       - 예: "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@\n-old\n+new"
       - 사용 케이스: Git 훅, CLI 도구
       
    2. files: 파일 변경사항 배열 (구조화된 형식)
       - 예: [{"path": "src/main.py", "status": "modified", "after": "..."}]
       - 사용 케이스: IDE 확장, 프로그래밍 방식 호출
    
    처리 과정:
    1. 입력 검증 (형식, 크기 제한)
    2. Diff 파싱 (unified 또는 files)
    3. 벡터 DB 업데이트 (의미적 코드 검색용)
    4. 그래프 DB 업데이트 (코드 관계 추적용)
    5. 통계 반환
    
    벡터 DB vs 그래프 DB:
    - 벡터 DB: 코드 내용을 임베딩으로 변환하여 의미적 검색 가능
      예: "사용자 인증 로직" 검색 → 관련 코드 찾기
    - 그래프 DB: 코드 간 관계(함수 호출, import 등) 추적
      예: 함수 A → 함수 B 호출 관계
    
    Args:
        request: Diff 적용 요청
            - unified: Unified diff 문자열 (선택)
            - files: 파일 변경 배열 (선택)
            둘 중 하나는 반드시 제공되어야 함
        user: 인증된 사용자 (헤더에서 자동 추출 및 검증)
        
    Returns:
        Diff 적용 결과 및 통계
        - ok: 성공 여부
        - files_processed: 처리된 파일 수
        - embeddings_upserted: 벡터 DB 업데이트 수
        - graph_nodes_updated: 그래프 DB 노드 업데이트 수
        - stats: 추가 통계 (모드, 배치 크기)
        
    Raises:
        HTTPException:
            - 400: 입력이 유효하지 않음 또는 diff가 너무 큼
            - 500: 처리 중 에러 발생
    
    Example (unified 모드):
        >>> POST /api/v1/diffs/apply
        >>> Headers: {"Authorization": "Bearer <jwt-token>"}
        >>> Body: {
        >>>     "unified": "--- a/test.py\n+++ b/test.py\n..."
        >>> }
        >>> Response: {
        >>>     "ok": true,
        >>>     "files_processed": 1,
        >>>     "embeddings_upserted": 1,
        >>>     "graph_nodes_updated": 1,
        >>>     "stats": {"mode": "unified", "batch_size": 100}
        >>> }
    
    Example (files 모드):
        >>> Body: {
        >>>     "files": [
        >>>         {
        >>>             "path": "src/main.py",
        >>>             "status": "modified",
        >>>             "before": "def old(): pass",
        >>>             "after": "def new(): pass"
        >>>         }
        >>>     ]
        >>> }
    """
    # 1. 입력 검증
    # 둘 중 하나는 반드시 제공되어야 함
    if not request.unified and not request.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'unified' or 'files' must be provided"
        )
    
    # 2. 크기 제한 확인 (DoS 공격 방지)
    if request.unified and len(request.unified.encode()) > settings.MAX_DIFF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Diff exceeds maximum size of {settings.MAX_DIFF_BYTES} bytes"
        )
    
    # 3. 통계 변수 초기화
    files_processed = 0
    embeddings_upserted = 0
    graph_nodes_updated = 0
    
    try:
        # 4-A. Unified diff 모드 처리
        if request.unified:
            logger.info("Processing unified diff")
            
            # Unified diff 파싱 (더미 구현)
            # 실제 구현 시에는 unidiff 라이브러리 사용 권장
            lines = request.unified.split("\n")
            
            # --- 와 +++ 로 시작하는 라인에서 파일 경로 추출
            # 형식: --- a/path/to/file.py
            #       +++ b/path/to/file.py
            affected_files = [
                line.split()[1] for line in lines 
                if line.startswith("+++") or line.startswith("---")
            ]
            
            # 각 파일마다 --- 와 +++ 2개 라인이 있으므로 중복 제거 후 /2
            unique_files = list(set(affected_files))
            files_processed = len(unique_files) // 2
            
            # ⚠️ Unified diff 모드는 파일 전체 내용을 알 수 없음
            # 실제 파일 시스템에서 읽어야 함
            logger.warning("Unified diff mode: file contents not provided, skipping vector DB update")
            embeddings_upserted = 0
            
            # WAL에 그래프 업데이트 작업 로깅
            wal_entries = {}
            for file_path in unique_files:
                wal_id = await wal.append({
                    "type": "graph_update",
                    "file": file_path,
                    "content": None,
                    "hash": hashlib.md5(request.unified.encode()).hexdigest()
                })
                wal_entries[file_path] = wal_id
            
            # 그래프 DB 업데이트 (파일 경로만으로도 가능)
            try:
                graph_nodes_updated = await graph_db.update_code_graph(
                    files=unique_files,
                    contents=None,  # 내용 없이 파일 노드만 업데이트
                    user_id=user.id  # 사용자 ID 전달
                )
                
                # 성공한 파일들의 WAL 표시
                for file_path in unique_files:
                    if file_path in wal_entries:
                        await wal.mark_success(wal_entries[file_path])
                        
            except Exception as e:
                logger.error(f"Graph DB update failed in unified mode: {e}")
                graph_nodes_updated = 0
                
                # 실패한 파일들의 WAL 표시
                for file_path in unique_files:
                    if file_path in wal_entries:
                        await wal.mark_failure(wal_entries[file_path], str(e))
        
        # 4-B. Files array 모드 처리
        elif request.files:
            logger.info(f"Processing {len(request.files)} file changes")
            files_processed = len(request.files)
            
            # 벡터 DB용 문서 및 그래프 DB용 파일 경로와 내용 준비
            documents = []
            file_contents = {}
            file_paths = []
            deleted_files = []
            wal_entries = {}  # {file_path: wal_id}
            
            for file_item in request.files:
                file_paths.append(file_item.path)
                
                if file_item.status == "deleted":
                    # 삭제된 파일 따로 처리
                    deleted_files.append(file_item.path)
                    
                    # 삭제 작업도 WAL에 로깅
                    wal_id = await wal.append({
                        "type": "delete",
                        "file": file_item.path,
                        "hash": None,
                        "user_id": user.id  # 사용자 ID 전달
                    })
                    wal_entries[file_item.path] = wal_id
                else:
                    # 변경 후 내용 우선, 없으면 변경 전 내용 사용
                    content = file_item.after or file_item.before or ""
                    
                    if content:
                        # WAL에 먼저 로깅 (content 포함)
                        wal_id = await wal.append({
                            "type": "upsert",
                            "file": file_item.path,
                            "content": content,
                            "hash": hashlib.md5(content.encode()).hexdigest(),
                            "user_id": user.id  # 사용자 ID 전달
                        })
                        wal_entries[file_item.path] = wal_id
                        
                        documents.append({
                            "file": file_item.path,
                            "content": content,
                            "status": file_item.status
                        })
                        
                        file_contents[file_item.path] = content
            
            # 벡터 DB 업데이트 (코드 내용을 임베딩으로 변환하여 저장)
            try:
                embeddings_upserted = await vector_db.upsert_embeddings(
                    collection=settings.VECTOR_DB_COLLECTION,
                    documents=documents,
                    user_id=user.id  # 사용자 ID 전달
                )
                logger.info(f"Vector DB: upserted {embeddings_upserted} embeddings")
                
                # 성공한 파일들의 WAL 표시
                for doc in documents:
                    if doc["file"] in wal_entries:
                        await wal.mark_success(wal_entries[doc["file"]])
                        
            except Exception as e:
                logger.error(f"Vector DB upsert failed: {e}")
                embeddings_upserted = 0
                
                # 실패한 파일들의 WAL 표시
                for doc in documents:
                    if doc["file"] in wal_entries:
                        await wal.mark_failure(wal_entries[doc["file"]], str(e))
            
            # 삭제된 파일 처리
            if deleted_files:
                try:
                    await vector_db.delete_embeddings(
                        collection=settings.VECTOR_DB_COLLECTION,
                        file_paths=deleted_files,
                        user_id=user.id  # 사용자 ID 전달
                    )
                    await graph_db.delete_file_nodes(deleted_files, user_id=user.id)
                    logger.info(f"Deleted {len(deleted_files)} files from DBs")
                    
                    # 성공한 삭제 작업의 WAL 표시
                    for file_path in deleted_files:
                        if file_path in wal_entries:
                            await wal.mark_success(wal_entries[file_path])
                            
                except Exception as e:
                    logger.error(f"Failed to delete files: {e}")
                    
                    # 실패한 삭제 작업의 WAL 표시
                    for file_path in deleted_files:
                        if file_path in wal_entries:
                            await wal.mark_failure(wal_entries[file_path], str(e))
            
            # 그래프 DB 업데이트 (파일 간 관계, 함수 호출 등 추적)
            try:
                graph_nodes_updated = await graph_db.update_code_graph(
                    files=[f for f in file_paths if f not in deleted_files],
                    contents=file_contents,  # 파일 내용 전달
                    user_id=user.id  # 사용자 ID 전달
                )
                logger.info(f"Graph DB: updated {graph_nodes_updated} nodes")
            except Exception as e:
                logger.error(f"Graph DB update failed: {e}")
                graph_nodes_updated = 0
        
        # 5. 결과 반환
        return DiffApplyResult(
            ok=True,
            files_processed=files_processed,
            embeddings_upserted=embeddings_upserted,
            graph_nodes_updated=graph_nodes_updated,
            stats={
                "mode": "unified" if request.unified else "files",
                "batch_size": settings.EMBED_BATCH_SIZE
            }
        )
        
    except Exception as e:
        # 6. 에러 처리
        logger.error(f"Error applying diff: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply diff: {str(e)}"
        )

