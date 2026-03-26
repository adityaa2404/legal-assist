from app.core.database import get_database
from app.core.config import settings
from app.models.user import UserCreate, UserInDB, UserResponse
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from typing import Optional
import logging

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


class AuthService:
    def __init__(self):
        db = get_database()
        self.collection = db.users

    def _hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def _verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    def create_access_token(self, email: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {"sub": email, "exp": expire}
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)

    def decode_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
            return payload.get("sub")
        except JWTError:
            return None

    async def register(self, user_data: UserCreate) -> Optional[UserInDB]:
        existing = await self.collection.find_one({"email": user_data.email})
        if existing:
            return None

        now = datetime.now(timezone.utc)
        user_doc = {
            "email": user_data.email,
            "full_name": user_data.full_name,
            "hashed_password": self._hash_password(user_data.password),
            "created_at": now,
            "is_active": True,
        }
        await self.collection.insert_one(user_doc)
        return UserInDB(**user_doc)

    async def authenticate(self, email: str, password: str) -> Optional[UserInDB]:
        user_doc = await self.collection.find_one({"email": email})
        if not user_doc:
            return None
        if not self._verify_password(password, user_doc["hashed_password"]):
            return None
        return UserInDB(**user_doc)

    async def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        user_doc = await self.collection.find_one({"email": email})
        if user_doc:
            return UserInDB(**user_doc)
        return None
