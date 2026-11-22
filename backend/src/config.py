import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://clinic:clinic_password@db:5432/clinic_wait")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "clinic-wait-demo-secret")
JWT_ALGORITHM = "HS256"
CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:18240").split(",")]
ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "/shared")
