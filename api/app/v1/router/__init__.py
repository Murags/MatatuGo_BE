from .auth import router as auth_router
from .routes import router as routes_router


from fastapi import APIRouter

router = APIRouter()
router.include_router(auth_router)
router.include_router(routes_router)
