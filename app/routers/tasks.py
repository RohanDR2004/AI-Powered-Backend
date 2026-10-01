from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.cache import get_cached, invalidate, invalidate_pattern, set_cached
from app.config import settings
from app.database import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.workers.tasks import enqueue_activity_log

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _list_cache_key(user_id: int, skip: int, limit: int) -> str:
    return f"cache:tasks:user:{user_id}:skip:{skip}:limit:{limit}"


def _list_cache_pattern(user_id: int) -> str:
    return f"cache:tasks:user:{user_id}:*"


def _task_cache_key(task_id: int) -> str:
    return f"cache:task:{task_id}"


async def _get_owned_task(db: AsyncSession, task_id: int, user_id: int) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id, Task.owner_id == user_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = Task(**payload.model_dump(), owner_id=current_user.id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await invalidate_pattern(_list_cache_pattern(current_user.id))
    await enqueue_activity_log(user_id=current_user.id, action="task_created", detail=f"Task '{task.title}' created")
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = _list_cache_key(current_user.id, skip, limit)
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Task)
        .where(Task.owner_id == current_user.id)
        .order_by(Task.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    tasks = result.scalars().all()
    serialized = [TaskOut.model_validate(task).model_dump(mode="json") for task in tasks]
    await set_cached(cache_key, serialized, settings.cache_ttl_seconds)
    return tasks


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = _task_cache_key(task_id)
    cached = await get_cached(cache_key)
    if cached is not None and cached.get("owner_id") == current_user.id:
        return cached

    task = await _get_owned_task(db, task_id, current_user.id)
    serialized = TaskOut.model_validate(task).model_dump(mode="json")
    await set_cached(cache_key, serialized, settings.cache_ttl_seconds)
    return task


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    await db.commit()
    await db.refresh(task)
    await invalidate(_task_cache_key(task_id))
    await invalidate_pattern(_list_cache_pattern(current_user.id))
    await enqueue_activity_log(user_id=current_user.id, action="task_updated", detail=f"Task '{task.title}' updated")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = await _get_owned_task(db, task_id, current_user.id)
    title = task.title
    await db.delete(task)
    await db.commit()
    await invalidate(_task_cache_key(task_id))
    await invalidate_pattern(_list_cache_pattern(current_user.id))
    await enqueue_activity_log(user_id=current_user.id, action="task_deleted", detail=f"Task '{title}' deleted")
    return None
