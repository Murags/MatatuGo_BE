from fastapi import APIRouter, Depends, HTTPException, status
from ..crud import auth as auth_crud
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import database_session_manager
from ..schemas.auth import SignupRequest, SignupResponse, LoginRequest, LoginResponse
from ..utils.jwt import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=SignupResponse)
async def signup(signup_request: SignupRequest, db: AsyncSession = Depends(database_session_manager.get_async_db)):
    existing_user = await auth_crud.get_user_by_email(db, signup_request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="User with this email already exists")
    
    user = await auth_crud.create_user(db, signup_request)
    token = create_access_token(data={"sub": str(user.id)})
    return SignupResponse(id=user.id, name=user.name, email=user.email, access_token=token, created_at=user.created_at, updated_at=user.updated_at)

@router.post("/login", response_model=LoginResponse)
async def login(login_request: LoginRequest, db: AsyncSession = Depends(database_session_manager.get_async_db)):
    user = await auth_crud.authenticate_user(db, login_request.email, login_request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid email or password")
    
    token = create_access_token(data={"sub": str(user.id)})
    return LoginResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        access_token=token
    )
    