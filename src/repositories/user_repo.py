"""User repository for database operations.

SQLite를 사용하여 사용자 정보를 영구 저장합니다.
"""
import sqlite3
import asyncio
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from src.models.user import User
import logging

logger = logging.getLogger(__name__)


class UserRepository:
    """사용자 저장소.
    
    SQLite 데이터베이스를 사용하여 사용자 정보를 관리합니다.
    
    스키마:
        users 테이블:
        - id: INTEGER PRIMARY KEY AUTOINCREMENT
        - github_id: INTEGER UNIQUE NOT NULL
        - username: TEXT NOT NULL
        - email: TEXT
        - name: TEXT
        - api_key: TEXT UNIQUE NOT NULL
        - created_at: TEXT NOT NULL
        - last_login: TEXT
    """
    
    def __init__(self, db_path: str = "data/users.db"):
        """저장소 초기화 및 DB 스키마 생성.
        
        Args:
            db_path: SQLite 데이터베이스 파일 경로
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 동기 초기화 (테이블 생성)
        self._init_db()
    
    def _init_db(self):
        """데이터베이스 초기화 및 테이블 생성."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                github_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                email TEXT,
                name TEXT,
                api_key TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)
        
        # 인덱스 생성 (성능 최적화)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_github_id ON users(github_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_key ON users(api_key)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info(f"User database initialized at {self.db_path}")
    
    async def _run_in_executor(self, func, *args):
        """동기 DB 작업을 비동기로 실행.
        
        SQLite는 동기 API이므로 executor를 사용하여 블로킹을 방지합니다.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args)
    
    def _create_user_from_row(self, row: tuple) -> User:
        """DB row를 User 객체로 변환."""
        return User(
            id=row[0],
            github_id=row[1],
            username=row[2],
            email=row[3],
            name=row[4],
            api_key=row[5],
            created_at=datetime.fromisoformat(row[6]),
            last_login=datetime.fromisoformat(row[7]) if row[7] else None
        )
    
    def _get_by_github_id_sync(self, github_id: int) -> Optional[User]:
        """GitHub ID로 사용자 조회 (동기)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, github_id, username, email, name, api_key, created_at, last_login
            FROM users
            WHERE github_id = ?
        """, (github_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._create_user_from_row(row)
        return None
    
    async def get_by_github_id(self, github_id: int) -> Optional[User]:
        """GitHub ID로 사용자 조회.
        
        Args:
            github_id: GitHub 사용자 ID
            
        Returns:
            User 객체 또는 None
        """
        return await self._run_in_executor(self._get_by_github_id_sync, github_id)
    
    def _get_by_api_key_sync(self, api_key: str) -> Optional[User]:
        """API 키로 사용자 조회 (동기)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, github_id, username, email, name, api_key, created_at, last_login
            FROM users
            WHERE api_key = ?
        """, (api_key,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._create_user_from_row(row)
        return None
    
    async def get_by_api_key(self, api_key: str) -> Optional[User]:
        """API 키로 사용자 조회.
        
        Args:
            api_key: 사용자 API 키
            
        Returns:
            User 객체 또는 None
        """
        return await self._run_in_executor(self._get_by_api_key_sync, api_key)
    
    def _create_sync(self, github_id: int, username: str, 
                     email: Optional[str] = None, name: Optional[str] = None) -> User:
        """새 사용자 생성 (동기).
        
        Args:
            github_id: GitHub 사용자 ID
            username: GitHub 사용자명
            email: 이메일 (optional)
            name: 표시 이름 (optional)
            
        Returns:
            생성된 User 객체
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # API 키 생성 (UUID4)
        api_key = str(uuid.uuid4())
        created_at = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO users (github_id, username, email, name, api_key, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (github_id, username, email, name, api_key, created_at, created_at))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Created new user: {username} (github_id={github_id}, id={user_id})")
        
        return User(
            id=user_id,
            github_id=github_id,
            username=username,
            email=email,
            name=name,
            api_key=api_key,
            created_at=datetime.fromisoformat(created_at),
            last_login=datetime.fromisoformat(created_at)
        )
    
    async def create(self, github_id: int, username: str,
                    email: Optional[str] = None, name: Optional[str] = None) -> User:
        """새 사용자 생성.
        
        Args:
            github_id: GitHub 사용자 ID
            username: GitHub 사용자명
            email: 이메일 (optional)
            name: 표시 이름 (optional)
            
        Returns:
            생성된 User 객체
        """
        return await self._run_in_executor(
            self._create_sync, github_id, username, email, name
        )
    
    def _update_last_login_sync(self, user_id: int):
        """마지막 로그인 시각 업데이트 (동기)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE users
            SET last_login = ?
            WHERE id = ?
        """, (now, user_id))
        
        conn.commit()
        conn.close()
    
    async def update_last_login(self, user_id: int):
        """마지막 로그인 시각 업데이트.
        
        Args:
            user_id: 사용자 ID
        """
        await self._run_in_executor(self._update_last_login_sync, user_id)
        logger.debug(f"Updated last_login for user_id={user_id}")
    
    def _upsert_sync(self, github_id: int, username: str,
                    email: Optional[str] = None, name: Optional[str] = None) -> User:
        """사용자 upsert (없으면 생성, 있으면 업데이트) (동기).
        
        Args:
            github_id: GitHub 사용자 ID
            username: GitHub 사용자명
            email: 이메일 (optional)
            name: 표시 이름 (optional)
            
        Returns:
            User 객체
        """
        # 기존 사용자 조회
        existing = self._get_by_github_id_sync(github_id)
        
        if existing:
            # 기존 사용자: 정보 업데이트
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE users
                SET username = ?, email = ?, name = ?, last_login = ?
                WHERE github_id = ?
            """, (username, email, name, now, github_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Updated existing user: {username} (github_id={github_id})")
            
            # 업데이트된 사용자 반환
            existing.username = username
            existing.email = email
            existing.name = name
            existing.last_login = datetime.fromisoformat(now)
            return existing
        else:
            # 새 사용자 생성
            return self._create_sync(github_id, username, email, name)
    
    async def upsert(self, github_id: int, username: str,
                    email: Optional[str] = None, name: Optional[str] = None) -> User:
        """사용자 upsert (없으면 생성, 있으면 업데이트).
        
        GitHub OAuth callback에서 사용합니다.
        
        Args:
            github_id: GitHub 사용자 ID
            username: GitHub 사용자명
            email: 이메일 (optional)
            name: 표시 이름 (optional)
            
        Returns:
            User 객체
        """
        return await self._run_in_executor(
            self._upsert_sync, github_id, username, email, name
        )


# 전역 user repository 인스턴스
user_repo = UserRepository()

