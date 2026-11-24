from fastapi import APIRouter
from app.api import auth, repositories, dashboard, health

api_router = APIRouter()

# Healthcheck
api_router.include_router(health.router)

# Authentication endpoints
api_router.include_router(auth.router)

# Repositories endpoints
api_router.include_router(repositories.router)

# Dashboard statistics
api_router.include_router(dashboard.router)
