from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from jose import jwt, JWTError
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.user import UserCreate, UserLogin, UserResponse, TokenResponse, UserInDB
from app.core.dependencies import get_current_user
from app.core.config import settings

router = APIRouter()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days


def _hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_access_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": email, "exp": expire}, settings.JWT_SECRET, algorithm="HS256")


async def _get_db():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    return client[settings.MONGO_DB_NAME]


# ── Normal email/password routes (for API testing & non-Clerk clients) ───────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserCreate):
    db = await _get_db()
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(400, "Email already registered")
    user = UserInDB(
        email=body.email,
        full_name=body.full_name,
        hashed_password=_hash_password(body.password),
        created_at=datetime.now(timezone.utc),
    )
    await db.users.insert_one(user.model_dump())
    token = _create_access_token(body.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(email=body.email, full_name=body.full_name, created_at=user.created_at),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin):
    db = await _get_db()
    doc = await db.users.find_one({"email": body.email})
    if not doc or not _verify_password(body.password, doc["hashed_password"]):
        raise HTTPException(401, "Invalid email or password")
    token = _create_access_token(body.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(email=doc["email"], full_name=doc["full_name"], created_at=doc.get("created_at")),
    )


# ── Clerk + normal JWT unified profile route ─────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_profile(email: str = Depends(get_current_user)):
    db = await _get_db()
    doc = await db.users.find_one({"email": email})
    full_name = doc["full_name"] if doc else ""
    created_at = doc.get("created_at") if doc else None
    return UserResponse(email=email, full_name=full_name, created_at=created_at)


@router.delete("/me", status_code=200)
async def delete_account(email: str = Depends(get_current_user)):
    db = await _get_db()
    await db.users.delete_one({"email": email})
    return {"message": "Account deleted"}
