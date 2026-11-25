from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.api import api_router
from app.services.ws_manager import ws_manager

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("forge.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager to initialize database and background services."""
    logger.info("Initializing FORGE Backend Services...")
    ws_manager.set_loop(asyncio.get_running_loop())
    init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down FORGE Backend Services...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="FORGE: Autonomous AI-Powered Software Engineering Platform API",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API v1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "status": "online",
        "docs": f"{settings.API_V1_STR}/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
