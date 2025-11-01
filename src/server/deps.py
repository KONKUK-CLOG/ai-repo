"""Dependency injection for FastAPI routes."""
from fastapi import Header, HTTPException, status
from src.server.settings import settings


async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify the API key from request header.
    
    Args:
        x_api_key: API key from x-api-key header
        
    Returns:
        The validated API key
        
    Raises:
        HTTPException: 401 if API key is invalid
    """
    if x_api_key != settings.SERVER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return x_api_key

