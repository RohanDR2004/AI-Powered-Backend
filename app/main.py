import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import Base, engine
from app.redis_client import redis_client
from app.routers import activity_logs, ai, auth, tasks, users

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app")

DEFAULT_JWT_SECRET = "change-this-secret-in-production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.jwt_secret_key == DEFAULT_JWT_SECRET:
        logger.warning(
            "JWT_SECRET_KEY is set to the insecure default. Set a unique secret via the "
            "JWT_SECRET_KEY environment variable before deploying."
        )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready; application startup complete.")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Authentication, task CRUD, AI integration, and activity logging.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(ai.router)
app.include_router(activity_logs.router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=settings.enable_docs)


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms
    )
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # Full traceback goes to the server log only; the client never sees
    # internal details (stack traces, DB errors, etc.) that could leak
    # implementation info.
    logger.exception("Unhandled exception while processing %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.app_name}


@app.get("/health", tags=["health"])
async def health():
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    database_ok = checks["database"] == "ok"
    overall = "ok" if all(v == "ok" for v in checks.values()) else ("degraded" if database_ok else "unhealthy")
    return JSONResponse(status_code=200 if database_ok else 503, content={"status": overall, "checks": checks})
