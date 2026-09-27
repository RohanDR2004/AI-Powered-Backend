from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.ai import AIGenerateRequest, AIGenerateResponse
from app.services.activity_service import log_activity
from app.services.ai_service import AIConfigurationError, AIRequestError, generate_ai_response

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate", response_model=AIGenerateResponse)
def generate(
    payload: AIGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = generate_ai_response(payload.prompt)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except AIRequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    log_activity(db, user_id=current_user.id, action="ai_generate", detail=f"Prompt: {payload.prompt[:100]}")
    return AIGenerateResponse(prompt=payload.prompt, response=result)
