from sqlalchemy.ext.asyncio import AsyncSession
from ..models.user import User

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
