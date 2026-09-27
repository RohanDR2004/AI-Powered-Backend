from pydantic import BaseModel, Field


class AIGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class AIGenerateResponse(BaseModel):
    prompt: str
    response: str
