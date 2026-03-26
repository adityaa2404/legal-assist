from fastapi import APIRouter, Depends, HTTPException
from app.models.user import UserCreate, UserLogin, UserResponse, TokenResponse
from app.services.auth_service import AuthService
from app.core.dependencies import get_auth_service

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    user = await auth_service.register(user_data)
    if not user:
        raise HTTPException(409, "Registration failed. Please try a different email.")

    token = auth_service.create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at,
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
):
    user = await auth_service.authenticate(credentials.email, credentials.password)
    if not user:
        raise HTTPException(401, "Invalid email or password")

    token = auth_service.create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            email=user.email,
            full_name=user.full_name,
            created_at=user.created_at,
        ),
    )
