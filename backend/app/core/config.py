import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FORGE"
    PROJECT_VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "forge_super_secure_jwt_secret_key_change_in_production_389271"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"
    
    # Database configuration
    # By default, use sqlite:///./forge.db for local development or postgresql://...
    DATABASE_URL: str = "sqlite:///./forge.db"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "forge"
    POSTGRES_PASSWORD: str = "forge_password"
    POSTGRES_DB: str = "forge_db"
    POSTGRES_PORT: int = 5432
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://forge-ai-neon-six.vercel.app",
]

    # External Provider Keys (optional in Phase 1)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str = ""  # Optional OpenAI-compatible endpoint (e.g. Ollama)
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    QDRANT_URL: str = "http://localhost:6333"
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "forge_graph"
    NEO4J_USE_MEMORY: bool = False

    # Phase 3 — Code RAG / Embedding configuration
    # Lightweight model: 384-dim, CPU-friendly, ~22M params
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    QDRANT_COLLECTION: str = "forge_code_chunks"
    # Use in-memory Qdrant when server is unavailable (development / CI)
    QDRANT_USE_MEMORY: bool = True
    # Chunking tuning
    RAG_CHUNK_MAX_LINES: int = 80
    RAG_CHUNK_OVERLAP_LINES: int = 10
    RAG_MAX_CHUNKS_PER_FILE: int = 500
    RAG_BATCH_SIZE: int = 32
    RAG_TOP_K: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        # Prevent default key in production environments
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and "change_in_production" in v:
            raise ValueError("Insecure default SECRET_KEY detected in production environment!")
        return v


settings = Settings()
