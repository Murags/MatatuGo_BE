from fastapi import APIRouter, Depends
from ..crud import auth as auth_crud
from sqlalchemy.ext.asyncio import AsyncSession
from ...database import database_session_manager
from ..schemas.auth import SignupRequest, SignupResponse


router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", response_model=SignupResponse)
async def signup(signup_request: SignupRequest, db: AsyncSession = Depends(database_session_manager.get_async_db)):
    user = await auth_crud.create_user(db, signup_request)
    return SignupResponse(id=user.id, name=user.name, email=user.email, created_at=user.created_at, updated_at=user.updated_at)
