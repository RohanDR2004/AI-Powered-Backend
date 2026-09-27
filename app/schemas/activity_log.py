from datetime import datetime

from pydantic import BaseModel


class ActivityLogOut(BaseModel):
    id: int
    action: str
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
