from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog


async def log_activity(db: AsyncSession, user_id: int, action: str, detail: str | None = None) -> None:
    entry = ActivityLog(user_id=user_id, action=action, detail=detail)
    db.add(entry)
    await db.commit()
