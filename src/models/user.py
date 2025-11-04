"""User model and schema.

사용자 정보를 표현하는 모델입니다.
GitHub OAuth를 통해 인증된 사용자의 정보를 저장합니다.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class User(BaseModel):
    """사용자 모델.
    
    GitHub OAuth로 인증된 사용자 정보를 담습니다.
    각 사용자는 고유한 API 키를 가지며, 이를 통해 API 접근을 인증합니다.
    
    Attributes:
        id: 내부 사용자 ID (자동 증가)
        github_id: GitHub 사용자 ID (고유)
        username: GitHub 사용자명
        email: 사용자 이메일 (optional)
        name: 사용자 표시 이름 (optional)
        api_key: API 인증 키 (UUID 기반, 자동 생성)
        created_at: 계정 생성 시각
        last_login: 마지막 로그인 시각
    """
    id: Optional[int] = None
    github_id: int = Field(..., description="GitHub user ID")
    username: str = Field(..., description="GitHub username")
    email: Optional[str] = Field(None, description="User email")
    name: Optional[str] = Field(None, description="User display name")
    api_key: str = Field(..., description="API authentication key")
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True  # For ORM compatibility
        json_schema_extra = {
            "example": {
                "id": 1,
                "github_id": 12345678,
                "username": "parkj",
                "email": "parkj@example.com",
                "name": "Park J",
                "api_key": "abc123...",
                "created_at": "2024-01-01T00:00:00",
                "last_login": "2024-01-02T12:00:00"
            }
        }


class UserPublic(BaseModel):
    """공개용 사용자 정보 (API 키 제외).
    
    클라이언트에게 반환할 때 사용하는 모델입니다.
    보안을 위해 API 키는 제외합니다.
    """
    id: int
    github_id: int
    username: str
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None

