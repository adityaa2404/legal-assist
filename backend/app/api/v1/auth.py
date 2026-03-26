from fastapi import APIRouter, Depends, HTTPException
from app.models.user import UserCreate, UserLogin, UserResponse, TokenResponse
from app.services.auth_service import AuthService
from app.core.dependencies import get_auth_service, get_current_user

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


@router.get("/me", response_model=UserResponse)
async def get_profile(
    email: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    user = await auth_service.get_user_by_email(email)
    if not user:
        raise HTTPException(404, "User not found")
    return UserResponse(email=user.email, full_name=user.full_name, created_at=user.created_at)


@router.delete("/me", status_code=200)
async def delete_account(
    email: str = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    deleted = await auth_service.delete_account(email)
    if not deleted:
        raise HTTPException(404, "Account not found")
    return {"message": "Account and all associated data deleted"}
