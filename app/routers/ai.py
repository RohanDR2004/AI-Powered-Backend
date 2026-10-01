from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.schemas.ai import AIGenerateRequest, AIGenerateResponse
from app.services.ai_service import AIConfigurationError, AIRequestError, generate_ai_response
from app.workers.tasks import enqueue_activity_log

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate", response_model=AIGenerateResponse)
async def generate(
    payload: AIGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await generate_ai_response(payload.prompt)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    await enqueue_activity_log(user_id=current_user.id, action="ai_generate", detail=f"Prompt: {payload.prompt[:100]}")
    return AIGenerateResponse(prompt=payload.prompt, response=result)
