from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import Base, engine
from app.routers import activity_logs, ai, auth, tasks, users

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="Phase 1 backend: authentication, task CRUD, AI integration, and activity logging.",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
app.include_router(ai.router)
app.include_router(activity_logs.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": settings.app_name}
