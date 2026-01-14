from sqlalchemy.ext.asyncio import AsyncSession
from ..models.user import User
from sqlalchemy import select

async def create_user(db: AsyncSession, request):
    """
    This function creates a new user in the database.
    Args:
        request: The request body containing the user data.
    Returns:
        The created user.
    """
    try:
        user = User(name=request.name, email=request.email)
        user.password = user.hash_password(request.password)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as e:
        print(f"Error creating user: {e}")
        raise e

async def get_user_by_email(db: AsyncSession, email: str):
    try:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    except Exception as e:
        print(f"Error fetching user by email: {e}")
        raise e

async def authenticate_user(db: AsyncSession, email: str, password: str):
    """
    This function authenticates a user.
    Args:
        email: The email of the user.
        password: The password of the user.
    Returns:
        The authenticated user or None if authentication fails.
    """
    try:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        if not user.verify_password(password):
            return None
        
        return user
    except Exception as e:
        print(f"Error authenticating user: {e}")
        raise e
