from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .database import init_db
from .middlewares import RedisRateLimitMiddleware, RequestAuditMiddleware
from .routes import auth, capacity, dashboard, followup, recovery, reports, samples, slots

app = FastAPI(title="门诊复诊候诊分布复盘", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RequestAuditMiddleware)
app.add_middleware(RedisRateLimitMiddleware)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(slots.router)
app.include_router(samples.router)
app.include_router(reports.router)
app.include_router(followup.router)
app.include_router(capacity.router)
app.include_router(recovery.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "backend"}
