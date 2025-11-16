"""User model and schema.

사용자 정보를 표현하는 모델입니다.
GitHub OAuth와 Java 백엔드가 관리하는 사용자 정보를 다룹니다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    """사용자 모델.
    
    GitHub OAuth로 인증된 사용자 정보를 담습니다.
    Java 백엔드가 발급한 JWT를 사용하여 인증합니다.
    
    Attributes:
        id: 내부 사용자 ID
        github_id: GitHub 사용자 ID (고유)
        username: GitHub 사용자명
        email: 사용자 이메일 (optional)
        name: 사용자 표시 이름 (optional)
        avatar_url: 프로필 이미지 URL (optional)
        created_at: 계정 생성 시각
        last_login: 마지막 로그인 시각
    """
    id: Optional[int] = None
    github_id: int = Field(..., description="GitHub user ID")
    username: str = Field(..., description="GitHub username")
    email: Optional[str] = Field(None, description="User email")
    name: Optional[str] = Field(None, description="User display name")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")
    created_at: Optional[datetime] = Field(default=None, description="Account creation timestamp")
    last_login: Optional[datetime] = Field(default=None, description="Last login timestamp")
    
    class Config:
        from_attributes = True  # For ORM compatibility
        json_schema_extra = {
            "example": {
                "id": 1,
                "github_id": 12345678,
                "username": "parkj",
                "email": "parkj@example.com",
                "name": "Park J",
                "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
                "created_at": "2024-01-01T00:00:00",
                "last_login": "2024-01-02T12:00:00"
            }
        }

    @classmethod
    def from_backend(cls, payload: Dict[str, Any]) -> "User":
        """Create a User model from Java backend payload."""
        created_at = payload.get("created_at")
        last_login = payload.get("last_login")

        timestamps: Dict[str, Optional[datetime]] = {
            "created_at": None,
            "last_login": None,
        }

        if isinstance(created_at, str):
            try:
                timestamps["created_at"] = datetime.fromisoformat(created_at)
            except ValueError:
                pass

        if isinstance(last_login, str):
            try:
                timestamps["last_login"] = datetime.fromisoformat(last_login)
            except ValueError:
                pass

        model_data = {
            "id": payload.get("id"),
            "github_id": payload.get("github_id"),
            "username": payload.get("username"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "avatar_url": payload.get("avatar_url"),
            **timestamps,
        }
        return cls(**model_data)


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
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None

