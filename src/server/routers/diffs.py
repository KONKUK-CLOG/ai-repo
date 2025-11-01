"""Diff application endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from src.server.deps import verify_api_key
from src.server.schemas import DiffApplyRequest, DiffApplyResult
from src.server.settings import settings
from src.adapters import vector_db, graph_db
import logging

router = APIRouter(prefix="/api/v1/diffs", tags=["diffs"])
logger = logging.getLogger(__name__)


@router.post("/apply", response_model=DiffApplyResult)
async def apply_diff(
    request: DiffApplyRequest,
    api_key: str = Depends(verify_api_key)
) -> DiffApplyResult:
    """Apply code diff to vector and graph indexes.
    
    Supports two input modes:
    1. unified: Unified diff patch string
    2. files: Array of file changes
    
    Args:
        request: Diff application request
        api_key: Validated API key
        
    Returns:
        Result with statistics
        
    Raises:
        HTTPException: 400 if request is invalid or diff too large
    """
    # Validate input
    if not request.unified and not request.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'unified' or 'files' must be provided"
        )
    
    # Check size limit
    if request.unified and len(request.unified.encode()) > settings.MAX_DIFF_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Diff exceeds maximum size of {settings.MAX_DIFF_BYTES} bytes"
        )
    
    files_processed = 0
    embeddings_upserted = 0
    graph_nodes_updated = 0
    
    try:
        # Process unified diff
        if request.unified:
            logger.info("Processing unified diff")
            # Parse unified diff (dummy implementation)
            lines = request.unified.split("\n")
            affected_files = [
                line.split()[1] for line in lines 
                if line.startswith("+++") or line.startswith("---")
            ]
            files_processed = len(set(affected_files)) // 2  # +++ and --- per file
            
            # Update vector DB
            embeddings_upserted = await vector_db.upsert_embeddings(
                collection=settings.VECTOR_DB_COLLECTION,
                documents=[{"file": f, "content": "dummy"} for f in affected_files]
            )
            
            # Update graph DB
            graph_nodes_updated = await graph_db.update_code_graph(
                files=affected_files
            )
        
        # Process files array
        elif request.files:
            logger.info(f"Processing {len(request.files)} file changes")
            files_processed = len(request.files)
            
            # Prepare documents for vector DB
            documents = []
            file_paths = []
            for file_item in request.files:
                file_paths.append(file_item.path)
                if file_item.status != "deleted":
                    content = file_item.after or file_item.before or ""
                    documents.append({
                        "file": file_item.path,
                        "content": content,
                        "status": file_item.status
                    })
            
            # Update vector DB
            embeddings_upserted = await vector_db.upsert_embeddings(
                collection=settings.VECTOR_DB_COLLECTION,
                documents=documents
            )
            
            # Update graph DB
            graph_nodes_updated = await graph_db.update_code_graph(
                files=file_paths
            )
        
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
        logger.error(f"Error applying diff: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply diff: {str(e)}"
        )

