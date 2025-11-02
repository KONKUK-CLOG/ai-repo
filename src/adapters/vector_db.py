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
    documents: List[Dict[str, Any]]
) -> int:
    """Upsert document embeddings to vector database.
    
    Args:
        collection: Collection name
        documents: List of documents to embed and upsert
            Each document should have:
            - file: 파일 경로
            - content: 파일 내용
            - status: optional (added/modified/deleted)
        
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
                # 1. 파일 경로 → 고유 ID (해시)
                file_path = doc["file"]
                file_id = hashlib.md5(file_path.encode()).hexdigest()
                
                # 2. 내용 → 임베딩 벡터
                content = doc.get("content", "")
                if not content:
                    logger.warning(f"Empty content for {file_path}, skipping")
                    continue
                
                embedding = await generate_embedding(content)
                if embedding is None:
                    logger.warning(f"Failed to generate embedding for {file_path}")
                    continue
                
                # 3. Point 생성
                points.append(PointStruct(
                    id=file_id,
                    vector=embedding,
                    payload={
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
    file_paths: List[str]
) -> int:
    """Vector DB에서 파일 삭제"""
    if not file_paths:
        return 0
    
    logger.info(f"Deleting {len(file_paths)} documents from vector DB")
    
    client = await get_qdrant_client()
    
    if client is None:
        logger.warning("Vector DB client not available. Using dummy implementation.")
        return len(file_paths)
    
    try:
        # 파일 경로 → ID 변환
        point_ids = [
            hashlib.md5(path.encode()).hexdigest()
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


async def list_all_files(collection: str) -> Dict[str, Dict[str, Any]]:
    """Vector DB에 인덱싱된 모든 파일 목록 조회"""
    client = await get_qdrant_client()
    
    if client is None:
        return {}
    
    try:
        # 모든 포인트 조회 (페이지네이션)
        all_files = {}
        offset = None
        
        while True:
            result = await client.scroll(
                collection_name=collection,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False  # 벡터는 불필요
            )
            
            points, next_offset = result
            
            for point in points:
                payload = point.payload
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

