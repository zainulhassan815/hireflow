from fastapi import APIRouter

from app.api.routes import auth, candidates, documents, health, jobs, rag, search, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
