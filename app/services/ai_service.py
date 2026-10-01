from openai import APIError, AsyncOpenAI, OpenAIError

from app.config import settings


class AIConfigurationError(Exception):
    pass


class AIRequestError(Exception):
    pass


async def generate_ai_response(prompt: str) -> str:
    if not settings.openai_api_key:
        raise AIConfigurationError(
            "AI service is not configured. Set the OPENAI_API_KEY environment variable."
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        completion = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
        )
    except (APIError, OpenAIError) as exc:
        raise AIRequestError(f"AI provider request failed: {exc}") from exc

    return completion.choices[0].message.content or ""
