from fastapi import APIRouter

from app.api.routes import auth, health

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Future routers:
# api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
# api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
# api_router.include_router(search.router, prefix="/search", tags=["search"])
# api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
