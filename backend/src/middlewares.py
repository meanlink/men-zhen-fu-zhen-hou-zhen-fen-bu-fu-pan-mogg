import time

import redis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import REDIS_URL


class RequestAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        return response


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit: int = 120):
        super().__init__(app)
        self.limit = limit
        self.client = redis.from_url(REDIS_URL, decode_responses=True)

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ("/health", "/docs", "/openapi.json"):
            return await call_next(request)
        try:
            key = f"clinic-rate:{request.client.host if request.client else 'unknown'}"
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, 60)
            if count > self.limit:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
        except redis.RedisError:
            pass
        return await call_next(request)
