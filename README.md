# AI-Powered Applications Backend Platform — Phase 1

A FastAPI backend providing JWT authentication, task CRUD, AI text generation (OpenAI), and
per-user activity logging, backed by PostgreSQL.

## Tech Stack

- Python 3.10+
- FastAPI
- PostgreSQL + SQLAlchemy
- JWT (python-jose) + Passlib (bcrypt)
- OpenAI API
- Pytest

## Project Structure

```
app/
  main.py                 FastAPI app instance, routers, exception handlers
  config.py               Settings loaded from environment variables (.env)
  database.py             SQLAlchemy engine/session setup
  models/                 SQLAlchemy ORM models (User, Task, ActivityLog)
  schemas/                Pydantic request/response schemas
  auth/                   Password hashing, JWT creation/validation, auth dependency
  routers/                API route handlers (auth, users, tasks, ai, activity_logs)
  services/                Business logic (activity logging, AI provider calls)
tests/                    Pytest test suite
requirements.txt
.env.example
```

## Setup

### 1. Create a virtual environment and install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

```sql
CREATE DATABASE ai_backend;
```

(Optionally also `CREATE DATABASE ai_backend_test;` for running tests.)

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in real values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Secret used to sign JWT access tokens |
| `JWT_ALGORITHM` | JWT signing algorithm (default `HS256`) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes |
| `OPENAI_API_KEY` | OpenAI API key, required for `/ai/generate` |
| `OPENAI_MODEL` | OpenAI chat model name (default `gpt-4o-mini`) |

`OPENAI_API_KEY` is optional at startup — the app still runs without it. Calling
`/ai/generate` without a configured key returns `503 Service Unavailable` with a clear message
instead of crashing.

### 4. Run the application

```bash
uvicorn app.main:app --reload
```

- API root: http://127.0.0.1:8000/
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

Database tables are created automatically on startup.

## API Overview

### Authentication
- `POST /auth/register` — register with name, email, password (unique email enforced, password hashed with bcrypt)
- `POST /auth/login` — verify credentials, returns a JWT access token

### Users
- `GET /users/me` — returns the authenticated user's profile (requires `Authorization: Bearer <token>`)

### Tasks (CRUD, scoped to authenticated user)
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PUT /tasks/{task_id}`
- `DELETE /tasks/{task_id}`

### AI Integration
- `POST /ai/generate` — `{ "prompt": "..." }`, forwards the prompt to the OpenAI API and returns the generated text

### Activity Logs
- `GET /activity-logs` — returns the authenticated user's own activity history (login, task changes, AI requests)

## Authentication in Swagger UI

Click **Authorize** in `/docs` and paste the JWT access token obtained from `/auth/login`
(no `Bearer` prefix needed — Swagger adds it automatically).

## Running Tests

Tests run against a separate PostgreSQL database (`ai_backend_test` by default) and drop/recreate
tables between tests.

```bash
pytest -v
```

## Postman

Import `postman_collection.json` into Postman. Set the collection variable `base_url`
(default `http://127.0.0.1:8000`) and `access_token` after logging in.

## Security Notes

- Passwords are hashed with bcrypt, never stored in plain text.
- JWT secret and API keys are read from environment variables, never hard-coded.
- `.env` is excluded from version control via `.gitignore`.
