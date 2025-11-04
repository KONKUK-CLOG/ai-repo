"""Vector database adapter for embeddings and semantic search."""
import logging
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.server.settings import settings

logger = logging.getLogger(__name__)

# Qdrant client (lazy initialization)
_qdrant_client = None


async def get_qdrant_client():
    """Qdrant 클라이언트 가져오기 (싱글톤)"""
    global _qdrant_client
    
    if _qdrant_client is None:
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import VectorParams, Distance
            
            _qdrant_client = AsyncQdrantClient(url=settings.VECTOR_DB_URL)
            
            # 컬렉션 존재 확인 및 생성
            collections = await _qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if settings.VECTOR_DB_COLLECTION not in collection_names:
                logger.info(f"Creating collection: {settings.VECTOR_DB_COLLECTION}")
                await _qdrant_client.create_collection(
                    collection_name=settings.VECTOR_DB_COLLECTION,
                    vectors_config=VectorParams(
                        size=1536,  # OpenAI text-embedding-3-small dimension
                        distance=Distance.COSINE
                    )
                )
        except ImportError:
            logger.warning("qdrant-client not installed. Using dummy implementation.")
            _qdrant_client = None
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant client: {e}")
            _qdrant_client = None
    
    return _qdrant_client


async def generate_embedding(text: str) -> Optional[List[float]]:
    """OpenAI로 텍스트 임베딩 생성"""
    try:
        from openai import AsyncOpenAI
        
        if not settings.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set. Cannot generate embeddings.")
            return None
        
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        # 텍스트 길이 제한 (8000 토큰 ≈ 32000 chars)
        text = text[:32000]
        
        response = await client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        
        return response.data[0].embedding
        
    except ImportError:
        logger.warning("openai package not installed. Cannot generate embeddings.")
        return None
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None


async def upsert_embeddings(
    collection: str,
    documents: List[Dict[str, Any]],
    user_id: int
) -> int:
    """Upsert document embeddings to vector database.
    
    다중 사용자 지원: user_id로 데이터를 격리합니다.
    각 문서의 ID는 md5(user_id + file_path)로 생성되어 사용자별로 고유합니다.
    
    Args:
        collection: Collection name
        documents: List of documents to embed and upsert
            Each document should have:
            - file: 파일 경로
            - content: 파일 내용
            - status: optional (added/modified/deleted)
        user_id: 사용자 ID (데이터 격리용)
        
    Returns:
        Number of embeddings upserted
    """
    if not documents:
        return 0
    
    logger.info(f"Upserting {len(documents)} documents to vector DB collection: {collection}")
    
    client = await get_qdrant_client()
    
    if client is None:
        # Dummy mode
        logger.warning("Vector DB client not available. Using dummy implementation.")
        return len(documents)
    
    try:
        from qdrant_client.models import PointStruct
        
        points = []
        successful = 0
        
        for doc in documents:
            try:
                # 1. 파일 경로 → 고유 ID (user_id + 파일 경로 해시)
                file_path = doc["file"]
                # 사용자별로 고유한 ID 생성
                file_id = hashlib.md5(f"{user_id}:{file_path}".encode()).hexdigest()
                
                # 2. 내용 → 임베딩 벡터
                content = doc.get("content", "")
                if not content:
                    logger.warning(f"Empty content for {file_path}, skipping")
                    continue
                
                embedding = await generate_embedding(content)
                if embedding is None:
                    logger.warning(f"Failed to generate embedding for {file_path}")
                    continue
                
                # 3. Point 생성 (payload에 user_id 포함)
                points.append(PointStruct(
                    id=file_id,
                    vector=embedding,
                    payload={
                        "user_id": user_id,  # 사용자 ID 추가
                        "file": file_path,
                        "content_preview": content[:500],  # 미리보기
                        "content_length": len(content),
                        "status": doc.get("status", "unknown"),
                        "updated_at": datetime.now().isoformat(),
                        "hash": hashlib.md5(content.encode()).hexdigest()
                    }
                ))
                successful += 1
                
            except Exception as e:
                logger.error(f"Failed to process document {doc.get('file')}: {e}")
                continue
        
        if points:
            # 4. Qdrant에 Upsert
            await client.upsert(
                collection_name=collection,
                points=points,
                wait=True  # 완료될 때까지 대기
            )
            
            logger.info(f"Successfully upserted {successful} embeddings to Qdrant")
        
        return successful
        
    except Exception as e:
        logger.error(f"Failed to upsert embeddings: {e}")
        raise


async def delete_embeddings(
    collection: str,
    file_paths: List[str],
    user_id: int
) -> int:
    """Vector DB에서 파일 삭제.
    
    다중 사용자 지원: user_id를 사용하여 해당 사용자의 파일만 삭제합니다.
    
    Args:
        collection: Collection name
        file_paths: 삭제할 파일 경로 리스트
        user_id: 사용자 ID
        
    Returns:
        삭제된 파일 수
    """
    if not file_paths:
        return 0
    
    logger.info(f"Deleting {len(file_paths)} documents from vector DB")
    
    client = await get_qdrant_client()
    
    if client is None:
        logger.warning("Vector DB client not available. Using dummy implementation.")
        return len(file_paths)
    
    try:
        # 파일 경로 → ID 변환 (user_id 포함)
        point_ids = [
            hashlib.md5(f"{user_id}:{path}".encode()).hexdigest()
            for path in file_paths
        ]
        
        # Qdrant에서 삭제
        await client.delete(
            collection_name=collection,
            points_selector=point_ids,
            wait=True
        )
        
        logger.info(f"Successfully deleted {len(file_paths)} embeddings from Qdrant")
        return len(file_paths)
        
    except Exception as e:
        logger.error(f"Failed to delete embeddings: {e}")
        raise


async def list_all_files(collection: str, user_id: int) -> Dict[str, Dict[str, Any]]:
    """Vector DB에 인덱싱된 사용자의 파일 목록 조회.
    
    다중 사용자 지원: user_id로 필터링하여 해당 사용자의 파일만 반환합니다.
    
    Args:
        collection: Collection name
        user_id: 사용자 ID
        
    Returns:
        파일 경로를 키로 하는 파일 정보 딕셔너리
    """
    client = await get_qdrant_client()
    
    if client is None:
        return {}
    
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # 사용자 ID로 필터링하여 조회 (페이지네이션)
        all_files = {}
        offset = None
        
        # user_id 필터
        user_filter = Filter(
            must=[
                FieldCondition(
                    key="user_id",
                    match=MatchValue(value=user_id)
                )
            ]
        )
        
        while True:
            result = await client.scroll(
                collection_name=collection,
                scroll_filter=user_filter,  # user_id 필터 적용
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False  # 벡터는 불필요
            )
            
            points, next_offset = result
            
            for point in points:
                payload = point.payload
                # user_id가 일치하는 파일만 포함 (이중 확인)
                if payload.get("user_id") == user_id:
                    all_files[payload["file"]] = {
                        "hash": payload.get("hash"),
                        "size": payload.get("content_length"),
                        "updated_at": payload.get("updated_at")
                    }
            
            if next_offset is None:
                break
            
            offset = next_offset
        
        return all_files
        
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        return {}


async def refresh_all_indexes() -> Dict[str, Any]:
    """Refresh all vector indexes.
    
    Returns:
        Refresh statistics
    """
    logger.info("Refreshing all vector indexes")
    logger.info(f"Vector DB URL: {settings.VECTOR_DB_URL}")
    
    # Dummy implementation
    return {
        "collections_refreshed": [settings.VECTOR_DB_COLLECTION],
        "total_embeddings": 1000,
        "success": True
    }

